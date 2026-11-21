"""The prompts sent to the language model, read from ``prompts.md`` (next to this file).

Each ``## name`` section of the Markdown file holds one prompt in its first fenced block. A file named by
``ONTOREVIEW_PROMPTS`` overrides the sections it defines; the others keep the packaged defaults.

    prompt("definition", context=...)   # the filled-in text
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

DEFAULT = Path(__file__).with_name("prompts.md")
SECTION = re.compile(r"^## +(?P<name>[\w-]+)\s*$(?P<body>.*?)(?=^## |\Z)", re.M | re.S)
FENCE = re.compile(r"^```[\w-]*\n(?P<text>.*?)\n```", re.M | re.S)


def parse(markdown: str) -> dict[str, str]:
    """{name: text} for every ``## name`` section that has a fenced block."""
    out = {}
    for m in SECTION.finditer(markdown):
        f = FENCE.search(m.group("body"))
        if f:
            out[m.group("name")] = f.group("text")
    return out


@lru_cache(maxsize=4)
def _load(override: str, mtimes: tuple) -> dict[str, str]:
    table = parse(DEFAULT.read_text("utf-8"))
    if override:
        table.update(parse(Path(override).expanduser().read_text("utf-8")))
    return table


def prompts() -> dict[str, str]:
    """All prompts; re-read when prompts.md (or the override) changes."""
    override = os.environ.get("ONTOREVIEW_PROMPTS", "")
    files = [DEFAULT] + ([Path(override).expanduser()] if override else [])
    return _load(override, tuple(f.stat().st_mtime if f.exists() else 0 for f in files))


def prompt(name: str, **values) -> str:
    """The prompt ``name`` with its ``{placeholders}`` filled in."""
    try:
        text = prompts()[name]
    except KeyError:
        raise KeyError(f"No prompt '{name}' in {DEFAULT.name}.") from None
    return text.format(**values)


__all__ = ["DEFAULT", "parse", "prompt", "prompts"]
