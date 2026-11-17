"""Migrate a Widoco ``config.properties`` file to ``ontoreview.toml``."""

from __future__ import annotations

from pathlib import Path


def parse_properties(text: str) -> dict[str, str]:
    """Minimal Java .properties parser (key=value / key: value, # and ! comments, line continuations)."""
    out: dict[str, str] = {}
    buf = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not buf and (not line or line[0] in "#!"):
            continue
        if line.endswith("\\") and not line.endswith("\\\\"):
            buf += line[:-1]
            continue
        line = buf + line
        buf = ""
        for i, ch in enumerate(line):
            if ch in "=:" and (i == 0 or line[i - 1] != "\\"):
                key, val = line[:i].strip(), line[i + 1:].strip()
                out[key] = val.replace("\\:", ":").replace("\\=", "=")
                break
    return out


_SIMPLE = {
    "ontologyTitle": "title",
    "abstract": "abstract",
    "description": "description",
    "ontologyRevisionNumber": "version_info",
    "thisVersionURI": "version_iri",
    "previousVersionURI": "prior_version",
    "dateOfRelease": "issued",
    "modified": "modified",
    "licenseURI": "license",
    "licenseName": "license_label",
    "citeAs": "citation",
    "DOI": "doi",
    "ontologyPrefix": "preferred_prefix",
    "ontologyNamespaceURI": "preferred_namespace",
    "status": "status",
    "logo": "logo",
}


def _split(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(";") if x.strip()]


def _split_keep(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(";")] if v else []


def _agents(props: dict[str, str], name_key: str, uri_key: str, inst_key: str) -> list[dict]:
    names = _split(props.get(name_key))
    uris = _split_keep(props.get(uri_key))  # keep empty slots so positions line up with names
    insts = _split_keep(props.get(inst_key))
    out = []
    for i, n in enumerate(names):
        a = {"name": n}
        if i < len(uris) and uris[i]:
            a["iri"] = uris[i]
        if i < len(insts) and insts[i]:
            a["affiliation"] = insts[i]
        out.append(a)
    return out


def _toml_str(v: str) -> str:
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def widoco_to_toml(path: str | Path, source: str | None = None) -> str:
    props = parse_properties(Path(path).read_text("utf-8"))
    lines = ["# Migrated from Widoco config.properties by ontoreview", ""]
    if source:
        lines.append(f"source = {_toml_str(source)}")
    lines += ['output = "docs"', ""]
    lines.append("[metadata]")
    for k, field in _SIMPLE.items():
        if props.get(k):
            lines.append(f"{field} = {_toml_str(props[k])}")
    kws = _split(props.get("keywords"))
    if kws:
        lines.append("keywords = [" + ", ".join(_toml_str(k) for k in kws) + "]")
    for field, keys in (
        ("creators", ("authors", "authorsURI", "authorsInstitution")),
        ("contributors", ("contributors", "contributorsURI", "contributorsInstitution")),
        ("publishers", ("publisher", "publisherURI", "publisherInstitution")),
    ):
        agents = _agents(props, *keys)
        for a in agents:
            lines.append("")
            lines.append(f"[[metadata.{field}]]")
            for k, v in a.items():
                lines.append(f"{k} = {_toml_str(v)}")
    return "\n".join(lines) + "\n"
