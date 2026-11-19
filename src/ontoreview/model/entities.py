"""In-memory documentation model. Templates and exporters only ever see these objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

KIND_LABELS = {
    "class": ("Class", "Classes"),
    "object_property": ("Object property", "Object properties"),
    "datatype_property": ("Datatype property", "Datatype properties"),
    "property": ("Property", "Properties"),
    "annotation_property": ("Annotation property", "Annotation properties"),
    "datatype": ("Datatype", "Datatypes"),
    "individual": ("Named individual", "Named individuals"),
    "concept_scheme": ("Concept scheme", "Concept schemes"),
    "concept": ("Concept", "Concepts"),
}

KIND_SLUGS = {
    "class": "classes",
    "object_property": "object-properties",
    "datatype_property": "datatype-properties",
    "property": "properties",
    "annotation_property": "annotation-properties",
    "datatype": "datatypes",
    "individual": "individuals",
    "concept_scheme": "concept-schemes",
    "concept": "concepts",
}

KIND_BADGES = {
    "class": "c",
    "object_property": "op",
    "datatype_property": "dp",
    "property": "p",
    "annotation_property": "ap",
    "datatype": "dt",
    "individual": "ni",
    "concept_scheme": "cs",
    "concept": "sc",
}


@dataclass(frozen=True)
class Ref:
    """A reference to an IRI: link target + display label."""

    iri: str
    label: str
    curie: str | None = None
    internal: bool = False
    anchor: str | None = None
    kind: str | None = None


# An expression is a list of tokens: ("ref", Ref) | ("kw", str) | ("punct", str) | ("lit", str)
Token = tuple[str, Any]
Expr = list[Token]


@dataclass
class Agent:
    name: str
    iri: str | None = None
    email: str | None = None
    orcid: str | None = None
    affiliation: str | None = None
    homepage: str | None = None


@dataclass
class Annotation:
    prop: Ref
    values: list[Expr]


@dataclass
class UsageRef:
    role: str  # e.g. "domain of", "range of", "restriction in"
    ref: Ref


@dataclass
class Term:
    iri: str
    kind: str
    anchor: str
    curie: str | None
    local_name: str
    label: str
    labels: dict[str, list[str]] = field(default_factory=dict)  # lang -> labels
    definition: str | None = None
    definitions: dict[str, str] = field(default_factory=dict)  # lang -> definition
    comments: list[str] = field(default_factory=list)
    alt_labels: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    notes: dict[str, list[str]] = field(default_factory=dict)
    see_also: list[Expr] = field(default_factory=list)
    is_defined_by: list[Ref] = field(default_factory=list)
    source: list[Expr] = field(default_factory=list)
    deprecated: bool = False
    replaced_by: list[Ref] = field(default_factory=list)
    status: str | None = None
    external: bool = False  # declared here but outside the ontology namespace
    imported: bool = False  # only declared in an imported ontology
    undeclared: bool = False  # annotation property used here but declared nowhere in the input
    use_count: int = 0  # undeclared annotation properties: number of terms (and header) using it

    # classes
    superclasses: list[Ref] = field(default_factory=list)
    inferred_superclasses: list[Ref] = field(default_factory=list)
    subclasses: list[Ref] = field(default_factory=list)
    restrictions: list[Expr] = field(default_factory=list)  # anonymous superclass expressions
    equivalent: list[Expr] = field(default_factory=list)
    disjoint: list[Ref] = field(default_factory=list)
    disjoint_union: list[Expr] = field(default_factory=list)
    keys: list[Expr] = field(default_factory=list)
    instances: list[Ref] = field(default_factory=list)

    # properties
    domain: list[Expr] = field(default_factory=list)
    range: list[Expr] = field(default_factory=list)
    characteristics: list[str] = field(default_factory=list)
    inverse_of: list[Expr] = field(default_factory=list)
    super_properties: list[Ref] = field(default_factory=list)
    sub_properties: list[Ref] = field(default_factory=list)
    equivalent_properties: list[Ref] = field(default_factory=list)
    disjoint_properties: list[Ref] = field(default_factory=list)
    chains: list[Expr] = field(default_factory=list)

    # individuals
    types: list[Expr] = field(default_factory=list)
    facts: list[tuple[Ref, Expr]] = field(default_factory=list)
    same_as: list[Ref] = field(default_factory=list)

    # SKOS
    broader: list[Ref] = field(default_factory=list)
    narrower: list[Ref] = field(default_factory=list)
    related: list[Ref] = field(default_factory=list)
    in_scheme: list[Ref] = field(default_factory=list)
    top_concepts: list[Ref] = field(default_factory=list)
    mappings: dict[str, list[Ref]] = field(default_factory=dict)

    used_in: list[UsageRef] = field(default_factory=list)
    annotations: list[Annotation] = field(default_factory=list)
    extra_blocks: list[str] = field(default_factory=list)  # plugin-provided HTML
    competency_questions: list[tuple[str, str]] = field(default_factory=list)  # (id, anchor)

    @property
    def kind_label(self) -> str:
        return KIND_LABELS[self.kind][0]

    @property
    def badge(self) -> str:
        return KIND_BADGES[self.kind]

    def ref(self) -> Ref:
        return Ref(self.iri, self.label, self.curie, True, self.anchor, self.kind)


@dataclass
class Metadata:
    iri: str | None = None
    title: str | None = None
    subtitle: str | None = None
    abstract: str | None = None
    description: str | None = None
    version_info: str | None = None
    version_iri: str | None = None
    prior_version: str | None = None
    backward_compatible_with: list[str] = field(default_factory=list)
    incompatible_with: list[str] = field(default_factory=list)
    issued: str | None = None
    created: str | None = None
    modified: str | None = None
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
    keywords: list[str] = field(default_factory=list)
    creators: list[Agent] = field(default_factory=list)
    contributors: list[Agent] = field(default_factory=list)
    publishers: list[Agent] = field(default_factory=list)
    funders: list[Agent] = field(default_factory=list)
    imports: list[Ref] = field(default_factory=list)
    see_also: list[str] = field(default_factory=list)
    source: list[str] = field(default_factory=list)
    other: list[Annotation] = field(default_factory=list)

    def missing(self) -> list[str]:
        wanted = ["title", "description", "license", "version_info", "creators",
                  "preferred_prefix", "preferred_namespace"]
        return [w for w in wanted if not getattr(self, w)]


@dataclass
class TreeNode:
    ref: Ref
    children: list[TreeNode] = field(default_factory=list)


@dataclass
class Ontology:
    metadata: Metadata
    namespace: str | None
    terms: dict[str, Term]  # iri -> term
    prefixes: list[tuple[str, str]]
    class_tree: list[TreeNode] = field(default_factory=list)
    property_tree: list[TreeNode] = field(default_factory=list)
    concept_tree: list[TreeNode] = field(default_factory=list)
    kind_trees: dict[str, list[TreeNode]] = field(default_factory=dict)  # per-kind sidebar trees
    source_kind: str = "rdf"
    language: str = "en"
    stats: dict[str, int] = field(default_factory=dict)

    def by_kind(self, kind: str) -> list[Term]:
        return sorted(
            (t for t in self.terms.values() if t.kind == kind),
            key=lambda t: (t.label.lower(), t.iri),
        )

    def kinds_present(self) -> list[str]:
        from ..vocab import KIND_ORDER

        return [k for k in KIND_ORDER if any(t.kind == k for t in self.terms.values())]
