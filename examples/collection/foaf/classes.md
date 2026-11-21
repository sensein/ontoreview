# Classes

### Agent

**IRI:** `http://xmlns.com/foaf/0.1/Agent` · `foaf:Agent`

An agent (eg. person, group, software or physical artifact).

| | |
|---|---|
| Equivalent to | [dcterms:Agent](http://purl.org/dc/terms/Agent) |
| Subclasses | [Group](classes.md#group), [Organization](classes.md#organization), [Person](classes.md#person) |
| Used in | in domain of [account](object-properties.md#holdsaccount); in domain of [account](object-properties.md#account); in domain of [age](datatype-properties.md#age); in domain of [AIM chat ID](datatype-properties.md#aimchatid); in domain of [birthday](datatype-properties.md#birthday); in domain of [gender](datatype-properties.md#gender); in domain of [ICQ chat ID](datatype-properties.md#icqchatid); in domain of [interest](object-properties.md#interest); in domain of [jabber ID](datatype-properties.md#jabberid); in domain of [made](object-properties.md#made); in domain of [MSN chat ID](datatype-properties.md#msnchatid); in domain of [openid](object-properties.md#openid); in domain of [personal mailbox](object-properties.md#mbox); in domain of [sha1sum of a personal mailbox URI name](datatype-properties.md#mbox_sha1sum); in domain of [Skype ID](datatype-properties.md#skypeid); in domain of [status](datatype-properties.md#status); in domain of [tipjar](object-properties.md#tipjar); in domain of [topic_interest](object-properties.md#topic_interest); in domain of [weblog](object-properties.md#weblog); in domain of [Yahoo chat ID](datatype-properties.md#yahoochatid); in range of [maker](object-properties.md#maker); in range of [member](object-properties.md#member) |

### Document

**IRI:** `http://xmlns.com/foaf/0.1/Document` · `foaf:Document`

A document.

| | |
|---|---|
| Equivalent to | [CreativeWork](http://schema.org/CreativeWork) |
| Subclasses | [Image](classes.md#image), [PersonalProfileDocument](classes.md#personalprofiledocument) |
| Disjoint with | [Organization](classes.md#organization), [Project](classes.md#project) |
| Used in | in domain of [primary topic](object-properties.md#primarytopic); in domain of [sha1sum (hex)](datatype-properties.md#sha1); in domain of [topic](object-properties.md#topic); in range of [account service homepage](object-properties.md#accountservicehomepage); in range of [homepage](object-properties.md#homepage); in range of [interest](object-properties.md#interest); in range of [is primary topic of](object-properties.md#isprimarytopicof); in range of [openid](object-properties.md#openid); in range of [page](object-properties.md#page); in range of [publications](object-properties.md#publications); in range of [schoolHomepage](object-properties.md#schoolhomepage); in range of [tipjar](object-properties.md#tipjar); in range of [weblog](object-properties.md#weblog); in range of [work info homepage](object-properties.md#workinfohomepage); in range of [workplace homepage](object-properties.md#workplacehomepage) |

### Group

**IRI:** `http://xmlns.com/foaf/0.1/Group` · `foaf:Group`

A class of Agents.

| | |
|---|---|
| Superclasses | [Agent](classes.md#agent) |
| Used in | in domain of [member](object-properties.md#member) |

### Image

**IRI:** `http://xmlns.com/foaf/0.1/Image` · `foaf:Image`

An image.

| | |
|---|---|
| Superclasses | [Document](classes.md#document) |
| Equivalent to | [ImageObject](http://schema.org/ImageObject) |
| Used in | in domain of [depicts](object-properties.md#depicts); in domain of [thumbnail](object-properties.md#thumbnail); in range of [depiction](object-properties.md#depiction); in range of [image](object-properties.md#img); in range of [thumbnail](object-properties.md#thumbnail) |

### Label Property

**IRI:** `http://xmlns.com/foaf/0.1/LabelProperty` · `foaf:LabelProperty`

A foaf:LabelProperty is any RDF property with texual values that serve as labels.

### Online Account

**IRI:** `http://xmlns.com/foaf/0.1/OnlineAccount` · `foaf:OnlineAccount`

An online account.

| | |
|---|---|
| Subclasses | [Online Chat Account](classes.md#onlinechataccount), [Online E-commerce Account](classes.md#onlineecommerceaccount), [Online Gaming Account](classes.md#onlinegamingaccount) |
| Used in | in domain of [account name](datatype-properties.md#accountname); in domain of [account service homepage](object-properties.md#accountservicehomepage); in range of [account](object-properties.md#holdsaccount); in range of [account](object-properties.md#account) |

### Online Chat Account

**IRI:** `http://xmlns.com/foaf/0.1/OnlineChatAccount` · `foaf:OnlineChatAccount`

An online chat account.

| | |
|---|---|
| Superclasses | [Online Account](classes.md#onlineaccount) |

### Online E-commerce Account

**IRI:** `http://xmlns.com/foaf/0.1/OnlineEcommerceAccount` · `foaf:OnlineEcommerceAccount`

An online e-commerce account.

| | |
|---|---|
| Superclasses | [Online Account](classes.md#onlineaccount) |

### Online Gaming Account

**IRI:** `http://xmlns.com/foaf/0.1/OnlineGamingAccount` · `foaf:OnlineGamingAccount`

An online gaming account.

| | |
|---|---|
| Superclasses | [Online Account](classes.md#onlineaccount) |

### Organization

**IRI:** `http://xmlns.com/foaf/0.1/Organization` · `foaf:Organization`

An organization.

| | |
|---|---|
| Superclasses | [Agent](classes.md#agent) |
| Disjoint with | [Document](classes.md#document), [Person](classes.md#person) |

### Person

**IRI:** `http://xmlns.com/foaf/0.1/Person` · `foaf:Person`

A person.

| | |
|---|---|
| Superclasses | [Agent](classes.md#agent), [Spatial Thing](classes.md#spatialthing) |
| Equivalent to | [Person](http://www.w3.org/2000/10/swap/pim/contact#Person); [Person](http://schema.org/Person) |
| Disjoint with | [Organization](classes.md#organization), [Project](classes.md#project) |
| Used in | in domain of [current project](object-properties.md#currentproject); in domain of [family_name](datatype-properties.md#family_name); in domain of [familyName](datatype-properties.md#familyname); in domain of [firstName](datatype-properties.md#firstname); in domain of [geekcode](datatype-properties.md#geekcode); in domain of [image](object-properties.md#img); in domain of [knows](object-properties.md#knows); in domain of [lastName](datatype-properties.md#lastname); in domain of [myersBriggs](datatype-properties.md#myersbriggs); in domain of [past project](object-properties.md#pastproject); in domain of [plan](datatype-properties.md#plan); in domain of [publications](object-properties.md#publications); in domain of [schoolHomepage](object-properties.md#schoolhomepage); in domain of [Surname](datatype-properties.md#surname); in domain of [work info homepage](object-properties.md#workinfohomepage); in domain of [workplace homepage](object-properties.md#workplacehomepage); in range of [knows](object-properties.md#knows) |

### PersonalProfileDocument

**IRI:** `http://xmlns.com/foaf/0.1/PersonalProfileDocument` · `foaf:PersonalProfileDocument`

A personal profile RDF document.

| | |
|---|---|
| Superclasses | [Document](classes.md#document) |

### Project

**IRI:** `http://xmlns.com/foaf/0.1/Project` · `foaf:Project`

A project (a collective endeavour of some kind).

| | |
|---|---|
| Disjoint with | [Document](classes.md#document), [Person](classes.md#person) |

### Spatial Thing

**IRI:** `http://www.w3.org/2003/01/geo/wgs84_pos#SpatialThing`

| | |
|---|---|
| Subclasses | [Person](classes.md#person) |
| Used in | in domain of [based near](object-properties.md#based_near); in range of [based near](object-properties.md#based_near) |

