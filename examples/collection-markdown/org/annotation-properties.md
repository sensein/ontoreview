# Annotation properties

### comment

**IRI:** `http://www.w3.org/2000/01/rdf-schema#comment` · `rdfs:comment`

### contributor

**IRI:** `http://purl.org/dc/terms/contributor` · `dct:contributor`

### created

**IRI:** `http://purl.org/dc/terms/created` · `dct:created`

### isDefinedBy

**IRI:** `http://www.w3.org/2000/01/rdf-schema#isDefinedBy` · `rdfs:isDefinedBy`

### label

**IRI:** `http://www.w3.org/2000/01/rdf-schema#label` · `rdfs:label`

### license

**IRI:** `http://purl.org/dc/terms/license` · `dct:license`

### modified

**IRI:** `http://purl.org/dc/terms/modified` · `dct:modified`

### prefLabel

**IRI:** `http://www.w3.org/2004/02/skos/core#prefLabel` · `skos:prefLabel`

### role (property)

**IRI:** `http://www.w3.org/ns/org#roleProperty` · `org:roleProperty`

This is a metalevel property which is used to annotate an `org:Role` instance with a sub-property of `org:memberOf` that can be used to directly indicate the role for easy of query. The intended semantics is a Membership relation involving the Role implies the existence of a direct property relationship through an inference rule of the form:  `{ [] org:member ?p; org:organization ?o; org:role [org:roleProperty ?r] } -> {?p ?r ?o}`.

| | |
|---|---|
| Domain | [Role](classes.md#role) |
| Range | [rdf:Property](http://www.w3.org/1999/02/22-rdf-syntax-ns#Property) |

### seeAlso

**IRI:** `http://www.w3.org/2000/01/rdf-schema#seeAlso` · `rdfs:seeAlso`

### title

**IRI:** `http://purl.org/dc/terms/title` · `dct:title`

### versionInfo

**IRI:** `http://www.w3.org/2002/07/owl#versionInfo` · `owl:versionInfo`

