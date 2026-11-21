# Object properties

### acts on property

**IRI:** `http://www.w3.org/ns/sosa/actsOnProperty` · `sosa:actsOnProperty`

Relation between an Actuation and the property of a FeatureOfInterest it is acting upon.

Relation between an Actuation and the property of a FeatureOfInterest it is acting upon.

| | |
|---|---|
| Domain | [Actuation](classes.md#actuation) |
| Range | [Actuatable Property](classes.md#actuatableproperty) |
| Inverse of | [is acted on by](object-properties.md#isactedonby) |
| Examples | `In the activity (Actuation) of automatically closing a window if the temperature in a room drops below 20 degrees Celsius, the property on which the Actuator acts upon is the state of the window as it changes from being open to being closed. ` |
| domainIncludes | sosa:Actuation |
| rangeIncludes | sosa:ActuatableProperty |

### has feature of interest

**IRI:** `http://www.w3.org/ns/sosa/hasFeatureOfInterest` · `sosa:hasFeatureOfInterest`

A relation between an Observation and the entity whose quality was observed, or between an Actuation and the entity whose property was modified, or between an act of Sampling and the entity that was sampled.

A relation between an Observation and the entity whose quality was observed, or between an Actuation and the entity whose property was modified, or between an act of Sampling and the entity that was sampled.

| | |
|---|---|
| Domain | [Sampling](classes.md#sampling); [Actuation](classes.md#actuation); [Observation](classes.md#observation) |
| Range | [Feature Of Interest](classes.md#featureofinterest); [Sample](classes.md#sample) |
| Inverse of | [is feature of interest of](object-properties.md#isfeatureofinterestof) |
| Examples | `For example, in an Observation of the weight of a person, the FeatureOfInterest is the person and the property is its weight.` |
| domainIncludes | sosa:Sampling; sosa:Actuation; sosa:Observation |
| rangeIncludes | sosa:FeatureOfInterest; sosa:Sample |

### has result

**IRI:** `http://www.w3.org/ns/sosa/hasResult` · `sosa:hasResult`

Relation linking an Observation or Actuation or act of Sampling and a Result or Sample.

Relation linking an Observation or Actuation or act of Sampling and a Result or Sample.

| | |
|---|---|
| Domain | [Sampling](classes.md#sampling); [Actuation](classes.md#actuation); [Observation](classes.md#observation) |
| Range | [Sample](classes.md#sample); [Result](classes.md#result) |
| Inverse of | [is result of](object-properties.md#isresultof) |
| domainIncludes | sosa:Sampling; sosa:Actuation; sosa:Observation |
| rangeIncludes | sosa:Sample; sosa:Result |

### has sample

**IRI:** `http://www.w3.org/ns/sosa/hasSample` · `sosa:hasSample`

Relation between a FeatureOfInterest and the Sample used to represent it.

Relation between a FeatureOfInterest and the Sample used to represent it.

| | |
|---|---|
| Domain | [Feature Of Interest](classes.md#featureofinterest) |
| Range | [Sample](classes.md#sample) |
| Inverse of | [is sample of](object-properties.md#issampleof) |
| domainIncludes | sosa:FeatureOfInterest |
| rangeIncludes | sosa:Sample |

### hosts

**IRI:** `http://www.w3.org/ns/sosa/hosts` · `sosa:hosts`

Relation between a Platform and a Sensor, Actuator, Sampler, or Platform, hosted or mounted on it.

Relation between a Platform and a Sensor, Actuator, Sampler, or Platform, hosted or mounted on it.

| | |
|---|---|
| Domain | [Platform](classes.md#platform) |
| Range | [Actuator](classes.md#actuator); [Platform](classes.md#platform); [Sampler](classes.md#sampler); [Sensor](classes.md#sensor) |
| Inverse of | [is hosted by](object-properties.md#ishostedby) |
| domainIncludes | sosa:Platform |
| rangeIncludes | sosa:Actuator; sosa:Platform; sosa:Sampler; sosa:Sensor |

### is acted on by

**IRI:** `http://www.w3.org/ns/sosa/isActedOnBy` · `sosa:isActedOnBy`

Relation between an ActuatableProperty of a FeatureOfInterest and an Actuation changing its state.

Relation between an ActuatableProperty of a FeatureOfInterest and an Actuation changing its state.

| | |
|---|---|
| Domain | [Actuatable Property](classes.md#actuatableproperty) |
| Range | [Actuation](classes.md#actuation) |
| Inverse of | [acts on property](object-properties.md#actsonproperty) |
| Examples | `In the activity (Actuation) of automatically closing a window if the temperature in a room drops below 20 degrees Celsius, the property on which the Actuator acts upon is the state of the window as it changes from being open to being closed. ` |
| domainIncludes | sosa:ActuatableProperty |
| rangeIncludes | sosa:Actuation |

### is feature of interest of

**IRI:** `http://www.w3.org/ns/sosa/isFeatureOfInterestOf` · `sosa:isFeatureOfInterestOf`

A relation between a FeatureOfInterest and an Observation about it, an Actuation acting on it, or an act of Sampling that sampled it.

A relation between a FeatureOfInterest and an Observation about it, an Actuation acting on it, or an act of Sampling that sampled it.

| | |
|---|---|
| Domain | [Sample](classes.md#sample); [Feature Of Interest](classes.md#featureofinterest) |
| Range | [Sampling](classes.md#sampling); [Actuation](classes.md#actuation); [Observation](classes.md#observation) |
| Inverse of | [has feature of interest](object-properties.md#hasfeatureofinterest) |
| domainIncludes | sosa:Sample; sosa:FeatureOfInterest |
| rangeIncludes | sosa:Sampling; sosa:Actuation; sosa:Observation |

### is hosted by

**IRI:** `http://www.w3.org/ns/sosa/isHostedBy` · `sosa:isHostedBy`

Relation between a Sensor, Actuator, Sampler, or Platform, and the Platform that it is mounted on or hosted by.

Relation between a Sensor, Actuator, Sampler, or Platform, and the Platform that it is mounted on or hosted by.

| | |
|---|---|
| Domain | [Platform](classes.md#platform); [Sampler](classes.md#sampler); [Sensor](classes.md#sensor); [Actuator](classes.md#actuator) |
| Range | [Platform](classes.md#platform) |
| Inverse of | [hosts](object-properties.md#hosts) |
| domainIncludes | sosa:Platform; sosa:Sampler; sosa:Sensor; sosa:Actuator |
| rangeIncludes | sosa:Platform |

### is observed by

**IRI:** `http://www.w3.org/ns/sosa/isObservedBy` · `sosa:isObservedBy`

Relation between an ObservableProperty and the Sensor able to observe it.

Relation between an ObservableProperty and the Sensor able to observe it.

| | |
|---|---|
| Domain | [Observable Property](classes.md#observableproperty) |
| Range | [Sensor](classes.md#sensor) |
| Inverse of | [observes](object-properties.md#observes) |
| domainIncludes | sosa:ObservableProperty |
| rangeIncludes | sosa:Sensor |

### is result of

**IRI:** `http://www.w3.org/ns/sosa/isResultOf` · `sosa:isResultOf`

Relation linking a Result to the Observation or Actuation or act of Sampling that created or caused it.

Relation linking a Result to the Observation or Actuation or act of Sampling that created or caused it.

| | |
|---|---|
| Domain | [Sample](classes.md#sample); [Result](classes.md#result) |
| Range | [Sampling](classes.md#sampling); [Actuation](classes.md#actuation); [Observation](classes.md#observation) |
| Inverse of | [has result](object-properties.md#hasresult) |
| domainIncludes | sosa:Sample; sosa:Result |
| rangeIncludes | sosa:Sampling; sosa:Actuation; sosa:Observation |

### is sample of

**IRI:** `http://www.w3.org/ns/sosa/isSampleOf` · `sosa:isSampleOf`

Relation from a Sample to the FeatureOfInterest that it is intended to be representative of.

Relation from a Sample to the FeatureOfInterest that it is intended to be representative of.

| | |
|---|---|
| Domain | [Sample](classes.md#sample) |
| Range | [Feature Of Interest](classes.md#featureofinterest) |
| Inverse of | [has sample](object-properties.md#hassample) |
| domainIncludes | sosa:Sample |
| rangeIncludes | sosa:FeatureOfInterest |

### made actuation

**IRI:** `http://www.w3.org/ns/sosa/madeActuation` · `sosa:madeActuation`

Relation between an Actuator and the Actuation it has made.

Relation between an Actuator and the Actuation it has made.

| | |
|---|---|
| Domain | [Actuator](classes.md#actuator) |
| Range | [Actuation](classes.md#actuation) |
| Inverse of | [made by actuator](object-properties.md#madebyactuator) |
| domainIncludes | sosa:Actuator |
| rangeIncludes | sosa:Actuation |

### made by actuator

**IRI:** `http://www.w3.org/ns/sosa/madeByActuator` · `sosa:madeByActuator`

Relation linking an Actuation to the Actuator that made that Actuation.

Relation linking an Actuation to the Actuator that made that Actuation.

| | |
|---|---|
| Domain | [Actuation](classes.md#actuation) |
| Range | [Actuator](classes.md#actuator) |
| Inverse of | [made actuation](object-properties.md#madeactuation) |
| domainIncludes | sosa:Actuation |
| rangeIncludes | sosa:Actuator |

### made by sampler

**IRI:** `http://www.w3.org/ns/sosa/madeBySampler` · `sosa:madeBySampler`

Relation linking an act of Sampling to the Sampler (sampling device or entity) that made it.

Relation linking an act of Sampling to the Sampler (sampling device or entity) that made it.

| | |
|---|---|
| Domain | [Sampling](classes.md#sampling) |
| Range | [Sampler](classes.md#sampler) |
| Inverse of | [made sampling](object-properties.md#madesampling) |
| domainIncludes | sosa:Sampling |
| rangeIncludes | sosa:Sampler |

### made by sensor

**IRI:** `http://www.w3.org/ns/sosa/madeBySensor` · `sosa:madeBySensor`

Relation between an Observation and the Sensor which made the Observation.

Relation between an Observation and the Sensor which made the Observation.

| | |
|---|---|
| Domain | [Observation](classes.md#observation) |
| Range | [Sensor](classes.md#sensor) |
| Inverse of | [made observation](object-properties.md#madeobservation) |
| domainIncludes | sosa:Observation |
| rangeIncludes | sosa:Sensor |

### made observation

**IRI:** `http://www.w3.org/ns/sosa/madeObservation` · `sosa:madeObservation`

Relation between a Sensor and an Observation made by the Sensor.

Relation between a Sensor and an Observation made by the Sensor.

| | |
|---|---|
| Domain | [Sensor](classes.md#sensor) |
| Range | [Observation](classes.md#observation) |
| Inverse of | [made by sensor](object-properties.md#madebysensor) |
| domainIncludes | sosa:Sensor |
| rangeIncludes | sosa:Observation |

### made sampling

**IRI:** `http://www.w3.org/ns/sosa/madeSampling` · `sosa:madeSampling`

Relation between a Sampler (sampling device or entity) and the Sampling act it performed.

Relation between a Sampler (sampling device or entity) and the Sampling act it performed.

| | |
|---|---|
| Domain | [Sampler](classes.md#sampler) |
| Range | [Sampling](classes.md#sampling) |
| Inverse of | [made by sampler](object-properties.md#madebysampler) |
| domainIncludes | sosa:Sampler |
| rangeIncludes | sosa:Sampling |

### observed property

**IRI:** `http://www.w3.org/ns/sosa/observedProperty` · `sosa:observedProperty`

Relation linking an Observation to the property that was observed. The ObservableProperty should be a property of the FeatureOfInterest (linked by hasFeatureOfInterest) of this Observation.

Relation linking an Observation to the property that was observed. The ObservableProperty should be a property of the FeatureOfInterest (linked by hasFeatureOfInterest) of this Observation.

| | |
|---|---|
| Domain | [Observation](classes.md#observation) |
| Range | [Observable Property](classes.md#observableproperty) |
| domainIncludes | sosa:Observation |
| rangeIncludes | sosa:ObservableProperty |

### observes

**IRI:** `http://www.w3.org/ns/sosa/observes` · `sosa:observes`

Relation between a Sensor and an ObservableProperty that it is capable of sensing.

Relation between a Sensor and an ObservableProperty that it is capable of sensing.

| | |
|---|---|
| Domain | [Sensor](classes.md#sensor) |
| Range | [Observable Property](classes.md#observableproperty) |
| Inverse of | [is observed by](object-properties.md#isobservedby) |
| domainIncludes | sosa:Sensor |
| rangeIncludes | sosa:ObservableProperty |

### phenomenon time

**IRI:** `http://www.w3.org/ns/sosa/phenomenonTime` · `sosa:phenomenonTime`

The time that the Result of an Observation, Actuation or Sampling applies to the FeatureOfInterest. Not necessarily the same as the resultTime. May be an Interval or an Instant, or some other compound TemporalEntity.

The time that the Result of an Observation, Actuation or Sampling applies to the FeatureOfInterest. Not necessarily the same as the resultTime. May be an Interval or an Instant, or some other compound TemporalEntity.

| | |
|---|---|
| Domain | [Sampling](classes.md#sampling); [Actuation](classes.md#actuation); [Observation](classes.md#observation) |
| Range | [TemporalEntity](classes.md#temporalentity) |
| domainIncludes | sosa:Sampling; sosa:Actuation; sosa:Observation |
| rangeIncludes | time:TemporalEntity |

### used procedure

**IRI:** `http://www.w3.org/ns/sosa/usedProcedure` · `sosa:usedProcedure`

A relation to link to a re-usable Procedure used in making an Observation, an Actuation, or a Sample, typically through a Sensor, Actuator or Sampler.

A relation to link to a re-usable Procedure used in making an Observation, an Actuation, or a Sample, typically through a Sensor, Actuator or Sampler.

| | |
|---|---|
| Domain | [Sampling](classes.md#sampling); [Actuation](classes.md#actuation); [Observation](classes.md#observation) |
| Range | [Procedure](classes.md#procedure) |
| domainIncludes | sosa:Sampling; sosa:Actuation; sosa:Observation |
| rangeIncludes | sosa:Procedure |

