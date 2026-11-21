# Classes

### Change Event

**IRI:** `http://www.w3.org/ns/org#ChangeEvent` · `org:ChangeEvent`

Represents an event which resulted in a major change to an organization such as a merger or complete restructuring. It is intended for situations where the resulting organization is sufficient distinct from the original organizations that it has a distinct identity and distinct URI. Extension vocabularies should define sub-classes of this to denote particular categories of event. The instant or interval at which the event occurred should be given by `prov:startAtTime` and `prov:endedAtTime`, a description should be given by `dct:description`. 

| | |
|---|---|
| Superclasses | [prov:Activity](http://www.w3.org/ns/prov#Activity) |
| Disjoint with | [Membership](classes.md#membership), [Organization](classes.md#organization), [Role](classes.md#role), [Site](classes.md#site) |
| Used in | in domain of [original organization](object-properties.md#originalorganization); in domain of [resulted in](object-properties.md#resultingorganization); in range of [changed by](object-properties.md#changedby); in range of [resulted from](object-properties.md#resultedfrom) |

### Endeavour

**IRI:** `http://www.w3.org/ns/org#OrganizationalCollaboration` · `org:OrganizationalCollaboration`

A collaboration between two or more Organizations such as a project. It meets the criteria for being an Organization in that it has an identity and defining purpose independent of its particular members but is neither a formally recognized legal entity nor a sub-unit within some larger organization. Might typically have a shorter lifetime than the Organizations within it, but not necessarily. All members are `org:Organization`s rather than individuals and those Organizations can play particular roles within the venture. Alternative names: _Project_ _Venture_  _Endeavour_ _Consortium_ _Endeavour_

| | |
|---|---|
| Superclasses | [Organization](classes.md#organization) |
| Equivalent to | [Organization](classes.md#organization) *and* ([has member](object-properties.md#hasmember) *only* [Organization](classes.md#organization)) |

### Formal Organization

**IRI:** `http://www.w3.org/ns/org#FormalOrganization` · `org:FormalOrganization`

An Organization which is recognized in the world at large, in particular in legal jurisdictions, with associated rights and responsibilities. Examples include a Corporation, Charity, Government or Church. Note that this is a super class of `gr:BusinessEntity` and it is recommended to use the GoodRelations vocabulary to denote Business classifications such as DUNS or NAICS.

| | |
|---|---|
| Superclasses | [foaf:Organization](http://xmlns.com/foaf/0.1/Organization), [Organization](classes.md#organization) |
| Subclasses | [gr:BusinessEntity](http://purl.org/goodrelations/v1#BusinessEntity) |
| Used in | in domain of [has Unit](object-properties.md#hasunit); in domain of [registered Site](object-properties.md#hasregisteredsite); in range of [unit Of](object-properties.md#unitof) |

### Membership

**IRI:** `http://www.w3.org/ns/org#Membership` · `org:Membership`

Indicates the nature of an Agent's membership of an organization. Represents an n-ary relation between an Agent, an Organization and a Role. It is possible to directly indicate membership, independent of the specific Role, through use of the `org:memberOf` property.

| | |
|---|---|
| Disjoint with | [Change Event](classes.md#changeevent), [Organization](classes.md#organization), [Role](classes.md#role), [Site](classes.md#site) |
| Used in | in domain of [member](object-properties.md#member); in domain of [member During](object-properties.md#memberduring); in domain of [organization](object-properties.md#organization); in domain of [role](object-properties.md#role); in range of [membership](object-properties.md#hasmembership) |

### Organization

**IRI:** `http://www.w3.org/ns/org#Organization` · `org:Organization`

Represents a collection of people organized together into a community or other social, commercial or political structure. The group has some common purpose or reason for existence which goes beyond the set of people belonging to it and can act as an Agent. Organizations are often decomposable into hierarchical structures.  It is recommended that SKOS lexical labels should be used to label the Organization. In particular `skos:prefLabel` for the primary (possibly legally recognized name), `skos:altLabel` for alternative names (trading names, colloquial names) and `skos:notation` to denote a code from a code list. Alternative names: _Collective_ _Body_ _Org_ _Group_

| | |
|---|---|
| Superclasses | [foaf:Agent](http://xmlns.com/foaf/0.1/Agent) |
| Equivalent to | [foaf:Organization](http://xmlns.com/foaf/0.1/Organization) |
| Subclasses | [Endeavour](classes.md#organizationalcollaboration), [Formal Organization](classes.md#formalorganization), [OrganizationalUnit](classes.md#organizationalunit) |
| Disjoint with | [Change Event](classes.md#changeevent), [Membership](classes.md#membership), [Role](classes.md#role), [Site](classes.md#site) |
| Used in | in domain of [changed by](object-properties.md#changedby); in domain of [classification](object-properties.md#classification); in domain of [has member](object-properties.md#hasmember); in domain of [has site](object-properties.md#hassite); in domain of [has SubOrganization](object-properties.md#hassuborganization); in domain of [identifier](datatype-properties.md#identifier); in domain of [linked to](object-properties.md#linkedto); in domain of [post](object-properties.md#haspost); in domain of [primary Site](object-properties.md#hasprimarysite); in domain of [purpose](properties.md#purpose); in domain of [resulted from](object-properties.md#resultedfrom); in domain of [subOrganization of](object-properties.md#suborganizationof); in domain of [transitive sub-organization](object-properties.md#transitivesuborganizationof); in range of [has SubOrganization](object-properties.md#hassuborganization); in range of [head of](object-properties.md#headof); in range of [linked to](object-properties.md#linkedto); in range of [member of](object-properties.md#memberof); in range of [organization](object-properties.md#organization); in range of [original organization](object-properties.md#originalorganization); in range of [post in](object-properties.md#postin); in range of [resulted in](object-properties.md#resultingorganization); in range of [site Of](object-properties.md#siteof); in range of [subOrganization of](object-properties.md#suborganizationof); in range of [transitive sub-organization](object-properties.md#transitivesuborganizationof); used in axioms of [Endeavour](classes.md#organizationalcollaboration) |

### OrganizationalUnit

**IRI:** `http://www.w3.org/ns/org#OrganizationalUnit` · `org:OrganizationalUnit`

An Organization such as a University Support Unit which is part of some larger FormalOrganization and only has full recognition within the context of that FormalOrganization, it is not a Legal Entity in its own right. Units can be large and complex containing other Units and even FormalOrganizations. Alternative names: _OU_ _Unit_ _Department_

| | |
|---|---|
| Superclasses | [Organization](classes.md#organization) |
| Used in | in domain of [unit Of](object-properties.md#unitof); in range of [has Unit](object-properties.md#hasunit) |

### Post

**IRI:** `http://www.w3.org/ns/org#Post` · `org:Post`

A Post represents some position within an organization that exists independently of the person or persons filling it. Posts may be used to represent situations where a person is a member of an organization ex officio (for example the Secretary of State for Scotland is part of UK Cabinet by virtue of being Secretary of State for Scotland, not as an individual person). A post can be held by multiple people and hence can be treated as a organization in its own right.

| | |
|---|---|
| Used in | in domain of [held by](object-properties.md#heldby); in domain of [post in](object-properties.md#postin); in domain of [reports to](object-properties.md#reportsto); in domain of [role](object-properties.md#role); in range of [holds](object-properties.md#holds); in range of [post](object-properties.md#haspost); in range of [reports to](object-properties.md#reportsto) |

### Role

**IRI:** `http://www.w3.org/ns/org#Role` · `org:Role`

Denotes a role that a Person or other Agent can take in an organization. Instances of this class describe the abstract role; to denote a specific instance of a person playing that role in a specific organization use an instance of `org:Membership`. It is common for roles to be arranged in some taxonomic structure and we use SKOS to represent that. The normal SKOS lexical properties should be used when labelling the Role. Additional descriptive properties for the Role, such as a Salary band, may be added by extension vocabularies.

| | |
|---|---|
| Superclasses | [skos:Concept](http://www.w3.org/2004/02/skos/core#Concept) |
| Disjoint with | [Change Event](classes.md#changeevent), [Membership](classes.md#membership), [Organization](classes.md#organization), [Site](classes.md#site) |
| Instances | [head](individuals.md#head) |
| Used in | in domain of [remuneration](object-properties.md#remuneration); in domain of [role (property)](annotation-properties.md#roleproperty); in range of [role](object-properties.md#role) |

### Site

**IRI:** `http://www.w3.org/ns/org#Site` · `org:Site`

An office or other premise at which the organization is located. Many organizations are spread across multiple sites and many sites will host multiple locations. In most cases a Site will be a physical location. However, we don't exclude the possibility of non-physical sites such as a virtual office with an associated post box and phone reception service. Extensions may provide subclasses to denote particular types of site.

| | |
|---|---|
| Disjoint with | [Change Event](classes.md#changeevent), [Membership](classes.md#membership), [Organization](classes.md#organization), [Role](classes.md#role) |
| Used in | in domain of [site Address](object-properties.md#siteaddress); in domain of [site Of](object-properties.md#siteof); in range of [based At](object-properties.md#basedat); in range of [has site](object-properties.md#hassite); in range of [primary Site](object-properties.md#hasprimarysite); in range of [registered Site](object-properties.md#hasregisteredsite) |

