# Datatype properties

### has simple result

**IRI:** `http://www.w3.org/ns/sosa/hasSimpleResult` · `sosa:hasSimpleResult`

The simple value of an Observation or Actuation or act of Sampling.

The simple value of an Observation or Actuation or act of Sampling.

| | |
|---|---|
| Domain | [Observation](classes.md#observation); [Sampling](classes.md#sampling); [Actuation](classes.md#actuation) |
| Examples | `For instance, the values 23 or true.` |
| domainIncludes | sosa:Observation; sosa:Sampling; sosa:Actuation |

### result time

**IRI:** `http://www.w3.org/ns/sosa/resultTime` · `sosa:resultTime`

The result time is the instant of time when the Observation, Actuation or Sampling activity was completed.

The result time is the instant of time when the Observation, Actuation or Sampling activity was completed.

| | |
|---|---|
| Domain | [Sampling](classes.md#sampling); [Actuation](classes.md#actuation); [Observation](classes.md#observation) |
| Range | [xsd:dateTime](http://www.w3.org/2001/XMLSchema#dateTime) |
| domainIncludes | sosa:Sampling; sosa:Actuation; sosa:Observation |

