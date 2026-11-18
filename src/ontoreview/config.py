"""Configuration model.

Configuration is resolved from (lowest to highest priority):
defaults -> ``ontoreview.toml`` / ``[tool.ontoreview]`` in ``pyproject.toml`` -> explicit keyword/CLI overrides.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    iri: str | None = None
    email: str | None = None
    affiliation: str | None = None


class MetadataOverrides(BaseModel):
    """Any field set here wins over what is extracted from the ontology."""

    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    subtitle: str | None = None
    abstract: str | None = None
    description: str | None = None
    version_info: str | None = None
    version_iri: str | None = None
    prior_version: str | None = None
    issued: str | None = None
    modified: str | None = None
    created: str | None = None
    license: str | None = None
    license_label: str | None = None
    rights: str | None = None
    citation: str | None = None
    doi: str | None = None
    preferred_prefix: str | None = None
    preferred_namespace: str | None = None
    logo: str | None = None
    status: str | None = None
    homepage: str | None = None
    repository: str | None = None
    keywords: list[str] | None = None
    creators: list[AgentConfig] | None = None
    contributors: list[AgentConfig] | None = None
    publishers: list[AgentConfig] | None = None
    funders: list[AgentConfig] | None = None


class CustomSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    file: str | None = None
    content: str | None = None
    position: Literal["before-terms", "after-terms"] = "before-terms"
    id: str | None = None


class SectionToggles(BaseModel):
    model_config = ConfigDict(extra="forbid")
    introduction: bool = True
    metadata: bool = True
    overview: bool = True
    graph: bool = True
    namespaces: bool = True
    terms: bool = True
    competency_questions: bool = True
    changelog: bool = True
    quality: bool = True
    provenance: bool = True
    citation: bool = True
    serializations: bool = True


class UIConfig(BaseModel):
    """Presentation options for the generated site."""

    model_config = ConfigDict(extra="forbid")
    term_index: Literal["sidebar", "section", "both", "none"] = Field(
        "sidebar", description="Where the list of terms appears: as a sub-hierarchy in the sidebar, "
                               "as an 'Index of terms' section, both, or nowhere")
    sidebar_expanded: bool = Field(False, description="Open the sidebar term lists by default")
    sidebar_term_limit: int = Field(600, description="Kinds with more terms get no sidebar sub-list")
    section_numbers: bool = True
    font: Literal["serif", "sans"] = "serif"
    accent: str | None = Field(None, description="Link colour, e.g. '#1d4f91'")
    width: Literal["normal", "wide"] = "wide"
    graph_notation: Literal["vowl", "uml"] = Field(
        "vowl", description="Figure notation: 'vowl' (WebVOWL-style circles) or 'uml' (class boxes)")
    graph_layout: Literal["auto", "hierarchy", "force", "concentric"] = Field(
        "auto", description="'auto' = force for VOWL, hierarchy for UML")
    graph_property_edges: bool | Literal["auto"] = Field(
        "auto", description="Show object-property edges: true, false or auto (on for up to 40 classes)")
    graph_top_levels: int = Field(2, description="Levels shown initially for large hierarchies")
    section_order: list[str] = Field(default_factory=list, description="Section ids in display order; "
                                     "'reference' stands for all term sections")


class EvaluationConfig(BaseModel):
    """External evaluators shown in the quality report."""

    model_config = ConfigDict(extra="forbid")
    oops: Literal["auto", "on", "off"] = Field(
        "auto", description="OOPS! pitfall scanner web service (uploads the ontology to "
                            "https://oops.linkeddata.es): auto = run alongside ROBOT, leaving out the pitfalls ROBOT "
                            "covers (full catalogue when ROBOT cannot run); on = always the full catalogue; off = never")
    oops_timeout: int = 90
    oops_endpoint: str | None = Field(None, description="OOPS! REST endpoint (default https://oops.linkeddata.es/rest)")
    robot: Literal["auto", "on", "off"] = Field(
        "auto", description="Run `robot report` (local robot, else Docker). auto = run, falling back to OOPS! "
                            "when unavailable; on = same, and report an error if unavailable; off = never")
    robot_path: str | None = Field(None, description="A local `robot` executable (optional; Docker is used otherwise)")
    robot_image: str = Field("obolibrary/robot", description="Docker image used to run ROBOT")
    robot_profile: str | None = Field(None, description="Custom ROBOT report profile (TSV)")
    reasoner: Literal["hermit", "elk", "off"] = Field(
        "hermit", description="Logical consistency check with an OWL reasoner via `robot reason` (needs ROBOT): "
                              "hermit = full OWL 2 DL, elk = fast, OWL 2 EL only, off = skip")
    reasoner_timeout: int = Field(600, description="Seconds before the reasoner is stopped")

    @field_validator("oops", "robot", mode="before")
    @classmethod
    def _bool_to_mode(cls, v):
        # older configs used oops = true / false
        return {True: "on", False: "off"}.get(v, v) if isinstance(v, bool) else v


class ChecksConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disable: list[str] = Field(default_factory=list)
    severity: dict[str, Literal["error", "warning", "info"]] = Field(default_factory=dict)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Input
    source: str | None = None
    format: str | None = None
    load_imports: bool = False
    direct_imports_only: bool = False
    imports: dict[str, str] = Field(default_factory=dict, description="IRI -> local file")
    catalog: str | None = None
    include_imported: bool = False

    # Content selection
    include_individuals: bool = True
    include_annotation_properties: bool = True
    include_external: bool = True
    reason: bool = False
    label_properties: list[str] = Field(default_factory=list, description="Extra label properties (CURIE/IRI), highest priority")
    definition_properties: list[str] = Field(default_factory=list, description="Extra definition properties (CURIE/IRI)")

    # Output
    output: str = "docs"
    layout: Literal["single", "multi"] = "single"
    languages: list[str] = Field(default_factory=lambda: ["en"])
    base_url: str | None = None
    theme: str | None = None
    custom_css: str | None = None
    head_html: str | None = None
    sections: SectionToggles = Field(default_factory=SectionToggles)
    ui: UIConfig = Field(default_factory=UIConfig)
    introduction: str | None = Field(None, description="Markdown file or text for the introduction")
    custom_sections: list[CustomSection] = Field(default_factory=list)

    # Competency questions (YAML / JSON / CSV / TSV / XLSX)
    competency_questions: list[str] = Field(default_factory=list)

    # Changelog
    previous_version: str | None = Field(None, description="File/URL of the previous release")

    # Publishing
    serializations: list[str] = Field(default_factory=lambda: ["ttl", "owl", "jsonld", "nt"])
    serialization_basename: str = "ontology"
    conneg: bool = True
    rewrite_base: str = "/"

    # Machine-readable docs for LLMs and agents: llms.txt, llms-full.txt, *.md, ontology.json
    llm: bool = True

    # Extensibility
    plugins: list[str] = Field(default_factory=list)
    checks: ChecksConfig = Field(default_factory=ChecksConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    metadata: MetadataOverrides = Field(default_factory=MetadataOverrides)

    # Internal: directory the config was loaded from (relative paths resolve against it)
    root: str = Field(".", exclude=True)

    def resolve(self, path: str | None) -> Path | None:
        if path is None:
            return None
        p = Path(path)
        return p if p.is_absolute() else Path(self.root) / p


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in extra.items():
        if v is None:
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def find_config_file(start: Path) -> Path | None:
    for name in ("ontoreview.toml", ".ontoreview.toml"):
        p = start / name
        if p.is_file():
            return p
    pp = start / "pyproject.toml"
    if pp.is_file():
        data = tomllib.loads(pp.read_text("utf-8"))
        if "ontoreview" in data.get("tool", {}):
            return pp
    return None


def load_config(path: str | Path | None = None, **overrides: Any) -> Config:
    """Load configuration from ``path`` (or auto-discover in cwd) and apply overrides."""
    data: dict[str, Any] = {}
    root = Path.cwd()
    cfg_path = Path(path) if path else find_config_file(Path.cwd())
    if cfg_path is not None:
        raw = tomllib.loads(cfg_path.read_text("utf-8"))
        if cfg_path.name == "pyproject.toml":
            raw = raw.get("tool", {}).get("ontoreview", {})
        data = raw
        root = cfg_path.parent.resolve()
    data = _deep_merge(data, overrides)
    data["root"] = str(root)
    return Config.model_validate(data)


CONFIG_TEMPLATE = """# OntoReview project configuration — https://github.com/CAIRNepal/ontoreview
# Keep this file next to your ontology. `ontoreview build`, `ontoreview check`, CI and the app all read it,
# so everyone gets the same documentation. Paths are relative to this file.

source = "{source}"
output = "docs"
layout = "single"           # "single" (one page) or "multi" (one page per section)
languages = ["en"]          # first one is the default; others are built under /<lang>/
# base_url = "https://w3id.org/my-ontology"   # where the docs will be published
# previous_version = "releases/1.0.0.ttl"     # enables the changelog
# competency_questions = ["cq.yaml"]
# introduction = "docs/intro.md"
# custom_css = "docs/custom.css"
# reason = true             # show inferred superclasses (pip install 'ontoreview[reason]')

serializations = ["ttl", "owl", "jsonld", "nt"]

[sections]
graph = true
quality = true
changelog = true

[checks]
disable = []                # e.g. ["OB019"]

[evaluation]
robot = "auto"              # ROBOT via a local robot or Docker: "auto" | "on" | "off"
oops = "auto"               # OOPS! web service (uploads the ontology): "auto" (complements ROBOT) | "on" (full) | "off"
reasoner = "hermit"         # logical consistency via ROBOT: "hermit" | "elk" (fast, OWL 2 EL only) | "off"

# Metadata found in the ontology is used automatically; anything here overrides it.
[metadata]
# title = "My Ontology"
# license = "https://creativecommons.org/licenses/by/4.0/"

# [[custom_sections]]
# title = "Examples"
# file = "docs/examples.md"
# position = "after-terms"
"""


def validate_config_text(text: str, root: str | Path | None = None) -> list[str]:
    """Problems in an ontoreview.toml's text (empty list when it is valid)."""
    from pydantic import ValidationError

    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return [f"TOML syntax: {e}"]
    try:
        Config.model_validate({**data, "root": str(root or Path.cwd())})
    except ValidationError as e:
        return [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
    return []
