# Classes

### Actuatable Property

**IRI:** `http://www.w3.org/ns/sosa/ActuatableProperty` · `sosa:ActuatableProperty`

An actuatable quality (property, characteristic) of a FeatureOfInterest.

An actuatable quality (property, characteristic) of a FeatureOfInterest.

| | |
|---|---|
| Used in | in domain of [is acted on by](object-properties.md#isactedonby); in range of [acts on property](object-properties.md#actsonproperty) |
| Examples | `A window actuator acts by changing the state between a frame and a window. The ability of the window to be opened and closed is its ActuatableProperty.` |

### Actuation

**IRI:** `http://www.w3.org/ns/sosa/Actuation` · `sosa:Actuation`

An Actuation carries out an (Actuation) Procedure to change the state of the world using an Actuator.

An Actuation carries out an (Actuation) Procedure to change the state of the world using an Actuator.

| | |
|---|---|
| Used in | in domain of [acts on property](object-properties.md#actsonproperty); in domain of [has feature of interest](object-properties.md#hasfeatureofinterest); in domain of [has result](object-properties.md#hasresult); in domain of [has simple result](datatype-properties.md#hassimpleresult); in domain of [made by actuator](object-properties.md#madebyactuator); in domain of [phenomenon time](object-properties.md#phenomenontime); in domain of [result time](datatype-properties.md#resulttime); in domain of [used procedure](object-properties.md#usedprocedure); in range of [is acted on by](object-properties.md#isactedonby); in range of [is feature of interest of](object-properties.md#isfeatureofinterestof); in range of [is result of](object-properties.md#isresultof); in range of [made actuation](object-properties.md#madeactuation) |
| Examples | `The activity of automatically closing a window if the temperature in a room drops below 20 degree Celsius. The activity is the Actuation and the device that closes the window is the Actuator. The Procedure is the rule, plan, or specification that defines the conditions that triggers the Actuation, here a drop in temperature. ` |

### Actuator

**IRI:** `http://www.w3.org/ns/sosa/Actuator` · `sosa:Actuator`

A device that is used by, or implements, an (Actuation) Procedure that changes the state of the world.

A device that is used by, or implements, an (Actuation) Procedure that changes the state of the world.

| | |
|---|---|
| Used in | in domain of [is hosted by](object-properties.md#ishostedby); in domain of [made actuation](object-properties.md#madeactuation); in range of [hosts](object-properties.md#hosts); in range of [made by actuator](object-properties.md#madebyactuator) |
| Examples | `A window actuator for automatic window control, i.e., opening or closing the window.` |

### Agent

**IRI:** `http://xmlns.com/foaf/0.1/Agent` · `foaf:Agent`

### Feature Of Interest

**IRI:** `http://www.w3.org/ns/sosa/FeatureOfInterest` · `sosa:FeatureOfInterest`

The thing whose property is being estimated or calculated in the course of an Observation to arrive at a Result or whose property is being manipulated by an Actuator, or which is being sampled or transformed in an act of Sampling.

The thing whose property is being estimated or calculated in the course of an Observation to arrive at a Result or whose property is being manipulated by an Actuator, or which is being sampled or transformed in an act of Sampling.

| | |
|---|---|
| Used in | in domain of [has sample](object-properties.md#hassample); in domain of [is feature of interest of](object-properties.md#isfeatureofinterestof); in range of [has feature of interest](object-properties.md#hasfeatureofinterest); in range of [is sample of](object-properties.md#issampleof) |
| Examples | `When measuring the height of a tree, the height is the observed ObservableProperty, 20m may be the Result of the Observation, and the tree is the FeatureOfInterest. A window is a FeatureOfInterest for an automatic window control Actuator.` |

### Observable Property

**IRI:** `http://www.w3.org/ns/sosa/ObservableProperty` · `sosa:ObservableProperty`

An observable quality (property, characteristic) of a FeatureOfInterest.

An observable quality (property, characteristic) of a FeatureOfInterest.

| | |
|---|---|
| Used in | in domain of [is observed by](object-properties.md#isobservedby); in range of [observed property](object-properties.md#observedproperty); in range of [observes](object-properties.md#observes) |
| Examples | `The height of a tree, the depth of a water body, or the temperature of a surface are examples of observable properties, while the value of a classic car is not (directly) observable but asserted.` |

### Observation

**IRI:** `http://www.w3.org/ns/sosa/Observation` · `sosa:Observation`

Act of carrying out an (Observation) Procedure to estimate or calculate a value of a property of a FeatureOfInterest. Links to a Sensor to describe what made the Observation and how; links to an ObservableProperty to describe what the result is an estimate of, and to a FeatureOfInterest to detail what that property was associated with.

Act of carrying out an (Observation) Procedure to estimate or calculate a value of a property of a FeatureOfInterest. Links to a Sensor to describe what made the Observation and how; links to an ObservableProperty to describe what the result is an estimate of, and to a FeatureOfInterest to detail what that property was associated with.

| | |
|---|---|
| Used in | in domain of [has feature of interest](object-properties.md#hasfeatureofinterest); in domain of [has result](object-properties.md#hasresult); in domain of [has simple result](datatype-properties.md#hassimpleresult); in domain of [made by sensor](object-properties.md#madebysensor); in domain of [observed property](object-properties.md#observedproperty); in domain of [phenomenon time](object-properties.md#phenomenontime); in domain of [result time](datatype-properties.md#resulttime); in domain of [used procedure](object-properties.md#usedprocedure); in range of [is feature of interest of](object-properties.md#isfeatureofinterestof); in range of [is result of](object-properties.md#isresultof); in range of [made observation](object-properties.md#madeobservation) |
| Examples | `The activity of estimating the intensity of an Earthquake using the Mercalli intensity scale is an Observation as is measuring the moment magnitude, i.e., the energy released by said earthquake.` |

### Platform

**IRI:** `http://www.w3.org/ns/sosa/Platform` · `sosa:Platform`

A Platform is an entity that hosts other entities, particularly Sensors, Actuators, Samplers, and other Platforms.

A Platform is an entity that hosts other entities, particularly Sensors, Actuators, Samplers, and other Platforms.

| | |
|---|---|
| Used in | in domain of [hosts](object-properties.md#hosts); in domain of [is hosted by](object-properties.md#ishostedby); in range of [hosts](object-properties.md#hosts); in range of [is hosted by](object-properties.md#ishostedby) |
| Examples | `A post, buoy, vehicle, ship, aircraft, satellite, cell-phone, human or animal may act as platforms for (technical or biological) sensors or actuators.` |

### Procedure

**IRI:** `http://www.w3.org/ns/sosa/Procedure` · `sosa:Procedure`

A workflow, protocol, plan, algorithm, or computational method specifying how to make an Observation, create a Sample, or make a change to the state of the world (via an Actuator). A Procedure is re-usable, and might be involved in many Observations, Samplings, or Actuations. It explains the steps to be carried out to arrive at reproducible results.

A workflow, protocol, plan, algorithm, or computational method specifying how to make an Observation, create a Sample, or make a change to the state of the world (via an Actuator). A Procedure is re-usable, and might be involved in many Observations, Samplings, or Actuations. It explains the steps to be carried out to arrive at reproducible results.

| | |
|---|---|
| Used in | in range of [used procedure](object-properties.md#usedprocedure) |
| Examples | `The measured wind speed differs depending on the height of the sensor above the surface, e.g., due to friction. Consequently, procedures for measuring wind speed define a standard height for anemometers above ground, typically 10m for meteorological measures and 2m in Agrometeorology. This definition of height, sensor placement, and so forth are defined by the Procedure.` |

### Result

**IRI:** `http://www.w3.org/ns/sosa/Result` · `sosa:Result`

The Result of an Observation, Actuation, or act of Sampling. To store an observation's simple result value one can use the hasSimpleResult property.

The Result of an Observation, Actuation, or act of Sampling. To store an observation's simple result value one can use the hasSimpleResult property.

| | |
|---|---|
| Used in | in domain of [is result of](object-properties.md#isresultof); in range of [has result](object-properties.md#hasresult) |
| Examples | `The value 20 as the height of a certain tree together with the unit, e.g., Meter.` |

### Sample

**IRI:** `http://www.w3.org/ns/sosa/Sample` · `sosa:Sample`

Feature which is intended to be representative of a FeatureOfInterest on which Observations may be made.

Physical samples are sometimes known as 'specimens'.

A Sample is the result from an act of Sampling.

Samples are artifacts of an observational strategy, and have no significant function outside of their role in the observation process. The characteristics of the samples themselves are of little interest, except perhaps to the manager of a sampling campaign.

A Sample is intended to sample some FatureOfInterest, so there is an expectation of at least one isSampleOf property. However, in some cases the identity, and even the exact type, of the sampled feature may not be known when observations are made using the sampling features.

Feature which is intended to be representative of a FeatureOfInterest on which Observations may be made.

| | |
|---|---|
| Used in | in domain of [is feature of interest of](object-properties.md#isfeatureofinterestof); in domain of [is result of](object-properties.md#isresultof); in domain of [is sample of](object-properties.md#issampleof); in range of [has feature of interest](object-properties.md#hasfeatureofinterest); in range of [has result](object-properties.md#hasresult); in range of [has sample](object-properties.md#hassample) |
| Examples | `A statistical sample is often designed to be characteristic of an entire population, so that observations can be made regarding the sample that provide a good estimate of the properties of the population.`; `A 'station' is essentially an identifiable locality where a sensor system or Procedure may be deployed and an observation made. In the context of the observation model, it connotes the 'world in the vicinity of the station', so the observed properties relate to the physical medium at the station, and not to any physical artifact such as a mooring, buoy, benchmark, monument, well, etc.` |

### Sampler

**IRI:** `http://www.w3.org/ns/sosa/Sampler` · `sosa:Sampler`

A device that is used by, or implements, a Sampling Procedure to create or transform one or more samples.

A device that is used by, or implements, a Sampling Procedure to create or transform one or more samples.

| | |
|---|---|
| Used in | in domain of [is hosted by](object-properties.md#ishostedby); in domain of [made sampling](object-properties.md#madesampling); in range of [hosts](object-properties.md#hosts); in range of [made by sampler](object-properties.md#madebysampler) |
| Examples | `A ball mill, diamond drill, hammer, hypodermic syringe and needle, image Sensor or a soil auger can all act as sampling devices (i.e., be Samplers). However, sometimes the distinction between the Sampler and the Sensor is not evident, as they are packaged as a unit. A Sampler need not be a physical device.` |

### Sampling

**IRI:** `http://www.w3.org/ns/sosa/Sampling` · `sosa:Sampling`

An act of Sampling carries out a sampling Procedure to create or transform one or more samples.

An act of Sampling carries out a sampling Procedure to create or transform one or more samples.

| | |
|---|---|
| Used in | in domain of [has feature of interest](object-properties.md#hasfeatureofinterest); in domain of [has result](object-properties.md#hasresult); in domain of [has simple result](datatype-properties.md#hassimpleresult); in domain of [made by sampler](object-properties.md#madebysampler); in domain of [phenomenon time](object-properties.md#phenomenontime); in domain of [result time](datatype-properties.md#resulttime); in domain of [used procedure](object-properties.md#usedprocedure); in range of [is feature of interest of](object-properties.md#isfeatureofinterestof); in range of [is result of](object-properties.md#isresultof); in range of [made sampling](object-properties.md#madesampling) |
| Examples | `Taking a diamond-drill core from a rock outcrop.`; `Splitting a piece of drill-core to create two new samples.`; `Registering an image of the landscape.`; `Digging a pit through a soil sequence.`; `Drilling an observation well.`; `Selecting a subset of a population.`; `Establishing a station for environmental monitoring.`; `Sieving a powder to separate the subset finer than 100-mesh.`; `Crushing a rock sample in a ball mill.`; `Drawing blood from a patient.`; `Dividing a field site into quadrants.` |

### Sensor

**IRI:** `http://www.w3.org/ns/sosa/Sensor` · `sosa:Sensor`

Device, agent (including humans), or software (simulation) involved in, or implementing, a Procedure. Sensors respond to a stimulus, e.g., a change in the environment, or input data composed from the results of prior Observations, and generate a Result. Sensors can be hosted by Platforms.

Device, agent (including humans), or software (simulation) involved in, or implementing, a Procedure. Sensors respond to a stimulus, e.g., a change in the environment, or input data composed from the results of prior Observations, and generate a Result. Sensors can be hosted by Platforms.

| | |
|---|---|
| Used in | in domain of [is hosted by](object-properties.md#ishostedby); in domain of [made observation](object-properties.md#madeobservation); in domain of [observes](object-properties.md#observes); in range of [hosts](object-properties.md#hosts); in range of [is observed by](object-properties.md#isobservedby); in range of [made by sensor](object-properties.md#madebysensor) |
| Examples | `Accelerometers, gyroscopes, barometers, magnetometers, and so forth are Sensors that are typically mounted on a modern smart phone (which acts as Platform). Other examples of sensors include the human eyes.` |

### TemporalEntity

**IRI:** `http://www.w3.org/2006/time#TemporalEntity` · `time:TemporalEntity`

| | |
|---|---|
| Used in | in range of [phenomenon time](object-properties.md#phenomenontime) |

### Vocabulary

**IRI:** `http://purl.org/vocommons/voaf#Vocabulary` · `voaf:Vocabulary`

| | |
|---|---|
| Instances | [Sensor, Observation, Sample, and Actuator (SOSA) Ontology](http://www.w3.org/ns/sosa/) |

