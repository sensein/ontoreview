# Annotation properties

### alternative label

**IRI:** `http://www.w3.org/2004/02/skos/core#altLabel` · `skos:altLabel`

An alternative lexical label for a resource.

The range of skos:altLabel is the class of RDF plain literals.

skos:prefLabel, skos:altLabel and skos:hiddenLabel are pairwise disjoint properties.

| | |
|---|---|
| Super-properties | [rdfs:label](http://www.w3.org/2000/01/rdf-schema#label) |
| Examples | `Acronyms, abbreviations, spelling variants, and irregular plural/singular forms may be included among the alternative labels for a concept. Mis-spelled terms are normally included as hidden labels (see skos:hiddenLabel).` |

### change note

**IRI:** `http://www.w3.org/2004/02/skos/core#changeNote` · `skos:changeNote`

A note about a modification to a concept.

| | |
|---|---|
| Super-properties | [note](annotation-properties.md#note) |

### definition

**IRI:** `http://www.w3.org/2004/02/skos/core#definition` · `skos:definition`

A statement or formal explanation of the meaning of a concept.

| | |
|---|---|
| Super-properties | [note](annotation-properties.md#note) |

### editorial note

**IRI:** `http://www.w3.org/2004/02/skos/core#editorialNote` · `skos:editorialNote`

A note for an editor, translator or maintainer of the vocabulary.

| | |
|---|---|
| Super-properties | [note](annotation-properties.md#note) |

### example

**IRI:** `http://www.w3.org/2004/02/skos/core#example` · `skos:example`

An example of the use of a concept.

| | |
|---|---|
| Super-properties | [note](annotation-properties.md#note) |

### hidden label

**IRI:** `http://www.w3.org/2004/02/skos/core#hiddenLabel` · `skos:hiddenLabel`

A lexical label for a resource that should be hidden when generating visual displays of the resource, but should still be accessible to free text search operations.

skos:prefLabel, skos:altLabel and skos:hiddenLabel are pairwise disjoint properties.

The range of skos:hiddenLabel is the class of RDF plain literals.

| | |
|---|---|
| Super-properties | [rdfs:label](http://www.w3.org/2000/01/rdf-schema#label) |

### history note

**IRI:** `http://www.w3.org/2004/02/skos/core#historyNote` · `skos:historyNote`

A note about the past state/use/meaning of a concept.

| | |
|---|---|
| Super-properties | [note](annotation-properties.md#note) |

### note

**IRI:** `http://www.w3.org/2004/02/skos/core#note` · `skos:note`

A general note, for any purpose.

| | |
|---|---|
| Sub-properties | [change note](annotation-properties.md#changenote), [definition](annotation-properties.md#definition), [editorial note](annotation-properties.md#editorialnote), [example](annotation-properties.md#example), [history note](annotation-properties.md#historynote), [scope note](annotation-properties.md#scopenote) |

### preferred label

**IRI:** `http://www.w3.org/2004/02/skos/core#prefLabel` · `skos:prefLabel`

The preferred lexical label for a resource, in a given language.

The range of skos:prefLabel is the class of RDF plain literals.

skos:prefLabel, skos:altLabel and skos:hiddenLabel are pairwise
      disjoint properties.

A resource has no more than one value of skos:prefLabel per language tag, and no more than one value of skos:prefLabel without language tag.

| | |
|---|---|
| Super-properties | [rdfs:label](http://www.w3.org/2000/01/rdf-schema#label) |

### scope note

**IRI:** `http://www.w3.org/2004/02/skos/core#scopeNote` · `skos:scopeNote`

A note that helps to clarify the meaning and/or the use of a concept.

| | |
|---|---|
| Super-properties | [note](annotation-properties.md#note) |

