# Classes

### Collection

**IRI:** `http://www.w3.org/2004/02/skos/core#Collection` · `skos:Collection`

A meaningful collection of concepts.

| | |
|---|---|
| Subclasses | [Ordered Collection](classes.md#orderedcollection) |
| Disjoint with | [Concept](classes.md#concept), [Concept Scheme](classes.md#conceptscheme) |
| Used in | in domain of [has member](object-properties.md#member); in range of [has member](object-properties.md#member) |

### Concept

**IRI:** `http://www.w3.org/2004/02/skos/core#Concept` · `skos:Concept`

An idea or notion; a unit of thought.

| | |
|---|---|
| Disjoint with | [Collection](classes.md#collection), [Concept Scheme](classes.md#conceptscheme) |
| Used in | in domain of [is in semantic relation with](object-properties.md#semanticrelation); in domain of [is top concept in scheme](object-properties.md#topconceptof); in range of [has member](object-properties.md#member); in range of [has top concept](object-properties.md#hastopconcept); in range of [is in semantic relation with](object-properties.md#semanticrelation) |

### Concept Scheme

**IRI:** `http://www.w3.org/2004/02/skos/core#ConceptScheme` · `skos:ConceptScheme`

A set of concepts, optionally including statements about semantic relationships between those concepts.

| | |
|---|---|
| Disjoint with | [Collection](classes.md#collection), [Concept](classes.md#concept) |
| Used in | in domain of [has top concept](object-properties.md#hastopconcept); in range of [is in scheme](object-properties.md#inscheme); in range of [is top concept in scheme](object-properties.md#topconceptof) |
| Examples | `Thesauri, classification schemes, subject heading lists, taxonomies, 'folksonomies', and other types of controlled vocabulary are all examples of concept schemes. Concept schemes are also embedded in glossaries and terminologies.` |

### Ordered Collection

**IRI:** `http://www.w3.org/2004/02/skos/core#OrderedCollection` · `skos:OrderedCollection`

An ordered collection of concepts, where both the grouping and the ordering are meaningful.

| | |
|---|---|
| Superclasses | [Collection](classes.md#collection) |
| Used in | in domain of [has member list](object-properties.md#memberlist) |

