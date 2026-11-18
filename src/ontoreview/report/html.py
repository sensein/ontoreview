"""A quality report as a standalone HTML page, using the theme's quality section."""

from __future__ import annotations

from pathlib import Path


def quality_html(onto, report) -> str:
    """The quality report as a standalone HTML page (``ontoreview check --format html``)."""
    from ..config import Config
    from ..render.site import THEME_DIR, Section, SiteRenderer

    cfg = Config()
    r = SiteRenderer(cfg, onto, Path("."), report=report)
    tmpl = r.env.from_string(
        '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Quality report · {{ meta.title }}</title><style>{{ css|safe }}</style></head>'
        '<body><main class="content" style="margin:auto">{% include "sections/quality.html" %}</main></body></html>'
    )
    css = (THEME_DIR / "static" / "ontoreview.css").read_text("utf-8")
    s = Section("quality", f"Quality report: {onto.metadata.title or ''}", "quality.html",
                context={"report": report})
    return tmpl.render(s=s, css=css, page="index.html", sections=[s])
