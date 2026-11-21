# Datatype properties

### identifier

**IRI:** `http://www.w3.org/ns/org#identifier` · `org:identifier`

Gives an identifier, such as a company registration number, that can be used to used to uniquely identify the organization. Many different national and international identier schemes are available. The org ontology is neutral to which schemes are used. The particular identifier scheme should be indicated by the datatype of the identifier value.  Using datatypes to distinguish the notation scheme used is consistent with recommended best practice for `skos:notation` of which this property is a specialization.

| | |
|---|---|
| Super-properties | [skos:notation](http://www.w3.org/2004/02/skos/core#notation) |
| Domain | [Organization](classes.md#organization) |

### location

**IRI:** `http://www.w3.org/ns/org#location` · `org:location`

Gives a location description for a person within the organization, for example a _Mail Stop_ for internal posting purposes.

| | |
|---|---|
| Domain | [foaf:Person](http://xmlns.com/foaf/0.1/Person) |
| Range | [xsd:string](http://www.w3.org/2001/XMLSchema#string) |

