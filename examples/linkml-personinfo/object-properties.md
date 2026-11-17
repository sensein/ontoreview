# Object properties

### employed_by ~~deprecated~~

**IRI:** `https://w3id.org/example/personinfo/employed_by` · `personinfo:employed_by`

| | |
|---|---|
| Range | [Organization](classes.md#organization) |
| Inverse of | [employees](object-properties.md#employees) |
| Used in | used in axioms of [Person](classes.md#person) |

### employees

**IRI:** `https://w3id.org/example/personinfo/employees` · `personinfo:employees`

| | |
|---|---|
| Range | [Person](classes.md#person) |
| Inverse of | [employed_by](object-properties.md#employed_by) |
| Used in | used in axioms of [Organization](classes.md#organization) |
| attribute of (LinkML) | personinfo:Organization |
| multivalued (LinkML) | true |

### gender

**IRI:** `https://w3id.org/example/personinfo/gender` · `personinfo:gender`

| | |
|---|---|
| Range | [GenderType](classes.md#gendertype) |
| Used in | used in axioms of [Person](classes.md#person) |

### organizations

**IRI:** `https://w3id.org/example/personinfo/organizations` · `personinfo:organizations`

| | |
|---|---|
| Range | [Organization](classes.md#organization) |
| Used in | used in axioms of [Container](classes.md#container) |
| attribute of (LinkML) | personinfo:Container |
| inlined as list (LinkML) | true |
| multivalued (LinkML) | true |

### persons

**IRI:** `https://w3id.org/example/personinfo/persons` · `personinfo:persons`

| | |
|---|---|
| Range | [Person](classes.md#person) |
| Used in | used in axioms of [Container](classes.md#container) |
| attribute of (LinkML) | personinfo:Container |
| inlined as list (LinkML) | true |
| multivalued (LinkML) | true |

