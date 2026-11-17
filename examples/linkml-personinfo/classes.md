# Classes

### Container

**IRI:** `https://w3id.org/example/personinfo/Container` · `personinfo:Container`

| | |
|---|---|
| Restrictions | [persons](object-properties.md#persons) *only* [Person](classes.md#person); [organizations](object-properties.md#organizations) *only* [Organization](classes.md#organization) |
| tree root (LinkML) | true |

### GenderType

**IRI:** `https://w3id.org/example/personinfo/GenderType` · `personinfo:GenderType`

Gender of a person.

| | |
|---|---|
| Equivalent to | {[nonbinary man](individuals.md#gsso_009254), [nonbinary woman](individuals.md#gsso_009253), [transgender woman](individuals.md#gsso_000384), [cisgender man](individuals.md#cisgender_20man)} |
| Instances | [cisgender man](individuals.md#cisgender_20man), [nonbinary man](individuals.md#gsso_009254), [nonbinary woman](individuals.md#gsso_009253), [transgender woman](individuals.md#gsso_000384) |
| Used in | in range of [gender](object-properties.md#gender); used in axioms of [Person](classes.md#person) |

### HasAliases

**IRI:** `https://w3id.org/example/personinfo/HasAliases` · `personinfo:HasAliases`

A mixin applied to any class that can have aliases.

| | |
|---|---|
| Restrictions | [aliases](datatype-properties.md#aliases) *only* [xsd:string](http://www.w3.org/2001/XMLSchema#string) |
| Subclasses | [Person](classes.md#person) |
| mixin (LinkML) | true |

### NamedThing

**IRI:** `https://w3id.org/example/personinfo/NamedThing` · `personinfo:NamedThing`

A generic grouping for any identifiable entity.

| | |
|---|---|
| Restrictions | [name](datatype-properties.md#name) *max* `1` [xsd:string](http://www.w3.org/2001/XMLSchema#string); [description](datatype-properties.md#description) *max* `1` [xsd:string](http://www.w3.org/2001/XMLSchema#string); [id](datatype-properties.md#id) *exactly* `1` [xsd:anyURI](http://www.w3.org/2001/XMLSchema#anyURI) |
| Subclasses | [Organization](classes.md#organization), [Person](classes.md#person) |
| abstract (LinkML) | true |

### Organization

**IRI:** `https://w3id.org/example/personinfo/Organization` · `personinfo:Organization`

An organization such as a company or university.

| | |
|---|---|
| Superclasses | [NamedThing](classes.md#namedthing) |
| Restrictions | [employees](object-properties.md#employees) *only* [Person](classes.md#person); [founding_date](datatype-properties.md#founding_date) *max* `1` [xsd:date](http://www.w3.org/2001/XMLSchema#date) |
| Used in | in range of [employed_by](object-properties.md#employed_by); in range of [organizations](object-properties.md#organizations); used in axioms of [Container](classes.md#container); used in axioms of [Person](classes.md#person) |

### Person

**IRI:** `http://schema.org/Person` · `schema:Person`

A person (alive, dead, undead, or fictional).

| | |
|---|---|
| Superclasses | [HasAliases](classes.md#hasaliases), [NamedThing](classes.md#namedthing) |
| Restrictions | [primary_email](datatype-properties.md#email) *exactly* `1` [xsd:string](http://www.w3.org/2001/XMLSchema#string)[*pattern* `"^\S+@[\S+\.]+\S+"`]; [employed_by](object-properties.md#employed_by) *max* `1` [Organization](classes.md#organization); [age_in_years](datatype-properties.md#age_in_years) *max* `1` [xsd:integer](http://www.w3.org/2001/XMLSchema#integer)[*>=* `0`, *<=* `999`]; [birth_date](datatype-properties.md#birthdate) *max* `1` [xsd:date](http://www.w3.org/2001/XMLSchema#date); [gender](object-properties.md#gender) *max* `1` [GenderType](classes.md#gendertype) |
| Used in | in range of [employees](object-properties.md#employees); in range of [persons](object-properties.md#persons); used in axioms of [Container](classes.md#container); used in axioms of [Organization](classes.md#organization) |
| Examples | `Ada Lovelace — a famous mathematician` |
| mixins (LinkML) | personinfo:HasAliases |

