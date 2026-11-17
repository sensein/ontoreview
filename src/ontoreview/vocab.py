"""Namespace constants and property groupings used across ontoreview."""

from __future__ import annotations

from rdflib import Namespace
from rdflib.namespace import DC, DCTERMS, FOAF, OWL, RDF, RDFS, SKOS, XSD

VANN = Namespace("http://purl.org/vocab/vann/")
SCHEMA = Namespace("https://schema.org/")
SCHEMA_HTTP = Namespace("http://schema.org/")
PROV = Namespace("http://www.w3.org/ns/prov#")
BIBO = Namespace("http://purl.org/ontology/bibo/")
CC = Namespace("http://creativecommons.org/ns#")
PAV = Namespace("http://purl.org/pav/")
VS = Namespace("http://www.w3.org/2003/06/sw-vocab-status/ns#")
OBO = Namespace("http://purl.obolibrary.org/obo/")
OBOINOWL = Namespace("http://www.geneontology.org/formats/oboInOwl#")
MOD = Namespace("https://w3id.org/mod#")
ADMS = Namespace("http://www.w3.org/ns/adms#")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
DOAP = Namespace("http://usefulinc.com/ns/doap#")
VCARD = Namespace("http://www.w3.org/2006/vcard/ns#")
WIDOCO = Namespace("https://w3id.org/widoco/vocab#")


def _both_schema(local: str) -> list:
    return [SCHEMA[local], SCHEMA_HTTP[local]]


# --- Term-level annotation properties (ordered by priority) -------------------
LABEL_PROPS = [RDFS.label, SKOS.prefLabel, *_both_schema("name"), DCTERMS.title, DC.title]
ALT_LABEL_PROPS = [SKOS.altLabel, OBOINOWL.hasExactSynonym, OBOINOWL.hasRelatedSynonym]
DEFINITION_PROPS = [
    SKOS.definition,
    OBO.IAO_0000115,
    DCTERMS.description,
    DC.description,
    *_both_schema("description"),
    RDFS.comment,
]
COMMENT_PROPS = [RDFS.comment]
EXAMPLE_PROPS = [SKOS.example, VANN.example, OBO.IAO_0000112]
NOTE_PROPS = {
    SKOS.scopeNote: "scope_note",
    SKOS.editorialNote: "editorial_note",
    SKOS.historyNote: "history_note",
    SKOS.changeNote: "change_note",
    SKOS.note: "note",
    VANN.usageNote: "usage_note",
    OBO.IAO_0000116: "editorial_note",
}
REPLACED_BY_PROPS = [DCTERMS.isReplacedBy, OBO.IAO_0100001]
STATUS_PROPS = [VS.term_status, BIBO.status, MOD.status, ADMS.status]
SOURCE_PROPS = [DCTERMS.source, PROV.wasDerivedFrom, OBO.IAO_0000119]

# Predicates rendered elsewhere so they are not repeated as "other annotations".
STRUCTURAL_PREDICATES = {
    RDF.type,
    RDFS.subClassOf,
    RDFS.subPropertyOf,
    RDFS.domain,
    RDFS.range,
    RDFS.isDefinedBy,
    RDFS.seeAlso,
    OWL.equivalentClass,
    OWL.equivalentProperty,
    OWL.disjointWith,
    OWL.inverseOf,
    OWL.propertyChainAxiom,
    OWL.deprecated,
    OWL.sameAs,
    OWL.differentFrom,
    OWL.propertyDisjointWith,
    OWL.hasKey,
    OWL.disjointUnionOf,
    OWL.unionOf,
    OWL.intersectionOf,
    OWL.oneOf,
    SKOS.broader,
    SKOS.narrower,
    SKOS.related,
    SKOS.inScheme,
    SKOS.topConceptOf,
    SKOS.hasTopConcept,
    SKOS.exactMatch,
    SKOS.closeMatch,
    SKOS.broadMatch,
    SKOS.narrowMatch,
    SKOS.relatedMatch,
    *LABEL_PROPS,
    *ALT_LABEL_PROPS,
    *DEFINITION_PROPS,
    *EXAMPLE_PROPS,
    *NOTE_PROPS.keys(),
    *REPLACED_BY_PROPS,
    *STATUS_PROPS,
    *SOURCE_PROPS,
}

CHARACTERISTICS = {
    OWL.FunctionalProperty: "Functional",
    OWL.InverseFunctionalProperty: "Inverse functional",
    OWL.TransitiveProperty: "Transitive",
    OWL.SymmetricProperty: "Symmetric",
    OWL.AsymmetricProperty: "Asymmetric",
    OWL.ReflexiveProperty: "Reflexive",
    OWL.IrreflexiveProperty: "Irreflexive",
}

# Vocabularies whose terms are never documented as part of the user's ontology.
BUILTIN_NAMESPACES = (
    str(RDF),
    str(RDFS),
    str(OWL),
    str(XSD),
    "http://www.w3.org/XML/1998/namespace",
)

KIND_ORDER = [
    "class",
    "object_property",
    "datatype_property",
    "property",
    "annotation_property",
    "datatype",
    "individual",
    "concept_scheme",
    "concept",
]

__all__ = [
    "DC",
    "DCTERMS",
    "FOAF",
    "OWL",
    "RDF",
    "RDFS",
    "SKOS",
    "XSD",
]
