# Object properties

### has broader

**IRI:** `http://www.w3.org/2004/02/skos/core#broader` · `skos:broader`

Relates a concept to a concept that is more general in meaning.

Broader concepts are typically rendered as parents in a concept hierarchy (tree).

| | |
|---|---|
| Super-properties | [has broader transitive](object-properties.md#broadertransitive) |
| Sub-properties | [has broader match](object-properties.md#broadmatch) |
| Inverse of | [has narrower](object-properties.md#narrower) |

### has broader match

**IRI:** `http://www.w3.org/2004/02/skos/core#broadMatch` · `skos:broadMatch`

skos:broadMatch is used to state a hierarchical mapping link between two conceptual resources in different concept schemes.

| | |
|---|---|
| Super-properties | [has broader](object-properties.md#broader), [is in mapping relation with](object-properties.md#mappingrelation) |
| Inverse of | [has narrower match](object-properties.md#narrowmatch) |

### has broader transitive

**IRI:** `http://www.w3.org/2004/02/skos/core#broaderTransitive` · `skos:broaderTransitive`

skos:broaderTransitive is a transitive superproperty of skos:broader.

| | |
|---|---|
| Super-properties | [is in semantic relation with](object-properties.md#semanticrelation) |
| Sub-properties | [has broader](object-properties.md#broader) |
| Characteristics | Transitive |
| Inverse of | [has narrower transitive](object-properties.md#narrowertransitive) |

### has close match

**IRI:** `http://www.w3.org/2004/02/skos/core#closeMatch` · `skos:closeMatch`

skos:closeMatch is used to link two concepts that are sufficiently similar that they can be used interchangeably in some information retrieval applications. In order to avoid the possibility of "compound errors" when combining mappings across more than two concept schemes, skos:closeMatch is not declared to be a transitive property.

| | |
|---|---|
| Super-properties | [is in mapping relation with](object-properties.md#mappingrelation) |
| Sub-properties | [has exact match](object-properties.md#exactmatch) |
| Characteristics | Symmetric |

### has exact match

**IRI:** `http://www.w3.org/2004/02/skos/core#exactMatch` · `skos:exactMatch`

skos:exactMatch is used to link two concepts, indicating a high degree of confidence that the concepts can be used interchangeably across a wide range of information retrieval applications. skos:exactMatch is a transitive property, and is a sub-property of skos:closeMatch.

skos:exactMatch is disjoint with each of the properties skos:broadMatch and skos:relatedMatch.

| | |
|---|---|
| Super-properties | [has close match](object-properties.md#closematch) |
| Characteristics | Transitive, Symmetric |

### has member

**IRI:** `http://www.w3.org/2004/02/skos/core#member` · `skos:member`

Relates a collection to one of its members.

| | |
|---|---|
| Domain | [Collection](classes.md#collection) |
| Range | [Concept](classes.md#concept) *or* [Collection](classes.md#collection) |

### has member list

**IRI:** `http://www.w3.org/2004/02/skos/core#memberList` · `skos:memberList`

Relates an ordered collection to the RDF list containing its members.

For any resource, every item in the list given as the value of the
      skos:memberList property is also a value of the skos:member property.

| | |
|---|---|
| Domain | [Ordered Collection](classes.md#orderedcollection) |
| Range | [rdf:List](http://www.w3.org/1999/02/22-rdf-syntax-ns#List) |
| Characteristics | Functional |

### has narrower

**IRI:** `http://www.w3.org/2004/02/skos/core#narrower` · `skos:narrower`

Relates a concept to a concept that is more specific in meaning.

Narrower concepts are typically rendered as children in a concept hierarchy (tree).

| | |
|---|---|
| Super-properties | [has narrower transitive](object-properties.md#narrowertransitive) |
| Sub-properties | [has narrower match](object-properties.md#narrowmatch) |
| Inverse of | [has broader](object-properties.md#broader) |

### has narrower match

**IRI:** `http://www.w3.org/2004/02/skos/core#narrowMatch` · `skos:narrowMatch`

skos:narrowMatch is used to state a hierarchical mapping link between two conceptual resources in different concept schemes.

| | |
|---|---|
| Super-properties | [has narrower](object-properties.md#narrower), [is in mapping relation with](object-properties.md#mappingrelation) |
| Inverse of | [has broader match](object-properties.md#broadmatch) |

### has narrower transitive

**IRI:** `http://www.w3.org/2004/02/skos/core#narrowerTransitive` · `skos:narrowerTransitive`

skos:narrowerTransitive is a transitive superproperty of skos:narrower.

| | |
|---|---|
| Super-properties | [is in semantic relation with](object-properties.md#semanticrelation) |
| Sub-properties | [has narrower](object-properties.md#narrower) |
| Characteristics | Transitive |
| Inverse of | [has broader transitive](object-properties.md#broadertransitive) |

### has related

**IRI:** `http://www.w3.org/2004/02/skos/core#related` · `skos:related`

Relates a concept to a concept with which there is an associative semantic relationship.

skos:related is disjoint with skos:broaderTransitive

| | |
|---|---|
| Super-properties | [is in semantic relation with](object-properties.md#semanticrelation) |
| Sub-properties | [has related match](object-properties.md#relatedmatch) |
| Characteristics | Symmetric |

### has related match

**IRI:** `http://www.w3.org/2004/02/skos/core#relatedMatch` · `skos:relatedMatch`

skos:relatedMatch is used to state an associative mapping link between two conceptual resources in different concept schemes.

| | |
|---|---|
| Super-properties | [has related](object-properties.md#related), [is in mapping relation with](object-properties.md#mappingrelation) |
| Characteristics | Symmetric |

### has top concept

**IRI:** `http://www.w3.org/2004/02/skos/core#hasTopConcept` · `skos:hasTopConcept`

Relates, by convention, a concept scheme to a concept which is topmost in the broader/narrower concept hierarchies for that scheme, providing an entry point to these hierarchies.

| | |
|---|---|
| Domain | [Concept Scheme](classes.md#conceptscheme) |
| Range | [Concept](classes.md#concept) |
| Inverse of | [is top concept in scheme](object-properties.md#topconceptof) |

### is in mapping relation with

**IRI:** `http://www.w3.org/2004/02/skos/core#mappingRelation` · `skos:mappingRelation`

Relates two concepts coming, by convention, from different schemes, and that have comparable meanings

These concept mapping relations mirror semantic relations, and the data model defined below is similar (with the exception of skos:exactMatch) to the data model defined for semantic relations. A distinct vocabulary is provided for concept mapping relations, to provide a convenient way to differentiate links within a concept scheme from links between concept schemes. However, this pattern of usage is not a formal requirement of the SKOS data model, and relies on informal definitions of best practice.

| | |
|---|---|
| Super-properties | [is in semantic relation with](object-properties.md#semanticrelation) |
| Sub-properties | [has broader match](object-properties.md#broadmatch), [has close match](object-properties.md#closematch), [has narrower match](object-properties.md#narrowmatch), [has related match](object-properties.md#relatedmatch) |

### is in scheme

**IRI:** `http://www.w3.org/2004/02/skos/core#inScheme` · `skos:inScheme`

Relates a resource (for example a concept) to a concept scheme in which it is included.

| | |
|---|---|
| Sub-properties | [is top concept in scheme](object-properties.md#topconceptof) |
| Range | [Concept Scheme](classes.md#conceptscheme) |

### is in semantic relation with

**IRI:** `http://www.w3.org/2004/02/skos/core#semanticRelation` · `skos:semanticRelation`

Links a concept to a concept related by meaning.

| | |
|---|---|
| Sub-properties | [has broader transitive](object-properties.md#broadertransitive), [has narrower transitive](object-properties.md#narrowertransitive), [has related](object-properties.md#related), [is in mapping relation with](object-properties.md#mappingrelation) |
| Domain | [Concept](classes.md#concept) |
| Range | [Concept](classes.md#concept) |

### is top concept in scheme

**IRI:** `http://www.w3.org/2004/02/skos/core#topConceptOf` · `skos:topConceptOf`

Relates a concept to the concept scheme that it is a top level concept of.

| | |
|---|---|
| Super-properties | [is in scheme](object-properties.md#inscheme) |
| Domain | [Concept](classes.md#concept) |
| Range | [Concept Scheme](classes.md#conceptscheme) |
| Inverse of | [has top concept](object-properties.md#hastopconcept) |

