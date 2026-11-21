# Datatype properties

### atTime

**IRI:** `http://www.w3.org/ns/prov#atTime` · `prov:atTime`

The time at which an InstantaneousEvent occurred, in the form of xsd:dateTime.

| | |
|---|---|
| Domain | [InstantaneousEvent](classes.md#instantaneousevent) |
| Range | [xsd:dateTime](http://www.w3.org/2001/XMLSchema#dateTime) |
| category | qualified |
| component | entities-activities |
| sharesDefinitionWith | prov:InstantaneousEvent |
| unqualifiedForm | prov:generatedAtTime; prov:startedAtTime; prov:invalidatedAtTime; prov:endedAtTime |

### endedAtTime

**IRI:** `http://www.w3.org/ns/prov#endedAtTime` · `prov:endedAtTime`

The time at which an activity ended. See also prov:startedAtTime.

| | |
|---|---|
| Domain | [Activity](classes.md#activity) |
| Range | [xsd:dateTime](http://www.w3.org/2001/XMLSchema#dateTime) |
| category | starting-point |
| component | entities-activities |
| editorialNote | It is the intent that the property chain holds: (prov:qualifiedEnd o prov:atTime) rdfs:subPropertyOf prov:endedAtTime. |
| qualifiedForm | prov:End; prov:atTime |

### generatedAtTime

**IRI:** `http://www.w3.org/ns/prov#generatedAtTime` · `prov:generatedAtTime`

The time at which an entity was completely created and is available for use.

| | |
|---|---|
| Domain | [Entity](classes.md#entity) |
| Range | [xsd:dateTime](http://www.w3.org/2001/XMLSchema#dateTime) |
| category | expanded |
| component | entities-activities |
| editorialNote | It is the intent that the property chain holds: (prov:qualifiedGeneration o prov:atTime) rdfs:subPropertyOf prov:generatedAtTime. |
| qualifiedForm | prov:Generation; prov:atTime |

### invalidatedAtTime

**IRI:** `http://www.w3.org/ns/prov#invalidatedAtTime` · `prov:invalidatedAtTime`

The time at which an entity was invalidated (i.e., no longer usable).

| | |
|---|---|
| Domain | [Entity](classes.md#entity) |
| Range | [xsd:dateTime](http://www.w3.org/2001/XMLSchema#dateTime) |
| category | expanded |
| component | entities-activities |
| editorialNote | It is the intent that the property chain holds: (prov:qualifiedInvalidation o prov:atTime) rdfs:subPropertyOf prov:invalidatedAtTime. |
| qualifiedForm | prov:Invalidation; prov:atTime |

### startedAtTime

**IRI:** `http://www.w3.org/ns/prov#startedAtTime` · `prov:startedAtTime`

The time at which an activity started. See also prov:endedAtTime.

| | |
|---|---|
| Domain | [Activity](classes.md#activity) |
| Range | [xsd:dateTime](http://www.w3.org/2001/XMLSchema#dateTime) |
| category | starting-point |
| component | entities-activities |
| editorialNote | It is the intent that the property chain holds: (prov:qualifiedStart o prov:atTime) rdfs:subPropertyOf prov:startedAtTime. |
| qualifiedForm | prov:Start; prov:atTime |

### value

**IRI:** `http://www.w3.org/ns/prov#value` · `prov:value`

Provides a value that is a direct representation of an entity.

| | |
|---|---|
| Domain | [Entity](classes.md#entity) |
| category | expanded |
| component | entities-activities |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-attribute-value |
| editorialNote | The editor's definition comes from http://www.w3.org/TR/rdf-primer/#rdfvalue; This property serves the same purpose as rdf:value, but has been reintroduced to avoid some of the definitional ambiguity in the RDF specification (specifically, 'may be used in describing structured values'). |

