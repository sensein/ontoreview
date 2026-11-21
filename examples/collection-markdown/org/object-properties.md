# Object properties

### based At

**IRI:** `http://www.w3.org/ns/org#basedAt` · `org:basedAt`

Indicates the site at which a person is based. We do not restrict the possibility that a person is based at multiple sites.

| | |
|---|---|
| Domain | [foaf:Person](http://xmlns.com/foaf/0.1/Person) |
| Range | [Site](classes.md#site) |

### changed by

**IRI:** `http://www.w3.org/ns/org#changedBy` · `org:changedBy`

Indicates a change event which resulted in a change to this organization. Depending on the event the organization may or may not have continued to exist after the event. Inverse of `org:originalOrganization`.

| | |
|---|---|
| Domain | [Organization](classes.md#organization) |
| Range | [Change Event](classes.md#changeevent) |
| Inverse of | [original organization](object-properties.md#originalorganization) |

### classification

**IRI:** `http://www.w3.org/ns/org#classification` · `org:classification`

Indicates a classification for this Organization within some classification scheme. Extension vocabularies may wish to specialize this property to have a range corresponding to a specific `skos:ConceptScheme`. This property is under discussion and may be revised or removed - in many cases organizations are best categorized by defining a sub-class hierarchy in an extension vocabulary.

| | |
|---|---|
| Domain | [Organization](classes.md#organization) |
| Range | [skos:Concept](http://www.w3.org/2004/02/skos/core#Concept) |

### has member

**IRI:** `http://www.w3.org/ns/org#hasMember` · `org:hasMember`

Indicates a person who is a member of the subject Organization. Inverse of `org:memberOf`, see that property for further clarification. Provided for compatibility with `foaf:member`.

| | |
|---|---|
| Domain | [Organization](classes.md#organization) |
| Range | [foaf:Agent](http://xmlns.com/foaf/0.1/Agent) |
| Inverse of | [member of](object-properties.md#memberof) |
| Used in | used in axioms of [Endeavour](classes.md#organizationalcollaboration) |

### has site

**IRI:** `http://www.w3.org/ns/org#hasSite` · `org:hasSite`

Indicates a site at which the Organization has some presence even if only indirect (e.g. virtual office or a professional service which is acting as the registered address for a company). Inverse of `org:siteOf`.

| | |
|---|---|
| Sub-properties | [primary Site](object-properties.md#hasprimarysite) |
| Domain | [Organization](classes.md#organization) |
| Range | [Site](classes.md#site) |
| Inverse of | [site Of](object-properties.md#siteof) |

### has SubOrganization

**IRI:** `http://www.w3.org/ns/org#hasSubOrganization` · `org:hasSubOrganization`

Represents hierarchical containment of Organizations or Organizational Units; indicates an organization which is a sub-part or child of this organization.  Inverse of `org:subOrganizationOf`.

| | |
|---|---|
| Sub-properties | [has Unit](object-properties.md#hasunit) |
| Domain | [Organization](classes.md#organization) |
| Range | [Organization](classes.md#organization) |
| Inverse of | [subOrganization of](object-properties.md#suborganizationof) |

### has Unit

**IRI:** `http://www.w3.org/ns/org#hasUnit` · `org:hasUnit`

Indicates a unit which is part of this Organization, e.g. a Department within a larger FormalOrganization. Inverse of `org:unitOf`.

| | |
|---|---|
| Super-properties | [has SubOrganization](object-properties.md#hassuborganization) |
| Domain | [Formal Organization](classes.md#formalorganization) |
| Range | [OrganizationalUnit](classes.md#organizationalunit) |
| Inverse of | [unit Of](object-properties.md#unitof) |

### head of

**IRI:** `http://www.w3.org/ns/org#headOf` · `org:headOf`

Indicates that a person is the leader or formal head of the Organization. This will normally mean that they are the root of the `org:reportsTo` (acyclic) graph, though an organization may have more than one head.

| | |
|---|---|
| Super-properties | [member of](object-properties.md#memberof) |
| Domain | [foaf:Agent](http://xmlns.com/foaf/0.1/Agent) |
| Range | [Organization](classes.md#organization) |

### held by

**IRI:** `http://www.w3.org/ns/org#heldBy` · `org:heldBy`

Indicates an Agent which holds a Post.

| | |
|---|---|
| Domain | [Post](classes.md#post) |
| Range | [foaf:Agent](http://xmlns.com/foaf/0.1/Agent) |
| Inverse of | [holds](object-properties.md#holds) |

### holds

**IRI:** `http://www.w3.org/ns/org#holds` · `org:holds`

Indicates a Post held by some Agent.

| | |
|---|---|
| Domain | [foaf:Agent](http://xmlns.com/foaf/0.1/Agent) |
| Range | [Post](classes.md#post) |
| Inverse of | [held by](object-properties.md#heldby) |

### linked to

**IRI:** `http://www.w3.org/ns/org#linkedTo` · `org:linkedTo`

Indicates an arbitrary relationship between two organizations. Specializations of this can be used to, for example, denote funding or supply chain relationships.

| | |
|---|---|
| Domain | [Organization](classes.md#organization) |
| Range | [Organization](classes.md#organization) |

### member

**IRI:** `http://www.w3.org/ns/org#member` · `org:member`

Indicates the Person (or other Agent including Organization) involved in the Membership relationship. Inverse of `org:hasMembership`

| | |
|---|---|
| Domain | [Membership](classes.md#membership) |
| Range | [foaf:Agent](http://xmlns.com/foaf/0.1/Agent) |
| Characteristics | Functional |
| Inverse of | [membership](object-properties.md#hasmembership) |

### member During

**IRI:** `http://www.w3.org/ns/org#memberDuring` · `org:memberDuring`

Optional property to indicate the interval for which the membership is/was valid.

| | |
|---|---|
| Domain | [Membership](classes.md#membership) |

### member of

**IRI:** `http://www.w3.org/ns/org#memberOf` · `org:memberOf`

Indicates that a person is a member of the Organization with no indication of the nature of that membership or the role played. Note that the choice of property name is not meant to limit the property to only formal membership arrangements, it is also indended to cover related concepts such as affilliation or other involvement in the organization. Extensions can specialize this relationship to indicate particular roles within the organization or more nuanced relationships to the organization. Has an optional inverse, `org:hasmember`.

| | |
|---|---|
| Sub-properties | [head of](object-properties.md#headof) |
| Domain | [foaf:Agent](http://xmlns.com/foaf/0.1/Agent) |
| Range | [Organization](classes.md#organization) |
| Inverse of | [has member](object-properties.md#hasmember) |

### membership

**IRI:** `http://www.w3.org/ns/org#hasMembership` · `org:hasMembership`

Indicates a membership relationship that the Agent plays. Inverse of `org:member`.

| | |
|---|---|
| Domain | [foaf:Agent](http://xmlns.com/foaf/0.1/Agent) |
| Range | [Membership](classes.md#membership) |
| Inverse of | [member](object-properties.md#member) |

### organization

**IRI:** `http://www.w3.org/ns/org#organization` · `org:organization`

Indicates Organization in which the Agent is a member.

| | |
|---|---|
| Domain | [Membership](classes.md#membership) |
| Range | [Organization](classes.md#organization) |
| Characteristics | Functional |

### original organization

**IRI:** `http://www.w3.org/ns/org#originalOrganization` · `org:originalOrganization`

Indicates one or more organizations that existed before the change event. Depending on the event they may or may not have continued to exist after the event. Inverse of `org:changedBy`.

| | |
|---|---|
| Super-properties | [prov:used](http://www.w3.org/ns/prov#used) |
| Domain | [Change Event](classes.md#changeevent) |
| Range | [Organization](classes.md#organization) |
| Inverse of | [changed by](object-properties.md#changedby) |

### post

**IRI:** `http://www.w3.org/ns/org#hasPost` · `org:hasPost`

Indicates a Post which exists within the Organization.

| | |
|---|---|
| Domain | [Organization](classes.md#organization) |
| Range | [Post](classes.md#post) |
| Inverse of | [post in](object-properties.md#postin) |

### post in

**IRI:** `http://www.w3.org/ns/org#postIn` · `org:postIn`

Indicates the Organization in which the Post exists.

| | |
|---|---|
| Domain | [Post](classes.md#post) |
| Range | [Organization](classes.md#organization) |
| Inverse of | [post](object-properties.md#haspost) |

### primary Site

**IRI:** `http://www.w3.org/ns/org#hasPrimarySite` · `org:hasPrimarySite`

Indicates a primary site for the Organization, this is the default means by which an Organization can be contacted and is not necessarily the formal headquarters.

| | |
|---|---|
| Super-properties | [has site](object-properties.md#hassite) |
| Sub-properties | [registered Site](object-properties.md#hasregisteredsite) |
| Domain | [Organization](classes.md#organization) |
| Range | [Site](classes.md#site) |

### registered Site

**IRI:** `http://www.w3.org/ns/org#hasRegisteredSite` · `org:hasRegisteredSite`

Indicates the legally registered site for the organization, in many legal jurisdictions there is a requirement that FormalOrganizations such as Companies or Charities have such a primary designed site. 

| | |
|---|---|
| Super-properties | [primary Site](object-properties.md#hasprimarysite) |
| Domain | [Formal Organization](classes.md#formalorganization) |
| Range | [Site](classes.md#site) |

### remuneration

**IRI:** `http://www.w3.org/ns/org#remuneration` · `org:remuneration`

Indicates a salary or other reward associated with the role. Typically this will be denoted using an existing representation scheme such as `gr:PriceSpecification` but the range is left open to allow applications to specialize it (e.g. to remunerationInGBP).

| | |
|---|---|
| Domain | [Role](classes.md#role) |

### reports to

**IRI:** `http://www.w3.org/ns/org#reportsTo` · `org:reportsTo`

Indicates a reporting relationship as might be depicted on an organizational chart. The precise semantics of the reporting relationship will vary by organization but is intended to encompass both direct supervisory relationships (e.g. carrying objective and salary setting authority) and more general reporting or accountability relationships (e.g. so called _dotted line_ reporting).

| | |
|---|---|
| Domain | [foaf:Agent](http://xmlns.com/foaf/0.1/Agent) *or* [Post](classes.md#post) |
| Range | [foaf:Agent](http://xmlns.com/foaf/0.1/Agent) *or* [Post](classes.md#post) |

### resulted from

**IRI:** `http://www.w3.org/ns/org#resultedFrom` · `org:resultedFrom`

Indicates an event which resulted in this organization. Inverse of `org:resultingOrganization`.

| | |
|---|---|
| Super-properties | [prov:wasGeneratedBy](http://www.w3.org/ns/prov#wasGeneratedBy) |
| Domain | [Organization](classes.md#organization) |
| Range | [Change Event](classes.md#changeevent) |
| Inverse of | [resulted in](object-properties.md#resultingorganization) |

### resulted in

**IRI:** `http://www.w3.org/ns/org#resultingOrganization` · `org:resultingOrganization`

Indicates an organization which was created or changed as a result of the event. Inverse of `org:resultedFrom`.

| | |
|---|---|
| Domain | [Change Event](classes.md#changeevent) |
| Range | [Organization](classes.md#organization) |
| Inverse of | [resulted from](object-properties.md#resultedfrom) |

### role

**IRI:** `http://www.w3.org/ns/org#role` · `org:role`

Indicates the Role that the Agent plays in a Membership relationship with an Organization.

| | |
|---|---|
| Domain | [Membership](classes.md#membership) *or* [Post](classes.md#post) |
| Range | [Role](classes.md#role) |

### site Address

**IRI:** `http://www.w3.org/ns/org#siteAddress` · `org:siteAddress`

Indicates an address for the site in a suitable encoding. Use of vCard (using the http://www.w3.org/TR/vcard-rdf/ vocabulary) is encouraged but the range is left open to allow other encodings to be used. The address may include email, telephone, and geo-location information and is not restricted to a physical address. 

| | |
|---|---|
| Domain | [Site](classes.md#site) |

### site Of

**IRI:** `http://www.w3.org/ns/org#siteOf` · `org:siteOf`

Indicates an Organization which has some presence at the given site. This is the inverse of `org:hasSite`.

| | |
|---|---|
| Domain | [Site](classes.md#site) |
| Range | [Organization](classes.md#organization) |
| Inverse of | [has site](object-properties.md#hassite) |

### subOrganization of

**IRI:** `http://www.w3.org/ns/org#subOrganizationOf` · `org:subOrganizationOf`

Represents hierarchical containment of Organizations or OrganizationalUnits; indicates an Organization which contains this Organization. Inverse of `org:hasSubOrganization`.

| | |
|---|---|
| Super-properties | [transitive sub-organization](object-properties.md#transitivesuborganizationof) |
| Sub-properties | [unit Of](object-properties.md#unitof) |
| Domain | [Organization](classes.md#organization) |
| Range | [Organization](classes.md#organization) |
| Inverse of | [has SubOrganization](object-properties.md#hassuborganization) |

### transitive sub-organization

**IRI:** `http://www.w3.org/ns/org#transitiveSubOrganizationOf` · `org:transitiveSubOrganizationOf`

The transitive closure of subOrganizationOf, giving a representation of all organizations that contain this one. Note that technically this is a super property of the transitive closure so it could contain additional assertions but such usage is discouraged.

| | |
|---|---|
| Sub-properties | [subOrganization of](object-properties.md#suborganizationof) |
| Domain | [Organization](classes.md#organization) |
| Range | [Organization](classes.md#organization) |
| Characteristics | Transitive |

### unit Of

**IRI:** `http://www.w3.org/ns/org#unitOf` · `org:unitOf`

Indicates an Organization of which this Unit is a part, e.g. a Department within a larger FormalOrganization. This is the inverse of `org:hasUnit`.

| | |
|---|---|
| Super-properties | [subOrganization of](object-properties.md#suborganizationof) |
| Domain | [OrganizationalUnit](classes.md#organizationalunit) |
| Range | [Formal Organization](classes.md#formalorganization) |
| Inverse of | [has Unit](object-properties.md#hasunit) |

