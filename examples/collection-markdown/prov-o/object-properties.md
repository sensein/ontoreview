# Object properties

### actedOnBehalfOf

**IRI:** `http://www.w3.org/ns/prov#actedOnBehalfOf` · `prov:actedOnBehalfOf`

An object property to express the accountability of an agent towards another agent. The subordinate agent acted on behalf of the responsible agent in an actual activity. 

| | |
|---|---|
| Super-properties | [wasInfluencedBy](object-properties.md#wasinfluencedby) |
| Domain | [Agent](classes.md#agent) |
| Range | [Agent](classes.md#agent) |
| Property chain | [qualifiedDelegation](object-properties.md#qualifieddelegation) *o* [agent](object-properties.md#agent) |
| category | starting-point |
| component | agents-responsibility |
| inverse | hadDelegate |
| qualifiedForm | prov:Delegation; prov:qualifiedDelegation |

### activity

**IRI:** `http://www.w3.org/ns/prov#activity` · `prov:activity`

| | |
|---|---|
| Super-properties | [influencer](object-properties.md#influencer) |
| Domain | [ActivityInfluence](classes.md#activityinfluence) |
| Range | [Activity](classes.md#activity) |
| category | qualified |
| editorialNote | This property behaves in spirit like rdf:object; it references the object of a prov:wasInfluencedBy triple. |
| editorsDefinition | The prov:activity property references an prov:Activity which influenced a resource. This property applies to an prov:ActivityInfluence, which is given by a subproperty of prov:qualifiedInfluence from the influenced prov:Entity, prov:Activity or prov:Agent. |
| inverse | activityOfInfluence |

### agent

**IRI:** `http://www.w3.org/ns/prov#agent` · `prov:agent`

| | |
|---|---|
| Super-properties | [influencer](object-properties.md#influencer) |
| Domain | [AgentInfluence](classes.md#agentinfluence) |
| Range | [Agent](classes.md#agent) |
| category | qualified |
| editorialNote | This property behaves in spirit like rdf:object; it references the object of a prov:wasInfluencedBy triple. |
| editorsDefinition | The prov:agent property references an prov:Agent which influenced a resource. This property applies to an prov:AgentInfluence, which is given by a subproperty of prov:qualifiedInfluence from the influenced prov:Entity, prov:Activity or prov:Agent. |
| inverse | agentOfInfluence |

### alternateOf

**IRI:** `http://www.w3.org/ns/prov#alternateOf` · `prov:alternateOf`

Two alternate entities present aspects of the same thing. These aspects may be the same or different, and the alternate entities may or may not overlap in time.

| | |
|---|---|
| Sub-properties | [specializationOf](object-properties.md#specializationof) |
| Domain | [Entity](classes.md#entity) |
| Range | [Entity](classes.md#entity) |
| category | expanded |
| component | alternate |
| constraints | http://www.w3.org/TR/2013/REC-prov-constraints-20130430/#prov-dm-constraints-fig |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-alternate |
| inverse | alternateOf |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-alternate |

### atLocation

**IRI:** `http://www.w3.org/ns/prov#atLocation` · `prov:atLocation`

The Location of any resource.

This property has multiple RDFS domains to suit multiple OWL Profiles. See <a href="#owl-profile">PROV-O OWL Profile</a>.

| | |
|---|---|
| Domain | [Activity](classes.md#activity) *or* [Agent](classes.md#agent) *or* [Entity](classes.md#entity) *or* [InstantaneousEvent](classes.md#instantaneousevent) |
| Range | [Location](classes.md#location) |
| category | expanded |
| editorialNote | This property is not functional because the many values could be at a variety of granularies (In this building, in this room, in that chair).; The naming of prov:atLocation parallels prov:atTime, and is not named prov:hadLocation to avoid conflicting with the convention that prov:had* properties are used on prov:Influence classes. |
| inverse | locationOf |
| sharesDefinitionWith | prov:Location |

### entity

**IRI:** `http://www.w3.org/ns/prov#entity` · `prov:entity`

| | |
|---|---|
| Super-properties | [influencer](object-properties.md#influencer) |
| Domain | [EntityInfluence](classes.md#entityinfluence) |
| Range | [Entity](classes.md#entity) |
| category | qualified |
| editorialNote | This property behaves in spirit like rdf:object; it references the object of a prov:wasInfluencedBy triple. |
| editorsDefinition | The prov:entity property references an prov:Entity which influenced a resource. This property applies to an prov:EntityInfluence, which is given by a subproperty of prov:qualifiedInfluence from the influenced prov:Entity, prov:Activity or prov:Agent. |
| inverse | entityOfInfluence |

### generated

**IRI:** `http://www.w3.org/ns/prov#generated` · `prov:generated`

| | |
|---|---|
| Super-properties | [influenced](object-properties.md#influenced) |
| Domain | [Activity](classes.md#activity) |
| Range | [Entity](classes.md#entity) |
| Inverse of | [wasGeneratedBy](object-properties.md#wasgeneratedby) |
| category | expanded |
| component | entities-activities |
| editorialNote | prov:generated is one of few inverse property defined, to allow Activity-oriented assertions in addition to Entity-oriented assertions. |
| inverse | wasGeneratedBy |
| sharesDefinitionWith | prov:Generation |

### hadActivity

**IRI:** `http://www.w3.org/ns/prov#hadActivity` · `prov:hadActivity`

The _optional_ Activity of an Influence, which used, generated, invalidated, or was the responsibility of some Entity. This property is _not_ used by ActivityInfluence (use prov:activity instead).

This property has multiple RDFS domains to suit multiple OWL Profiles. See <a href="#owl-profile">PROV-O OWL Profile</a>.

| | |
|---|---|
| Domain | [Delegation](classes.md#delegation) *or* [Derivation](classes.md#derivation) *or* [End](classes.md#end) *or* [Start](classes.md#start); [Influence](classes.md#influence) |
| Range | [Activity](classes.md#activity) |
| Used in | used in axioms of [ActivityInfluence](classes.md#activityinfluence) |
| category | qualified |
| component | derivations |
| editorialNote | The multiple rdfs:domain assertions are intended. One is simpler and works for OWL-RL, the union is more specific but is not recognized by OWL-RL. |
| inverse | wasActivityOfInfluence |
| sharesDefinitionWith | prov:Activity |

### hadGeneration

**IRI:** `http://www.w3.org/ns/prov#hadGeneration` · `prov:hadGeneration`

The _optional_ Generation involved in an Entity's Derivation.

| | |
|---|---|
| Domain | [Derivation](classes.md#derivation) |
| Range | [Generation](classes.md#generation) |
| category | qualified |
| component | derivations |
| inverse | generatedAsDerivation |
| sharesDefinitionWith | prov:Generation |

### hadMember

**IRI:** `http://www.w3.org/ns/prov#hadMember` · `prov:hadMember`

| | |
|---|---|
| Super-properties | [wasInfluencedBy](object-properties.md#wasinfluencedby) |
| Domain | [Collection](classes.md#collection) |
| Range | [Entity](classes.md#entity) |
| category | expanded |
| component | expanded |
| inverse | wasMemberOf |
| sharesDefinitionWith | prov:Collection |

### hadPlan

**IRI:** `http://www.w3.org/ns/prov#hadPlan` · `prov:hadPlan`

The _optional_ Plan adopted by an Agent in Association with some Activity. Plan specifications are out of the scope of this specification.

| | |
|---|---|
| Domain | [Association](classes.md#association) |
| Range | [Plan](classes.md#plan) |
| category | qualified |
| component | agents-responsibility |
| inverse | wasPlanOf |
| sharesDefinitionWith | prov:Plan |

### hadPrimarySource

**IRI:** `http://www.w3.org/ns/prov#hadPrimarySource` · `prov:hadPrimarySource`

| | |
|---|---|
| Super-properties | [wasDerivedFrom](object-properties.md#wasderivedfrom) |
| Domain | [Entity](classes.md#entity) |
| Range | [Entity](classes.md#entity) |
| Property chain | [qualifiedPrimarySource](object-properties.md#qualifiedprimarysource) *o* [entity](object-properties.md#entity) |
| category | expanded |
| component | derivations |
| inverse | wasPrimarySourceOf |
| qualifiedForm | prov:qualifiedPrimarySource; prov:PrimarySource |

### hadRole

**IRI:** `http://www.w3.org/ns/prov#hadRole` · `prov:hadRole`

The _optional_ Role that an Entity assumed in the context of an Activity. For example, :baking prov:used :spoon; prov:qualified [ a prov:Usage; prov:entity :spoon; prov:hadRole roles:mixing_implement ].

This property has multiple RDFS domains to suit multiple OWL Profiles. See <a href="#owl-profile">PROV-O OWL Profile</a>.

| | |
|---|---|
| Domain | [Association](classes.md#association) *or* [InstantaneousEvent](classes.md#instantaneousevent); [Influence](classes.md#influence) |
| Range | [Role](classes.md#role) |
| category | qualified |
| component | agents-responsibility |
| editorsDefinition | prov:hadRole references the Role (i.e. the function of an entity with respect to an activity), in the context of an instantaneous usage, generation, association, start, and end. |
| inverse | wasRoleIn |
| sharesDefinitionWith | prov:Role |

### hadUsage

**IRI:** `http://www.w3.org/ns/prov#hadUsage` · `prov:hadUsage`

The _optional_ Usage involved in an Entity's Derivation.

| | |
|---|---|
| Domain | [Derivation](classes.md#derivation) |
| Range | [Usage](classes.md#usage) |
| category | qualified |
| component | derivations |
| inverse | wasUsedInDerivation |
| sharesDefinitionWith | prov:Usage |

### influenced

**IRI:** `http://www.w3.org/ns/prov#influenced` · `prov:influenced`

| | |
|---|---|
| Sub-properties | [generated](object-properties.md#generated), [invalidated](object-properties.md#invalidated) |
| Inverse of | [wasInfluencedBy](object-properties.md#wasinfluencedby) |
| category | expanded |
| component | agents-responsibility |
| inverse | wasInfluencedBy |
| sharesDefinitionWith | prov:Influence |

### influencer

**IRI:** `http://www.w3.org/ns/prov#influencer` · `prov:influencer`

Subproperties of prov:influencer are used to cite the object of an unqualified PROV-O triple whose predicate is a subproperty of prov:wasInfluencedBy (e.g. prov:used, prov:wasGeneratedBy). prov:influencer is used much like rdf:object is used.

| | |
|---|---|
| Sub-properties | [activity](object-properties.md#activity), [agent](object-properties.md#agent), [entity](object-properties.md#entity) |
| Domain | [Influence](classes.md#influence) |
| Range | [owl:Thing](http://www.w3.org/2002/07/owl#Thing) |
| category | qualified |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-influence |
| editorialNote | This property and its subproperties are used in the same way as the rdf:object property, i.e. to reference the object of an unqualified prov:wasInfluencedBy or prov:influenced triple. |
| editorsDefinition | This property is used as part of the qualified influence pattern. Subclasses of prov:Influence use these subproperties to reference the resource (Entity, Agent, or Activity) whose influence is being qualified. |
| inverse | hadInfluence |

### invalidated

**IRI:** `http://www.w3.org/ns/prov#invalidated` · `prov:invalidated`

| | |
|---|---|
| Super-properties | [influenced](object-properties.md#influenced) |
| Domain | [Activity](classes.md#activity) |
| Range | [Entity](classes.md#entity) |
| Inverse of | [wasInvalidatedBy](object-properties.md#wasinvalidatedby) |
| category | expanded |
| component | entities-activities |
| editorialNote | prov:invalidated is one of few inverse property defined, to allow Activity-oriented assertions in addition to Entity-oriented assertions. |
| inverse | wasInvalidatedBy |
| sharesDefinitionWith | prov:Invalidation |

### qualifiedAssociation

**IRI:** `http://www.w3.org/ns/prov#qualifiedAssociation` · `prov:qualifiedAssociation`

If this Activity prov:wasAssociatedWith Agent :ag, then it can qualify the Association using prov:qualifiedAssociation [ a prov:Association;  prov:agent :ag; :foo :bar ].

| | |
|---|---|
| Super-properties | [qualifiedInfluence](object-properties.md#qualifiedinfluence) |
| Domain | [Activity](classes.md#activity) |
| Range | [Association](classes.md#association) |
| category | qualified |
| component | agents-responsibility |
| inverse | qualifiedAssociationOf |
| sharesDefinitionWith | prov:Association |
| unqualifiedForm | prov:wasAssociatedWith |

### qualifiedAttribution

**IRI:** `http://www.w3.org/ns/prov#qualifiedAttribution` · `prov:qualifiedAttribution`

If this Entity prov:wasAttributedTo Agent :ag, then it can qualify how it was influenced using prov:qualifiedAttribution [ a prov:Attribution;  prov:agent :ag; :foo :bar ].

| | |
|---|---|
| Super-properties | [qualifiedInfluence](object-properties.md#qualifiedinfluence) |
| Domain | [Entity](classes.md#entity) |
| Range | [Attribution](classes.md#attribution) |
| category | qualified |
| component | agents-responsibility |
| inverse | qualifiedAttributionOf |
| sharesDefinitionWith | prov:Attribution |
| unqualifiedForm | prov:wasAttributedTo |

### qualifiedCommunication

**IRI:** `http://www.w3.org/ns/prov#qualifiedCommunication` · `prov:qualifiedCommunication`

If this Activity prov:wasInformedBy Activity :a, then it can qualify how it was influenced using prov:qualifiedCommunication [ a prov:Communication;  prov:activity :a; :foo :bar ].

| | |
|---|---|
| Super-properties | [qualifiedInfluence](object-properties.md#qualifiedinfluence) |
| Domain | [Activity](classes.md#activity) |
| Range | [Communication](classes.md#communication) |
| category | qualified |
| component | entities-activities |
| inverse | qualifiedCommunicationOf |
| qualifiedForm | prov:Communication |
| sharesDefinitionWith | prov:Communication |

### qualifiedDelegation

**IRI:** `http://www.w3.org/ns/prov#qualifiedDelegation` · `prov:qualifiedDelegation`

If this Agent prov:actedOnBehalfOf Agent :ag, then it can qualify how with prov:qualifiedResponsibility [ a prov:Responsibility;  prov:agent :ag; :foo :bar ].

| | |
|---|---|
| Super-properties | [qualifiedInfluence](object-properties.md#qualifiedinfluence) |
| Domain | [Agent](classes.md#agent) |
| Range | [Delegation](classes.md#delegation) |
| category | qualified |
| component | agents-responsibility |
| inverse | qualifiedDelegationOf |
| sharesDefinitionWith | prov:Delegation |
| unqualifiedForm | prov:actedOnBehalfOf |

### qualifiedDerivation

**IRI:** `http://www.w3.org/ns/prov#qualifiedDerivation` · `prov:qualifiedDerivation`

If this Entity prov:wasDerivedFrom Entity :e, then it can qualify how it was derived using prov:qualifiedDerivation [ a prov:Derivation;  prov:entity :e; :foo :bar ].

| | |
|---|---|
| Super-properties | [qualifiedInfluence](object-properties.md#qualifiedinfluence) |
| Domain | [Entity](classes.md#entity) |
| Range | [Derivation](classes.md#derivation) |
| category | qualified |
| component | derivations |
| inverse | qualifiedDerivationOf |
| sharesDefinitionWith | prov:Derivation |
| unqualifiedForm | prov:wasDerivedFrom |

### qualifiedEnd

**IRI:** `http://www.w3.org/ns/prov#qualifiedEnd` · `prov:qualifiedEnd`

If this Activity prov:wasEndedBy Entity :e1, then it can qualify how it was ended using prov:qualifiedEnd [ a prov:End;  prov:entity :e1; :foo :bar ].

| | |
|---|---|
| Super-properties | [qualifiedInfluence](object-properties.md#qualifiedinfluence) |
| Domain | [Activity](classes.md#activity) |
| Range | [End](classes.md#end) |
| category | qualified |
| component | entities-activities |
| inverse | qualifiedEndOf |
| sharesDefinitionWith | prov:End |
| unqualifiedForm | prov:wasEndedBy |

### qualifiedGeneration

**IRI:** `http://www.w3.org/ns/prov#qualifiedGeneration` · `prov:qualifiedGeneration`

If this Activity prov:generated Entity :e, then it can qualify how it performed the Generation using prov:qualifiedGeneration [ a prov:Generation;  prov:entity :e; :foo :bar ].

| | |
|---|---|
| Super-properties | [qualifiedInfluence](object-properties.md#qualifiedinfluence) |
| Domain | [Entity](classes.md#entity) |
| Range | [Generation](classes.md#generation) |
| category | qualified |
| component | entities-activities |
| inverse | qualifiedGenerationOf |
| sharesDefinitionWith | prov:Generation |
| unqualifiedForm | prov:wasGeneratedBy |

### qualifiedInfluence

**IRI:** `http://www.w3.org/ns/prov#qualifiedInfluence` · `prov:qualifiedInfluence`

Because prov:qualifiedInfluence is a broad relation, the more specific relations (qualifiedCommunication, qualifiedDelegation, qualifiedEnd, etc.) should be used when applicable.

| | |
|---|---|
| Sub-properties | [qualifiedAssociation](object-properties.md#qualifiedassociation), [qualifiedAttribution](object-properties.md#qualifiedattribution), [qualifiedCommunication](object-properties.md#qualifiedcommunication), [qualifiedDelegation](object-properties.md#qualifieddelegation), [qualifiedDerivation](object-properties.md#qualifiedderivation), [qualifiedEnd](object-properties.md#qualifiedend), [qualifiedGeneration](object-properties.md#qualifiedgeneration), [qualifiedInvalidation](object-properties.md#qualifiedinvalidation), [qualifiedPrimarySource](object-properties.md#qualifiedprimarysource), [qualifiedQuotation](object-properties.md#qualifiedquotation), [qualifiedRevision](object-properties.md#qualifiedrevision), [qualifiedStart](object-properties.md#qualifiedstart), [qualifiedUsage](object-properties.md#qualifiedusage) |
| Domain | [Activity](classes.md#activity) *or* [Agent](classes.md#agent) *or* [Entity](classes.md#entity) |
| Range | [Influence](classes.md#influence) |
| category | qualified |
| component | derivations |
| inverse | qualifiedInfluenceOf |
| sharesDefinitionWith | prov:Influence |
| unqualifiedForm | prov:wasInfluencedBy |

### qualifiedInvalidation

**IRI:** `http://www.w3.org/ns/prov#qualifiedInvalidation` · `prov:qualifiedInvalidation`

If this Entity prov:wasInvalidatedBy Activity :a, then it can qualify how it was invalidated using prov:qualifiedInvalidation [ a prov:Invalidation;  prov:activity :a; :foo :bar ].

| | |
|---|---|
| Super-properties | [qualifiedInfluence](object-properties.md#qualifiedinfluence) |
| Domain | [Entity](classes.md#entity) |
| Range | [Invalidation](classes.md#invalidation) |
| category | qualified |
| component | entities-activities |
| inverse | qualifiedInvalidationOf |
| sharesDefinitionWith | prov:Invalidation |
| unqualifiedForm | prov:wasInvalidatedBy |

### qualifiedPrimarySource

**IRI:** `http://www.w3.org/ns/prov#qualifiedPrimarySource` · `prov:qualifiedPrimarySource`

If this Entity prov:hadPrimarySource Entity :e, then it can qualify how using prov:qualifiedPrimarySource [ a prov:PrimarySource; prov:entity :e; :foo :bar ].

| | |
|---|---|
| Super-properties | [qualifiedInfluence](object-properties.md#qualifiedinfluence) |
| Domain | [Entity](classes.md#entity) |
| Range | [PrimarySource](classes.md#primarysource) |
| category | qualified |
| component | derivations |
| inverse | qualifiedSourceOf |
| sharesDefinitionWith | prov:PrimarySource |
| unqualifiedForm | prov:hadPrimarySource |

### qualifiedQuotation

**IRI:** `http://www.w3.org/ns/prov#qualifiedQuotation` · `prov:qualifiedQuotation`

If this Entity prov:wasQuotedFrom Entity :e, then it can qualify how using prov:qualifiedQuotation [ a prov:Quotation;  prov:entity :e; :foo :bar ].

| | |
|---|---|
| Super-properties | [qualifiedInfluence](object-properties.md#qualifiedinfluence) |
| Domain | [Entity](classes.md#entity) |
| Range | [Quotation](classes.md#quotation) |
| category | qualified |
| component | derivations |
| inverse | qualifiedQuotationOf |
| sharesDefinitionWith | prov:Quotation |
| unqualifiedForm | prov:wasQuotedFrom |

### qualifiedRevision

**IRI:** `http://www.w3.org/ns/prov#qualifiedRevision` · `prov:qualifiedRevision`

If this Entity prov:wasRevisionOf Entity :e, then it can qualify how it was revised using prov:qualifiedRevision [ a prov:Revision;  prov:entity :e; :foo :bar ].

| | |
|---|---|
| Super-properties | [qualifiedInfluence](object-properties.md#qualifiedinfluence) |
| Domain | [Entity](classes.md#entity) |
| Range | [Revision](classes.md#revision) |
| category | qualified |
| component | derivations |
| inverse | revisedEntity |
| sharesDefinitionWith | prov:Revision |
| unqualifiedForm | prov:wasRevisionOf |

### qualifiedStart

**IRI:** `http://www.w3.org/ns/prov#qualifiedStart` · `prov:qualifiedStart`

If this Activity prov:wasStartedBy Entity :e1, then it can qualify how it was started using prov:qualifiedStart [ a prov:Start;  prov:entity :e1; :foo :bar ].

| | |
|---|---|
| Super-properties | [qualifiedInfluence](object-properties.md#qualifiedinfluence) |
| Domain | [Activity](classes.md#activity) |
| Range | [Start](classes.md#start) |
| category | qualified |
| component | entities-activities |
| inverse | qualifiedStartOf |
| sharesDefinitionWith | prov:Start |
| unqualifiedForm | prov:wasStartedBy |

### qualifiedUsage

**IRI:** `http://www.w3.org/ns/prov#qualifiedUsage` · `prov:qualifiedUsage`

If this Activity prov:used Entity :e, then it can qualify how it used it using prov:qualifiedUsage [ a prov:Usage; prov:entity :e; :foo :bar ].

| | |
|---|---|
| Super-properties | [qualifiedInfluence](object-properties.md#qualifiedinfluence) |
| Domain | [Activity](classes.md#activity) |
| Range | [Usage](classes.md#usage) |
| category | qualified |
| component | entities-activities |
| inverse | qualifiedUsingActivity |
| sharesDefinitionWith | prov:Usage |
| unqualifiedForm | prov:used |

### specializationOf

**IRI:** `http://www.w3.org/ns/prov#specializationOf` · `prov:specializationOf`

An entity that is a specialization of another shares all aspects of the latter, and additionally presents more specific aspects of the same thing as the latter. In particular, the lifetime of the entity being specialized contains that of any specialization. Examples of aspects include a time period, an abstraction, and a context associated with the entity.

| | |
|---|---|
| Super-properties | [alternateOf](object-properties.md#alternateof) |
| Domain | [Entity](classes.md#entity) |
| Range | [Entity](classes.md#entity) |
| category | expanded |
| component | alternate |
| constraints | http://www.w3.org/TR/2013/REC-prov-constraints-20130430/#prov-dm-constraints-fig |
| dm | http://www.w3.org/TR/2013/REC-prov-dm-20130430/#term-specialization |
| inverse | generalizationOf |
| n | http://www.w3.org/TR/2013/REC-prov-n-20130430/#expression-specialization |

### used

**IRI:** `http://www.w3.org/ns/prov#used` · `prov:used`

A prov:Entity that was used by this prov:Activity. For example, :baking prov:used :spoon, :egg, :oven .

| | |
|---|---|
| Super-properties | [wasInfluencedBy](object-properties.md#wasinfluencedby) |
| Domain | [Activity](classes.md#activity) |
| Range | [Entity](classes.md#entity) |
| Property chain | [qualifiedUsage](object-properties.md#qualifiedusage) *o* [entity](object-properties.md#entity) |
| category | starting-point |
| component | entities-activities |
| inverse | wasUsedBy |
| qualifiedForm | prov:qualifiedUsage; prov:Usage |

### wasAssociatedWith

**IRI:** `http://www.w3.org/ns/prov#wasAssociatedWith` · `prov:wasAssociatedWith`

An prov:Agent that had some (unspecified) responsibility for the occurrence of this prov:Activity.

| | |
|---|---|
| Super-properties | [wasInfluencedBy](object-properties.md#wasinfluencedby) |
| Domain | [Activity](classes.md#activity) |
| Range | [Agent](classes.md#agent) |
| Property chain | [qualifiedAssociation](object-properties.md#qualifiedassociation) *o* [agent](object-properties.md#agent) |
| category | starting-point |
| component | agents-responsibility |
| inverse | wasAssociateFor |
| qualifiedForm | prov:qualifiedAssociation; prov:Association |

### wasAttributedTo

**IRI:** `http://www.w3.org/ns/prov#wasAttributedTo` · `prov:wasAttributedTo`

Attribution is the ascribing of an entity to an agent.

Attribution is the ascribing of an entity to an agent.

| | |
|---|---|
| Super-properties | [wasInfluencedBy](object-properties.md#wasinfluencedby) |
| Domain | [Entity](classes.md#entity) |
| Range | [Agent](classes.md#agent) |
| Property chain | [qualifiedAttribution](object-properties.md#qualifiedattribution) *o* [agent](object-properties.md#agent) |
| category | starting-point |
| component | agents-responsibility |
| inverse | contributed |
| qualifiedForm | prov:Attribution; prov:qualifiedAttribution |

### wasDerivedFrom

**IRI:** `http://www.w3.org/ns/prov#wasDerivedFrom` · `prov:wasDerivedFrom`

A derivation is a transformation of an entity into another, an update of an entity resulting in a new one, or the construction of a new entity based on a pre-existing entity.

The more specific subproperties of prov:wasDerivedFrom (i.e., prov:wasQuotedFrom, prov:wasRevisionOf, prov:hadPrimarySource) should be used when applicable.

| | |
|---|---|
| Super-properties | [wasInfluencedBy](object-properties.md#wasinfluencedby) |
| Sub-properties | [hadPrimarySource](object-properties.md#hadprimarysource), [wasQuotedFrom](object-properties.md#wasquotedfrom), [wasRevisionOf](object-properties.md#wasrevisionof) |
| Domain | [Entity](classes.md#entity) |
| Range | [Entity](classes.md#entity) |
| Property chain | [qualifiedDerivation](object-properties.md#qualifiedderivation) *o* [entity](object-properties.md#entity) |
| category | starting-point |
| component | derivations |
| inverse | hadDerivation |
| qualifiedForm | prov:qualifiedDerivation; prov:Derivation |

### wasEndedBy

**IRI:** `http://www.w3.org/ns/prov#wasEndedBy` · `prov:wasEndedBy`

End is when an activity is deemed to have ended. An end may refer to an entity, known as trigger, that terminated the activity.

| | |
|---|---|
| Super-properties | [wasInfluencedBy](object-properties.md#wasinfluencedby) |
| Domain | [Activity](classes.md#activity) |
| Range | [Entity](classes.md#entity) |
| Property chain | [qualifiedEnd](object-properties.md#qualifiedend) *o* [entity](object-properties.md#entity) |
| category | expanded |
| component | entities-activities |
| inverse | ended |
| qualifiedForm | prov:End; prov:qualifiedEnd |

### wasGeneratedBy

**IRI:** `http://www.w3.org/ns/prov#wasGeneratedBy` · `prov:wasGeneratedBy`

| | |
|---|---|
| Super-properties | [wasInfluencedBy](object-properties.md#wasinfluencedby) |
| Domain | [Entity](classes.md#entity) |
| Range | [Activity](classes.md#activity) |
| Inverse of | [generated](object-properties.md#generated) |
| Property chain | [qualifiedGeneration](object-properties.md#qualifiedgeneration) *o* [activity](object-properties.md#activity) |
| category | starting-point |
| component | entities-activities |
| inverse | generated |
| qualifiedForm | prov:Generation; prov:qualifiedGeneration |

### wasInfluencedBy

**IRI:** `http://www.w3.org/ns/prov#wasInfluencedBy` · `prov:wasInfluencedBy`

Because prov:wasInfluencedBy is a broad relation, its more specific subproperties (e.g. prov:wasInformedBy, prov:actedOnBehalfOf, prov:wasEndedBy, etc.) should be used when applicable.

This property has multiple RDFS domains to suit multiple OWL Profiles. See <a href="#owl-profile">PROV-O OWL Profile</a>.

| | |
|---|---|
| Sub-properties | [actedOnBehalfOf](object-properties.md#actedonbehalfof), [hadMember](object-properties.md#hadmember), [used](object-properties.md#used), [wasAssociatedWith](object-properties.md#wasassociatedwith), [wasAttributedTo](object-properties.md#wasattributedto), [wasDerivedFrom](object-properties.md#wasderivedfrom), [wasEndedBy](object-properties.md#wasendedby), [wasGeneratedBy](object-properties.md#wasgeneratedby), [wasInformedBy](object-properties.md#wasinformedby), [wasInvalidatedBy](object-properties.md#wasinvalidatedby), [wasStartedBy](object-properties.md#wasstartedby) |
| Domain | [Activity](classes.md#activity) *or* [Agent](classes.md#agent) *or* [Entity](classes.md#entity) |
| Range | [Activity](classes.md#activity) *or* [Agent](classes.md#agent) *or* [Entity](classes.md#entity) |
| Inverse of | [influenced](object-properties.md#influenced) |
| category | qualified |
| component | agents-responsibility |
| editorialNote | The sub-properties of prov:wasInfluencedBy can be elaborated in more detail using the Qualification Pattern. For example, the binary relation :baking prov:used :spoon can be qualified by asserting :baking prov:qualifiedUsage [ a prov:Usage; prov:entity :spoon; prov:atLocation :kitchen ] .  Subproperties of prov:wasInfluencedBy may also be asserted directly without being qualified.  prov:wasInfluencedBy should not be used without also using one of its subproperties.   |
| inverse | influenced |
| qualifiedForm | prov:qualifiedInfluence; prov:Influence |
| sharesDefinitionWith | prov:Influence |

### wasInformedBy

**IRI:** `http://www.w3.org/ns/prov#wasInformedBy` · `prov:wasInformedBy`

An activity a2 is dependent on or informed by another activity a1, by way of some unspecified entity that is generated by a1 and used by a2.

| | |
|---|---|
| Super-properties | [wasInfluencedBy](object-properties.md#wasinfluencedby) |
| Domain | [Activity](classes.md#activity) |
| Range | [Activity](classes.md#activity) |
| Property chain | [qualifiedCommunication](object-properties.md#qualifiedcommunication) *o* [activity](object-properties.md#activity) |
| category | starting-point |
| component | entities-activities |
| inverse | informed |
| qualifiedForm | prov:qualifiedCommunication; prov:Communication |

### wasInvalidatedBy

**IRI:** `http://www.w3.org/ns/prov#wasInvalidatedBy` · `prov:wasInvalidatedBy`

| | |
|---|---|
| Super-properties | [wasInfluencedBy](object-properties.md#wasinfluencedby) |
| Domain | [Entity](classes.md#entity) |
| Range | [Activity](classes.md#activity) |
| Inverse of | [invalidated](object-properties.md#invalidated) |
| Property chain | [qualifiedInvalidation](object-properties.md#qualifiedinvalidation) *o* [activity](object-properties.md#activity) |
| category | expanded |
| component | entities-activities |
| inverse | invalidated |
| qualifiedForm | prov:qualifiedInvalidation; prov:Invalidation |

### wasQuotedFrom

**IRI:** `http://www.w3.org/ns/prov#wasQuotedFrom` · `prov:wasQuotedFrom`

An entity is derived from an original entity by copying, or 'quoting', some or all of it.

| | |
|---|---|
| Super-properties | [wasDerivedFrom](object-properties.md#wasderivedfrom) |
| Domain | [Entity](classes.md#entity) |
| Range | [Entity](classes.md#entity) |
| Property chain | [qualifiedQuotation](object-properties.md#qualifiedquotation) *o* [entity](object-properties.md#entity) |
| category | expanded |
| component | derivations |
| inverse | quotedAs |
| qualifiedForm | prov:Quotation; prov:qualifiedQuotation |

### wasRevisionOf

**IRI:** `http://www.w3.org/ns/prov#wasRevisionOf` · `prov:wasRevisionOf`

A revision is a derivation that revises an entity into a revised version.

| | |
|---|---|
| Super-properties | [wasDerivedFrom](object-properties.md#wasderivedfrom) |
| Domain | [Entity](classes.md#entity) |
| Range | [Entity](classes.md#entity) |
| Property chain | [qualifiedRevision](object-properties.md#qualifiedrevision) *o* [entity](object-properties.md#entity) |
| category | expanded |
| component | derivations |
| inverse | hadRevision |
| qualifiedForm | prov:qualifiedRevision; prov:Revision |

### wasStartedBy

**IRI:** `http://www.w3.org/ns/prov#wasStartedBy` · `prov:wasStartedBy`

Start is when an activity is deemed to have started. A start may refer to an entity, known as trigger, that initiated the activity.

| | |
|---|---|
| Super-properties | [wasInfluencedBy](object-properties.md#wasinfluencedby) |
| Domain | [Activity](classes.md#activity) |
| Range | [Entity](classes.md#entity) |
| Property chain | [qualifiedStart](object-properties.md#qualifiedstart) *o* [entity](object-properties.md#entity) |
| category | expanded |
| component | entities-activities |
| inverse | started |
| qualifiedForm | prov:qualifiedStart; prov:Start |

