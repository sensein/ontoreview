"""Plugin system.

A plugin is any object (module, class instance, ...) exposing some of these optional hooks:

    def sections(ontology, config) -> list[dict]
        # each dict: {"id", "title", "markdown" | "html", "position": "before-terms"|"after-terms"}
    def term_blocks(term, ontology) -> list[str]     # extra HTML appended to a term card
    def rules() -> list[ontoreview.checks.Rule]         # extra quality checks
    def template_dirs() -> list[str | Path]          # Jinja template overrides
    def postprocess(output_dir, ontology, config)    # run after the site is written

Plugins are discovered through the ``ontoreview.plugins`` entry-point group and from the
``plugins = ["package.module:object"]`` config option.
"""

from __future__ import annotations

import importlib
import logging
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

from markupsafe import Markup

log = logging.getLogger(__name__)


def _load_ref(ref: str) -> Any:
    mod_name, _, attr = ref.partition(":")
    obj = importlib.import_module(mod_name)
    for part in filter(None, attr.split(".")):
        obj = getattr(obj, part)
    return obj() if isinstance(obj, type) else obj


def load_plugins(refs: list[str], use_entry_points: bool = True) -> list[Any]:
    plugins: list[Any] = []
    if use_entry_points:
        try:
            for ep in entry_points(group="ontoreview.plugins"):
                try:
                    obj = ep.load()
                    plugins.append(obj() if isinstance(obj, type) else obj)
                except Exception as e:  # noqa: BLE001
                    log.warning("Failed to load plugin entry point %s: %s", ep.name, e)
        except TypeError:  # pragma: no cover - very old importlib.metadata
            pass
    for ref in refs:
        plugins.append(_load_ref(ref))
    return plugins


class PluginManager:
    def __init__(self, plugins: list[Any]):
        self.plugins = plugins

    def _call(self, hook: str, *args) -> list[Any]:
        out = []
        for p in self.plugins:
            fn = getattr(p, hook, None)
            if callable(fn):
                res = fn(*args)
                if res is not None:
                    out.append(res)
        return out

    def rules(self) -> list:
        return [r for res in self._call("rules") for r in res]

    def template_dirs(self) -> list[Path]:
        return [Path(d) for res in self._call("template_dirs") for d in res]

    def sections(self, ontology, config) -> list:
        from .render.site import Section, markdown

        out = []
        for res in self._call("sections", ontology, config):
            for s in res:
                body = Markup(s["html"]) if "html" in s else markdown(s.get("markdown", ""))
                out.append(Section(s["id"], s["title"], "custom.html",
                                   context={"body": body, "position": s.get("position", "after-terms")}))
        return out

    def decorate_terms(self, ontology) -> None:
        if not any(callable(getattr(p, "term_blocks", None)) for p in self.plugins):
            return
        for t in ontology.terms.values():
            for res in self._call("term_blocks", t, ontology):
                t.extra_blocks.extend(Markup(b) for b in res)

    def postprocess(self, out_dir, ontology, config) -> None:
        self._call("postprocess", out_dir, ontology, config)
