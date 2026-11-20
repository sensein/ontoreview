# Classes

### farm machine

**IRI:** `http://example.org/toy/Machine` · `ex:Machine`

| | |
|---|---|
| Superclasses | [r:Device](http://example.org/ref/Device) |
| Subclasses | [tractor](classes.md#tractor) |

### measurement

**IRI:** `http://example.org/toy/Measurement` · `ex:Measurement`

An act of determining the value of a quantity.

| | |
|---|---|
| Subclasses | [pH reading](classes.md#phreading) |

### pH reading

**IRI:** `http://example.org/toy/PHReading` · `ex:PHReading`

A soil pH value measured at 20 cm depth with a glass electrode, reported to 0.01 units.

| | |
|---|---|
| Superclasses | [measurement](classes.md#measurement) |
| Subclasses | [soil pH reading](classes.md#soilphreading) |

### process

**IRI:** `http://example.org/toy/Process` · `ex:Process`

Something that happens over time and has participants.

### sensor

**IRI:** `http://example.org/toy/Sensor` · `ex:Sensor`

A device that detects a physical property and produces an output signal.

### soil pH reading

**IRI:** `http://example.org/toy/SoilPHReading` · `ex:SoilPHReading`

| | |
|---|---|
| Superclasses | [pH reading](classes.md#phreading) |

### soil sample

**IRI:** `http://example.org/toy/SoilSample` · `ex:SoilSample`

A sample of topsoil collected for agronomic analysis of a field.

| | |
|---|---|
| hasBroadSynonym | sample |

### tractor

**IRI:** `http://example.org/toy/Tractor` · `ex:Tractor`

| | |
|---|---|
| Superclasses | [farm machine](classes.md#machine) |

