# Classes

### Activity

**IRI:** `http://www.w3.org/ns/prov#Activity` · `prov:Activity`

An activity is something that occurs over a period of time and acts upon or with entities; it may include consuming, processing, transforming, modifying, relocating, using, or generating entities.

| | |
|---|---|
| Disjoint with | [Entity](classes.md#entity) |
| Used in | in domain of [atLocation](object-properties.md#atlocation); in domain of [endedAtTime](datatype-properties.md#endedattime); in domain of [generated](object-properties.md#generated); in domain of [invalidated](object-properties.md#invalidated); in domain of [qualifiedAssociation](object-properties.md#qualifiedassociation); in domain of [qualifiedCommunication](object-properties.md#qualifiedcommunication); in domain of [qualifiedEnd](object-properties.md#qualifiedend); in domain of [qualifiedInfluence](object-properties.md#qualifiedinfluence); in domain of [qualifiedStart](object-properties.md#qualifiedstart); in domain of [qualifiedUsage](object-properties.md#qualifiedusage); in domain of [startedAtTime](datatype-properties.md#startedattime); in domain of [used](object-properties.md#used); in domain of [wasAssociatedWith](object-properties.md#wasassociatedwith); in domain of [wasEndedBy](object-properties.md#wasendedby); in domain of [wasInfluencedBy](object-properties.md#wasinfluencedby); in domain of [wasInformedBy](object-properties.md#wasinformedby); in domain of [wasStartedBy](object-properties.md#wasstartedby); in range of [activity](object-properties.md#activity); in range of [hadActivity](object-properties.md#hadactivity); in range of [wasGeneratedBy](object-properties.md#wasgeneratedby); in range of [wasInfluencedBy](object-properties.md#wasinfluencedby); in range of [wasInformedBy](object-properties.md#wasinformedby); in range of [wasInvalidatedBy](object-properties.md#wasinvalidatedby) |
| category | starting-point |
| component | entities-activities |
| constraints | http://www.w3.org/TR/2013/REC-prov-constraints-20130430/#prov-dm-constraints-fig |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-Activity |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-Activity |

### ActivityInfluence

**IRI:** `http://www.w3.org/ns/prov#ActivityInfluence` · `prov:ActivityInfluence`

It is not recommended that the type ActivityInfluence be asserted without also asserting one of its more specific subclasses.

ActivityInfluence provides additional descriptions of an Activity's binary influence upon any other kind of resource. Instances of ActivityInfluence use the prov:activity property to cite the influencing Activity.

| | |
|---|---|
| Superclasses | [Influence](classes.md#influence) |
| Restrictions | [hadActivity](object-properties.md#hadactivity) *max* `0` |
| Subclasses | [Communication](classes.md#communication), [Generation](classes.md#generation), [Invalidation](classes.md#invalidation) |
| Disjoint with | [EntityInfluence](classes.md#entityinfluence) |
| Used in | in domain of [activity](object-properties.md#activity) |
| category | qualified |
| editorsDefinition | ActivitiyInfluence is the capacity of an activity to have an effect on the character, development, or behavior of another by means of generation, invalidation, communication, or other. |

### Agent

**IRI:** `http://www.w3.org/ns/prov#Agent` · `prov:Agent`

An agent is something that bears some form of responsibility for an activity taking place, for the existence of an entity, or for another agent's activity. 

| | |
|---|---|
| Subclasses | [Organization](classes.md#organization), [Person](classes.md#person), [SoftwareAgent](classes.md#softwareagent) |
| Disjoint with | [InstantaneousEvent](classes.md#instantaneousevent) |
| Used in | in domain of [actedOnBehalfOf](object-properties.md#actedonbehalfof); in domain of [atLocation](object-properties.md#atlocation); in domain of [qualifiedDelegation](object-properties.md#qualifieddelegation); in domain of [qualifiedInfluence](object-properties.md#qualifiedinfluence); in domain of [wasInfluencedBy](object-properties.md#wasinfluencedby); in range of [actedOnBehalfOf](object-properties.md#actedonbehalfof); in range of [agent](object-properties.md#agent); in range of [wasAssociatedWith](object-properties.md#wasassociatedwith); in range of [wasAttributedTo](object-properties.md#wasattributedto); in range of [wasInfluencedBy](object-properties.md#wasinfluencedby) |
| category | starting-point |
| component | agents-responsibility |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-agent |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-Agent |

### AgentInfluence

**IRI:** `http://www.w3.org/ns/prov#AgentInfluence` · `prov:AgentInfluence`

It is not recommended that the type AgentInfluence be asserted without also asserting one of its more specific subclasses.

AgentInfluence provides additional descriptions of an Agent's binary influence upon any other kind of resource. Instances of AgentInfluence use the prov:agent property to cite the influencing Agent.

| | |
|---|---|
| Superclasses | [Influence](classes.md#influence) |
| Subclasses | [Association](classes.md#association), [Attribution](classes.md#attribution), [Delegation](classes.md#delegation) |
| Used in | in domain of [agent](object-properties.md#agent) |
| category | qualified |
| editorsDefinition | AgentInfluence is the capacity of an agent to have an effect on the character, development, or behavior of another by means of attribution, association, delegation, or other. |

### Association

**IRI:** `http://www.w3.org/ns/prov#Association` · `prov:Association`

An activity association is an assignment of responsibility to an agent for an activity, indicating that the agent had a role in the activity. It further allows for a plan to be specified, which is the plan intended by the agent to achieve some goals in the context of this activity.

An instance of prov:Association provides additional descriptions about the binary prov:wasAssociatedWith relation from an prov:Activity to some prov:Agent that had some responsiblity for it. For example, :baking prov:wasAssociatedWith :baker; prov:qualifiedAssociation [ a prov:Association; prov:agent :baker; :foo :bar ].

| | |
|---|---|
| Superclasses | [AgentInfluence](classes.md#agentinfluence) |
| Used in | in domain of [hadPlan](object-properties.md#hadplan); in domain of [hadRole](object-properties.md#hadrole); in range of [qualifiedAssociation](object-properties.md#qualifiedassociation) |
| category | qualified |
| component | agents-responsibility |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-Association |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-Association |
| unqualifiedForm | prov:wasAssociatedWith |

### Attribution

**IRI:** `http://www.w3.org/ns/prov#Attribution` · `prov:Attribution`

Attribution is the ascribing of an entity to an agent.

When an entity e is attributed to agent ag, entity e was generated by some unspecified activity that in turn was associated to agent ag. Thus, this relation is useful when the activity is not known, or irrelevant.

An instance of prov:Attribution provides additional descriptions about the binary prov:wasAttributedTo relation from an prov:Entity to some prov:Agent that had some responsible for it. For example, :cake prov:wasAttributedTo :baker; prov:qualifiedAttribution [ a prov:Attribution; prov:entity :baker; :foo :bar ].

| | |
|---|---|
| Superclasses | [AgentInfluence](classes.md#agentinfluence) |
| Used in | in range of [qualifiedAttribution](object-properties.md#qualifiedattribution) |
| category | qualified |
| component | agents-responsibility |
| constraints | http://www.w3.org/TR/2013/REC-prov-constraints-20130430/#prov-dm-constraints-fig |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-attribution |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-attribution |
| unqualifiedForm | prov:wasAttributedTo |

### Bundle

**IRI:** `http://www.w3.org/ns/prov#Bundle` · `prov:Bundle`

A bundle is a named set of provenance descriptions, and is itself an Entity, so allowing provenance of provenance to be expressed.

Note that there are kinds of bundles (e.g. handwritten letters, audio recordings, etc.) that are not expressed in PROV-O, but can be still be described by PROV-O.

| | |
|---|---|
| Superclasses | [Entity](classes.md#entity) |
| category | expanded |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-bundle-entity |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-bundle-declaration |

### Collection

**IRI:** `http://www.w3.org/ns/prov#Collection` · `prov:Collection`

A collection is an entity that provides a structure to some constituents, which are themselves entities. These constituents are said to be member of the collections.

| | |
|---|---|
| Superclasses | [Entity](classes.md#entity) |
| Subclasses | [EmptyCollection](classes.md#emptycollection) |
| Used in | in domain of [hadMember](object-properties.md#hadmember) |
| category | expanded |
| component | collections |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-collection |

### Communication

**IRI:** `http://www.w3.org/ns/prov#Communication` · `prov:Communication`

Communication is the exchange of an entity by two activities, one activity using the entity generated by the other.

An instance of prov:Communication provides additional descriptions about the binary prov:wasInformedBy relation from an informed prov:Activity to the prov:Activity that informed it. For example, :you_jumping_off_bridge prov:wasInformedBy :everyone_else_jumping_off_bridge; prov:qualifiedCommunication [ a prov:Communication; prov:activity :everyone_else_jumping_off_bridge; :foo :bar ].

| | |
|---|---|
| Superclasses | [ActivityInfluence](classes.md#activityinfluence) |
| Used in | in range of [qualifiedCommunication](object-properties.md#qualifiedcommunication) |
| category | qualified |
| component | entities-activities |
| constraints | http://www.w3.org/TR/2013/REC-prov-constraints-20130430/#prov-dm-constraints-fig |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-Communication |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-wasInformedBy |
| unqualifiedForm | prov:wasInformedBy |

### Delegation

**IRI:** `http://www.w3.org/ns/prov#Delegation` · `prov:Delegation`

Delegation is the assignment of authority and responsibility to an agent (by itself or by another agent) to carry out a specific activity as a delegate or representative, while the agent it acts on behalf of retains some responsibility for the outcome of the delegated work.

For example, a student acted on behalf of his supervisor, who acted on behalf of the department chair, who acted on behalf of the university; all those agents are responsible in some way for the activity that took place but we do not say explicitly who bears responsibility and to what degree.

An instance of prov:Delegation provides additional descriptions about the binary prov:actedOnBehalfOf relation from a performing prov:Agent to some prov:Agent for whom it was performed. For example, :mixing prov:wasAssociatedWith :toddler . :toddler prov:actedOnBehalfOf :mother; prov:qualifiedDelegation [ a prov:Delegation; prov:entity :mother; :foo :bar ].

| | |
|---|---|
| Superclasses | [AgentInfluence](classes.md#agentinfluence) |
| Used in | in domain of [hadActivity](object-properties.md#hadactivity); in range of [qualifiedDelegation](object-properties.md#qualifieddelegation) |
| category | qualified |
| component | agents-responsibility |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-delegation |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-delegation |
| unqualifiedForm | prov:actedOnBehalfOf |

### Derivation

**IRI:** `http://www.w3.org/ns/prov#Derivation` · `prov:Derivation`

A derivation is a transformation of an entity into another, an update of an entity resulting in a new one, or the construction of a new entity based on a pre-existing entity.

An instance of prov:Derivation provides additional descriptions about the binary prov:wasDerivedFrom relation from some derived prov:Entity to another prov:Entity from which it was derived. For example, :chewed_bubble_gum prov:wasDerivedFrom :unwrapped_bubble_gum; prov:qualifiedDerivation [ a prov:Derivation; prov:entity :unwrapped_bubble_gum; :foo :bar ].

The more specific forms of prov:Derivation (i.e., prov:Revision, prov:Quotation, prov:PrimarySource) should be asserted if they apply.

| | |
|---|---|
| Superclasses | [EntityInfluence](classes.md#entityinfluence) |
| Subclasses | [PrimarySource](classes.md#primarysource), [Quotation](classes.md#quotation), [Revision](classes.md#revision) |
| Used in | in domain of [hadActivity](object-properties.md#hadactivity); in domain of [hadGeneration](object-properties.md#hadgeneration); in domain of [hadUsage](object-properties.md#hadusage); in range of [qualifiedDerivation](object-properties.md#qualifiedderivation) |
| category | qualified |
| component | derivations |
| constraints | http://www.w3.org/TR/2013/REC-prov-constraints-20130430/#prov-dm-constraints-fig |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-Derivation |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#Derivation-Relation |
| unqualifiedForm | prov:wasDerivedFrom |

### EmptyCollection

**IRI:** `http://www.w3.org/ns/prov#EmptyCollection` · `prov:EmptyCollection`

An empty collection is a collection without members.

| | |
|---|---|
| Superclasses | [Collection](classes.md#collection) |
| category | expanded |
| component | collections |

### End

**IRI:** `http://www.w3.org/ns/prov#End` · `prov:End`

End is when an activity is deemed to have been ended by an entity, known as trigger. The activity no longer exists after its end. Any usage, generation, or invalidation involving an activity precedes the activity's end. An end may refer to a trigger entity that terminated the activity, or to an activity, known as ender that generated the trigger.

An instance of prov:End provides additional descriptions about the binary prov:wasEndedBy relation from some ended prov:Activity to an prov:Entity that ended it. For example, :ball_game prov:wasEndedBy :buzzer; prov:qualifiedEnd [ a prov:End; prov:entity :buzzer; :foo :bar; prov:atTime '2012-03-09T08:05:08-05:00'^^xsd:dateTime ].

| | |
|---|---|
| Superclasses | [EntityInfluence](classes.md#entityinfluence), [InstantaneousEvent](classes.md#instantaneousevent) |
| Used in | in domain of [hadActivity](object-properties.md#hadactivity); in range of [qualifiedEnd](object-properties.md#qualifiedend) |
| category | qualified |
| component | entities-activities |
| constraints | http://www.w3.org/TR/2013/REC-prov-constraints-20130430/#prov-dm-constraints-fig |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-End |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-End |
| unqualifiedForm | prov:wasEndedBy |

### Entity

**IRI:** `http://www.w3.org/ns/prov#Entity` · `prov:Entity`

An entity is a physical, digital, conceptual, or other kind of thing with some fixed aspects; entities may be real or imaginary. 

| | |
|---|---|
| Subclasses | [Bundle](classes.md#bundle), [Collection](classes.md#collection), [Plan](classes.md#plan) |
| Disjoint with | [Activity](classes.md#activity), [InstantaneousEvent](classes.md#instantaneousevent) |
| Used in | in domain of [alternateOf](object-properties.md#alternateof); in domain of [atLocation](object-properties.md#atlocation); in domain of [generatedAtTime](datatype-properties.md#generatedattime); in domain of [hadPrimarySource](object-properties.md#hadprimarysource); in domain of [invalidatedAtTime](datatype-properties.md#invalidatedattime); in domain of [qualifiedAttribution](object-properties.md#qualifiedattribution); in domain of [qualifiedDerivation](object-properties.md#qualifiedderivation); in domain of [qualifiedGeneration](object-properties.md#qualifiedgeneration); in domain of [qualifiedInfluence](object-properties.md#qualifiedinfluence); in domain of [qualifiedInvalidation](object-properties.md#qualifiedinvalidation); in domain of [qualifiedPrimarySource](object-properties.md#qualifiedprimarysource); in domain of [qualifiedQuotation](object-properties.md#qualifiedquotation); in domain of [qualifiedRevision](object-properties.md#qualifiedrevision); in domain of [specializationOf](object-properties.md#specializationof); in domain of [value](datatype-properties.md#value); in domain of [wasAttributedTo](object-properties.md#wasattributedto); in domain of [wasDerivedFrom](object-properties.md#wasderivedfrom); in domain of [wasGeneratedBy](object-properties.md#wasgeneratedby); in domain of [wasInfluencedBy](object-properties.md#wasinfluencedby); in domain of [wasInvalidatedBy](object-properties.md#wasinvalidatedby); in domain of [wasQuotedFrom](object-properties.md#wasquotedfrom); in domain of [wasRevisionOf](object-properties.md#wasrevisionof); in range of [alternateOf](object-properties.md#alternateof); in range of [entity](object-properties.md#entity); in range of [generated](object-properties.md#generated); in range of [hadMember](object-properties.md#hadmember); in range of [hadPrimarySource](object-properties.md#hadprimarysource); in range of [invalidated](object-properties.md#invalidated); in range of [specializationOf](object-properties.md#specializationof); in range of [used](object-properties.md#used); in range of [wasDerivedFrom](object-properties.md#wasderivedfrom); in range of [wasEndedBy](object-properties.md#wasendedby); in range of [wasInfluencedBy](object-properties.md#wasinfluencedby); in range of [wasQuotedFrom](object-properties.md#wasquotedfrom); in range of [wasRevisionOf](object-properties.md#wasrevisionof); in range of [wasStartedBy](object-properties.md#wasstartedby) |
| category | starting-point |
| component | entities-activities |
| constraints | http://www.w3.org/TR/2013/REC-prov-constraints-20130430/#prov-dm-constraints-fig |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-entity |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-Entity |

### EntityInfluence

**IRI:** `http://www.w3.org/ns/prov#EntityInfluence` · `prov:EntityInfluence`

EntityInfluence provides additional descriptions of an Entity's binary influence upon any other kind of resource. Instances of EntityInfluence use the prov:entity property to cite the influencing Entity.

It is not recommended that the type EntityInfluence be asserted without also asserting one of its more specific subclasses.

| | |
|---|---|
| Superclasses | [Influence](classes.md#influence) |
| Subclasses | [Derivation](classes.md#derivation), [End](classes.md#end), [Start](classes.md#start), [Usage](classes.md#usage) |
| Disjoint with | [ActivityInfluence](classes.md#activityinfluence) |
| Used in | in domain of [entity](object-properties.md#entity) |
| category | qualified |
| editorsDefinition | EntityInfluence is the capacity of an entity to have an effect on the character, development, or behavior of another by means of usage, start, end, derivation, or other.  |

### Generation

**IRI:** `http://www.w3.org/ns/prov#Generation` · `prov:Generation`

Generation is the completion of production of a new entity by an activity. This entity did not exist before generation and becomes available for usage after this generation.

An instance of prov:Generation provides additional descriptions about the binary prov:wasGeneratedBy relation from a generated prov:Entity to the prov:Activity that generated it. For example, :cake prov:wasGeneratedBy :baking; prov:qualifiedGeneration [ a prov:Generation; prov:activity :baking; :foo :bar ].

| | |
|---|---|
| Superclasses | [ActivityInfluence](classes.md#activityinfluence), [InstantaneousEvent](classes.md#instantaneousevent) |
| Used in | in range of [hadGeneration](object-properties.md#hadgeneration); in range of [qualifiedGeneration](object-properties.md#qualifiedgeneration) |
| category | qualified |
| component | entities-activities |
| constraints | http://www.w3.org/TR/2013/REC-prov-constraints-20130430/#prov-dm-constraints-fig |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-Generation |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-Generation |
| unqualifiedForm | prov:wasGeneratedBy |

### Influence

**IRI:** `http://www.w3.org/ns/prov#Influence` · `prov:Influence`

Influence is the capacity of an entity, activity, or agent to have an effect on the character, development, or behavior of another by means of usage, start, end, generation, invalidation, communication, derivation, attribution, association, or delegation.

An instance of prov:Influence provides additional descriptions about the binary prov:wasInfluencedBy relation from some influenced Activity, Entity, or Agent to the influencing Activity, Entity, or Agent. For example, :stomach_ache prov:wasInfluencedBy :spoon; prov:qualifiedInfluence [ a prov:Influence; prov:entity :spoon; :foo :bar ] . Because prov:Influence is a broad relation, the more specific relations (Communication, Delegation, End, etc.) should be used when applicable.

Because prov:Influence is a broad relation, its most specific subclasses (e.g. prov:Communication, prov:Delegation, prov:End, prov:Revision, etc.) should be used when applicable.

| | |
|---|---|
| Subclasses | [ActivityInfluence](classes.md#activityinfluence), [AgentInfluence](classes.md#agentinfluence), [EntityInfluence](classes.md#entityinfluence) |
| Used in | in domain of [hadActivity](object-properties.md#hadactivity); in domain of [hadRole](object-properties.md#hadrole); in domain of [influencer](object-properties.md#influencer); in range of [qualifiedInfluence](object-properties.md#qualifiedinfluence) |
| category | qualified |
| component | derivations |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-influence |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-influence |
| unqualifiedForm | prov:wasInfluencedBy |

### InstantaneousEvent

**IRI:** `http://www.w3.org/ns/prov#InstantaneousEvent` · `prov:InstantaneousEvent`

The PROV data model is implicitly based on a notion of instantaneous events (or just events), that mark transitions in the world. Events include generation, usage, or invalidation of entities, as well as starting or ending of activities. This notion of event is not first-class in the data model, but it is useful for explaining its other concepts and its semantics.

An instantaneous event, or event for short, happens in the world and marks a change in the world, in its activities and in its entities. The term 'event' is commonly used in process algebra with a similar meaning. Events represent communications or interactions; they are assumed to be atomic and instantaneous.

| | |
|---|---|
| Subclasses | [End](classes.md#end), [Generation](classes.md#generation), [Invalidation](classes.md#invalidation), [Start](classes.md#start), [Usage](classes.md#usage) |
| Disjoint with | [Agent](classes.md#agent), [Entity](classes.md#entity) |
| Used in | in domain of [atLocation](object-properties.md#atlocation); in domain of [atTime](datatype-properties.md#attime); in domain of [hadRole](object-properties.md#hadrole) |
| category | qualified |
| component | entities-activities |
| constraints | http://www.w3.org/TR/2013/REC-prov-constraints-20130430/#dfn-event |

### Invalidation

**IRI:** `http://www.w3.org/ns/prov#Invalidation` · `prov:Invalidation`

Invalidation is the start of the destruction, cessation, or expiry of an existing entity by an activity. The entity is no longer available for use (or further invalidation) after invalidation. Any generation or usage of an entity precedes its invalidation.

An instance of prov:Invalidation provides additional descriptions about the binary prov:wasInvalidatedBy relation from an invalidated prov:Entity to the prov:Activity that invalidated it. For example, :uncracked_egg prov:wasInvalidatedBy :baking; prov:qualifiedInvalidation [ a prov:Invalidation; prov:activity :baking; :foo :bar ].

| | |
|---|---|
| Superclasses | [ActivityInfluence](classes.md#activityinfluence), [InstantaneousEvent](classes.md#instantaneousevent) |
| Used in | in range of [qualifiedInvalidation](object-properties.md#qualifiedinvalidation) |
| category | qualified |
| component | entities-activities |
| constraints | http://www.w3.org/TR/2013/REC-prov-constraints-20130430/#prov-dm-constraints-fig |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-Invalidation |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-Invalidation |
| unqualifiedForm | prov:wasInvalidatedBy |

### Location

**IRI:** `http://www.w3.org/ns/prov#Location` · `prov:Location`

A location can be an identifiable geographic place (ISO 19112), but it can also be a non-geographic place such as a directory, row, or column. As such, there are numerous ways in which location can be expressed, such as by a coordinate, address, landmark, and so forth.

| | |
|---|---|
| Used in | in range of [atLocation](object-properties.md#atlocation) |
| category | expanded |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-attribute-location |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-attribute |

### Organization

**IRI:** `http://www.w3.org/ns/prov#Organization` · `prov:Organization`

An organization is a social or legal institution such as a company, society, etc.

| | |
|---|---|
| Superclasses | [Agent](classes.md#agent) |
| category | expanded |
| component | agents-responsibility |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-agent |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-types |

### Person

**IRI:** `http://www.w3.org/ns/prov#Person` · `prov:Person`

Person agents are people.

| | |
|---|---|
| Superclasses | [Agent](classes.md#agent) |
| category | expanded |
| component | agents-responsibility |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-agent |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-types |

### Plan

**IRI:** `http://www.w3.org/ns/prov#Plan` · `prov:Plan`

A plan is an entity that represents a set of actions or steps intended by one or more agents to achieve some goals.

There exist no prescriptive requirement on the nature of plans, their representation, the actions or steps they consist of, or their intended goals. Since plans may evolve over time, it may become necessary to track their provenance, so plans themselves are entities. Representing the plan explicitly in the provenance can be useful for various tasks: for example, to validate the execution as represented in the provenance record, to manage expectation failures, or to provide explanations.

| | |
|---|---|
| Superclasses | [Entity](classes.md#entity) |
| Used in | in range of [hadPlan](object-properties.md#hadplan) |
| category | expanded; qualified |
| component | agents-responsibility |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-Association |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-Association |

### PrimarySource

**IRI:** `http://www.w3.org/ns/prov#PrimarySource` · `prov:PrimarySource`

A primary source for a topic refers to something produced by some agent with direct experience and knowledge about the topic, at the time of the topic's study, without benefit from hindsight.

Because of the directness of primary sources, they 'speak for themselves' in ways that cannot be captured through the filter of secondary sources. As such, it is important for secondary sources to reference those primary sources from which they were derived, so that their reliability can be investigated.

A primary source relation is a particular case of derivation of secondary materials from their primary sources. It is recognized that the determination of primary sources can be up to interpretation, and should be done according to conventions accepted within the application's domain.

An instance of prov:PrimarySource provides additional descriptions about the binary prov:hadPrimarySource relation from some secondary prov:Entity to an earlier, primary prov:Entity. For example, :blog prov:hadPrimarySource :newsArticle; prov:qualifiedPrimarySource [ a prov:PrimarySource; prov:entity :newsArticle; :foo :bar ] .

| | |
|---|---|
| Superclasses | [Derivation](classes.md#derivation) |
| Used in | in range of [qualifiedPrimarySource](object-properties.md#qualifiedprimarysource) |
| category | qualified |
| component | derivations |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-primary-source |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-original-source |
| unqualifiedForm | prov:hadPrimarySource |

### Quotation

**IRI:** `http://www.w3.org/ns/prov#Quotation` · `prov:Quotation`

A quotation is the repeat of (some or all of) an entity, such as text or image, by someone who may or may not be its original author. Quotation is a particular case of derivation.

An instance of prov:Quotation provides additional descriptions about the binary prov:wasQuotedFrom relation from some taken prov:Entity from an earlier, larger prov:Entity. For example, :here_is_looking_at_you_kid prov:wasQuotedFrom :casablanca_script; prov:qualifiedQuotation [ a prov:Quotation; prov:entity :casablanca_script; :foo :bar ].

| | |
|---|---|
| Superclasses | [Derivation](classes.md#derivation) |
| Used in | in range of [qualifiedQuotation](object-properties.md#qualifiedquotation) |
| category | qualified |
| component | derivations |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-quotation |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-quotation |
| unqualifiedForm | prov:wasQuotedFrom |

### Revision

**IRI:** `http://www.w3.org/ns/prov#Revision` · `prov:Revision`

A revision is a derivation for which the resulting entity is a revised version of some original. The implication here is that the resulting entity contains substantial content from the original. Revision is a particular case of derivation.

An instance of prov:Revision provides additional descriptions about the binary prov:wasRevisionOf relation from some newer prov:Entity to an earlier prov:Entity. For example, :draft_2 prov:wasRevisionOf :draft_1; prov:qualifiedRevision [ a prov:Revision; prov:entity :draft_1; :foo :bar ].

| | |
|---|---|
| Superclasses | [Derivation](classes.md#derivation) |
| Used in | in range of [qualifiedRevision](object-properties.md#qualifiedrevision) |
| category | qualified |
| component | derivations |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-revision |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-Revision |
| unqualifiedForm | prov:wasRevisionOf |

### Role

**IRI:** `http://www.w3.org/ns/prov#Role` · `prov:Role`

A role is the function of an entity or agent with respect to an activity, in the context of a usage, generation, invalidation, association, start, and end.

| | |
|---|---|
| Used in | in range of [hadRole](object-properties.md#hadrole) |
| category | qualified |
| component | agents-responsibility |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-attribute-role |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-attribute |

### SoftwareAgent

**IRI:** `http://www.w3.org/ns/prov#SoftwareAgent` · `prov:SoftwareAgent`

A software agent is running software.

| | |
|---|---|
| Superclasses | [Agent](classes.md#agent) |
| category | expanded |
| component | agents-responsibility |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-agent |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-types |

### Start

**IRI:** `http://www.w3.org/ns/prov#Start` · `prov:Start`

Start is when an activity is deemed to have been started by an entity, known as trigger. The activity did not exist before its start. Any usage, generation, or invalidation involving an activity follows the activity's start. A start may refer to a trigger entity that set off the activity, or to an activity, known as starter, that generated the trigger.

An instance of prov:Start provides additional descriptions about the binary prov:wasStartedBy relation from some started prov:Activity to an prov:Entity that started it. For example, :foot_race prov:wasStartedBy :bang; prov:qualifiedStart [ a prov:Start; prov:entity :bang; :foo :bar; prov:atTime '2012-03-09T08:05:08-05:00'^^xsd:dateTime ] .

| | |
|---|---|
| Superclasses | [EntityInfluence](classes.md#entityinfluence), [InstantaneousEvent](classes.md#instantaneousevent) |
| Used in | in domain of [hadActivity](object-properties.md#hadactivity); in range of [qualifiedStart](object-properties.md#qualifiedstart) |
| category | qualified |
| component | entities-activities |
| constraints | http://www.w3.org/TR/2013/REC-prov-constraints-20130430/#prov-dm-constraints-fig |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-Start |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-Start |
| unqualifiedForm | prov:wasStartedBy |

### Usage

**IRI:** `http://www.w3.org/ns/prov#Usage` · `prov:Usage`

Usage is the beginning of utilizing an entity by an activity. Before usage, the activity had not begun to utilize this entity and could not have been affected by the entity.

An instance of prov:Usage provides additional descriptions about the binary prov:used relation from some prov:Activity to an prov:Entity that it used. For example, :keynote prov:used :podium; prov:qualifiedUsage [ a prov:Usage; prov:entity :podium; :foo :bar ].

| | |
|---|---|
| Superclasses | [EntityInfluence](classes.md#entityinfluence), [InstantaneousEvent](classes.md#instantaneousevent) |
| Used in | in range of [hadUsage](object-properties.md#hadusage); in range of [qualifiedUsage](object-properties.md#qualifiedusage) |
| category | qualified |
| component | entities-activities |
| constraints | http://www.w3.org/TR/2013/REC-prov-constraints-20130430/#prov-dm-constraints-fig |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-Usage |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-Usage |
| unqualifiedForm | prov:used |

