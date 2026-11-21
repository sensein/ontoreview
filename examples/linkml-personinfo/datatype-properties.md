# Datatype properties

### age_in_years

**IRI:** `https://w3id.org/example/personinfo/age_in_years` · `personinfo:age_in_years`

| | |
|---|---|
| Range | [xsd:integer](http://www.w3.org/2001/XMLSchema#integer)[*>=* `0`, *<=* `999`] |
| Used in | used in axioms of [Person](classes.md#person) |
| maximum value (LinkML) | 999 |
| minimum value (LinkML) | 0 |

### aliases

**IRI:** `https://w3id.org/example/personinfo/aliases` · `personinfo:aliases`

| | |
|---|---|
| Range | [xsd:string](http://www.w3.org/2001/XMLSchema#string) |
| Used in | used in axioms of [HasAliases](classes.md#hasaliases) |
| attribute of (LinkML) | personinfo:HasAliases |
| multivalued (LinkML) | true |

### birth_date

**IRI:** `http://schema.org/birthDate` · `schema:birthDate`

| | |
|---|---|
| Range | [xsd:date](http://www.w3.org/2001/XMLSchema#date) |
| Used in | used in axioms of [Person](classes.md#person) |

### description

**IRI:** `http://schema.org/description` · `schema:description`

A human-readable description for a thing.

| | |
|---|---|
| Range | [xsd:string](http://www.w3.org/2001/XMLSchema#string) |
| Used in | used in axioms of [NamedThing](classes.md#namedthing) |

### founding_date

**IRI:** `https://w3id.org/example/personinfo/founding_date` · `personinfo:founding_date`

When the organization was founded.

| | |
|---|---|
| Range | [xsd:date](http://www.w3.org/2001/XMLSchema#date) |
| Used in | used in axioms of [Organization](classes.md#organization) |
| attribute of (LinkML) | personinfo:Organization |

### id

**IRI:** `https://w3id.org/example/personinfo/id` · `personinfo:id`

A unique identifier for a thing.

| | |
|---|---|
| Range | [xsd:anyURI](http://www.w3.org/2001/XMLSchema#anyURI) |
| Characteristics | Functional |
| Used in | used in axioms of [NamedThing](classes.md#namedthing) |
| identifier (LinkML) | true |

### name

**IRI:** `http://schema.org/name` · `schema:name`

A human-readable name for a thing.

| | |
|---|---|
| Range | [xsd:string](http://www.w3.org/2001/XMLSchema#string) |
| Used in | used in axioms of [NamedThing](classes.md#namedthing) |

### primary_email

**IRI:** `http://schema.org/email` · `schema:email`

The main email address of a person.

| | |
|---|---|
| Range | [xsd:string](http://www.w3.org/2001/XMLSchema#string)[*pattern* `"^\S+@[\S+\.]+\S+"`] |
| Used in | used in axioms of [Person](classes.md#person) |
| pattern (LinkML) | ^\S+@[\S+\.]+\S+ |

