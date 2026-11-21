# Object properties

### account

**IRI:** `http://xmlns.com/foaf/0.1/account` · `foaf:account`

Indicates an account held by this agent.

| | |
|---|---|
| Domain | [Agent](classes.md#agent) |
| Range | [Online Account](classes.md#onlineaccount) |

### account

**IRI:** `http://xmlns.com/foaf/0.1/holdsAccount` · `foaf:holdsAccount`

Indicates an account held by this agent.

| | |
|---|---|
| Domain | [Agent](classes.md#agent) |
| Range | [Online Account](classes.md#onlineaccount) |

### account service homepage

**IRI:** `http://xmlns.com/foaf/0.1/accountServiceHomepage` · `foaf:accountServiceHomepage`

Indicates a homepage of the service provide for this online account.

| | |
|---|---|
| Domain | [Online Account](classes.md#onlineaccount) |
| Range | [Document](classes.md#document) |

### based near

**IRI:** `http://xmlns.com/foaf/0.1/based_near` · `foaf:based_near`

A location that something is based near, for some broadly human notion of near.

| | |
|---|---|
| Domain | [Spatial Thing](classes.md#spatialthing) |
| Range | [Spatial Thing](classes.md#spatialthing) |

### current project

**IRI:** `http://xmlns.com/foaf/0.1/currentProject` · `foaf:currentProject`

A current project this person works on.

| | |
|---|---|
| Domain | [Person](classes.md#person) |
| Range | [Thing](http://www.w3.org/2002/07/owl#Thing) |

### depiction

**IRI:** `http://xmlns.com/foaf/0.1/depiction` · `foaf:depiction`

A depiction of some thing.

| | |
|---|---|
| Sub-properties | [image](object-properties.md#img) |
| Domain | [Thing](http://www.w3.org/2002/07/owl#Thing) |
| Range | [Image](classes.md#image) |
| Inverse of | [depicts](object-properties.md#depicts) |

### depicts

**IRI:** `http://xmlns.com/foaf/0.1/depicts` · `foaf:depicts`

A thing depicted in this representation.

| | |
|---|---|
| Domain | [Image](classes.md#image) |
| Range | [Thing](http://www.w3.org/2002/07/owl#Thing) |
| Inverse of | [depiction](object-properties.md#depiction) |

### focus

**IRI:** `http://xmlns.com/foaf/0.1/focus` · `foaf:focus`

The underlying or 'focal' entity associated with some SKOS-described concept.

| | |
|---|---|
| Domain | [Concept](http://www.w3.org/2004/02/skos/core#Concept) |
| Range | [Thing](http://www.w3.org/2002/07/owl#Thing) |

### funded by

**IRI:** `http://xmlns.com/foaf/0.1/fundedBy` · `foaf:fundedBy`

An organization funding a project or person.

| | |
|---|---|
| Domain | [Thing](http://www.w3.org/2002/07/owl#Thing) |
| Range | [Thing](http://www.w3.org/2002/07/owl#Thing) |

### homepage

**IRI:** `http://xmlns.com/foaf/0.1/homepage` · `foaf:homepage`

A homepage for some thing.

| | |
|---|---|
| Super-properties | [is primary topic of](object-properties.md#isprimarytopicof), [page](object-properties.md#page) |
| Domain | [Thing](http://www.w3.org/2002/07/owl#Thing) |
| Range | [Document](classes.md#document) |
| Characteristics | Inverse functional |

### image

**IRI:** `http://xmlns.com/foaf/0.1/img` · `foaf:img`

An image that can be used to represent some thing (ie. those depictions which are particularly representative of something, eg. one's photo on a homepage).

| | |
|---|---|
| Super-properties | [depiction](object-properties.md#depiction) |
| Domain | [Person](classes.md#person) |
| Range | [Image](classes.md#image) |

### interest

**IRI:** `http://xmlns.com/foaf/0.1/interest` · `foaf:interest`

A page about a topic of interest to this person.

| | |
|---|---|
| Domain | [Agent](classes.md#agent) |
| Range | [Document](classes.md#document) |

### is primary topic of

**IRI:** `http://xmlns.com/foaf/0.1/isPrimaryTopicOf` · `foaf:isPrimaryTopicOf`

A document that this thing is the primary topic of.

| | |
|---|---|
| Super-properties | [page](object-properties.md#page) |
| Sub-properties | [homepage](object-properties.md#homepage), [openid](object-properties.md#openid) |
| Domain | [Thing](http://www.w3.org/2002/07/owl#Thing) |
| Range | [Document](classes.md#document) |
| Characteristics | Inverse functional |
| Inverse of | [primary topic](object-properties.md#primarytopic) |

### knows

**IRI:** `http://xmlns.com/foaf/0.1/knows` · `foaf:knows`

A person known by this person (indicating some level of reciprocated interaction between the parties).

| | |
|---|---|
| Domain | [Person](classes.md#person) |
| Range | [Person](classes.md#person) |

### logo

**IRI:** `http://xmlns.com/foaf/0.1/logo` · `foaf:logo`

A logo representing some thing.

| | |
|---|---|
| Domain | [Thing](http://www.w3.org/2002/07/owl#Thing) |
| Range | [Thing](http://www.w3.org/2002/07/owl#Thing) |
| Characteristics | Inverse functional |

### made

**IRI:** `http://xmlns.com/foaf/0.1/made` · `foaf:made`

Something that was made by this agent.

| | |
|---|---|
| Domain | [Agent](classes.md#agent) |
| Range | [Thing](http://www.w3.org/2002/07/owl#Thing) |
| Inverse of | [maker](object-properties.md#maker) |

### maker

**IRI:** `http://xmlns.com/foaf/0.1/maker` · `foaf:maker`

An agent that  made this thing.

| | |
|---|---|
| Domain | [Thing](http://www.w3.org/2002/07/owl#Thing) |
| Range | [Agent](classes.md#agent) |
| Inverse of | [made](object-properties.md#made) |

### member

**IRI:** `http://xmlns.com/foaf/0.1/member` · `foaf:member`

Indicates a member of a Group

| | |
|---|---|
| Domain | [Group](classes.md#group) |
| Range | [Agent](classes.md#agent) |

### openid

**IRI:** `http://xmlns.com/foaf/0.1/openid` · `foaf:openid`

An OpenID for an Agent.

| | |
|---|---|
| Super-properties | [is primary topic of](object-properties.md#isprimarytopicof) |
| Domain | [Agent](classes.md#agent) |
| Range | [Document](classes.md#document) |
| Characteristics | Inverse functional |

### page

**IRI:** `http://xmlns.com/foaf/0.1/page` · `foaf:page`

A page or document about this thing.

| | |
|---|---|
| Sub-properties | [homepage](object-properties.md#homepage), [is primary topic of](object-properties.md#isprimarytopicof), [tipjar](object-properties.md#tipjar), [weblog](object-properties.md#weblog) |
| Domain | [Thing](http://www.w3.org/2002/07/owl#Thing) |
| Range | [Document](classes.md#document) |
| Inverse of | [topic](object-properties.md#topic) |

### past project

**IRI:** `http://xmlns.com/foaf/0.1/pastProject` · `foaf:pastProject`

A project this person has previously worked on.

| | |
|---|---|
| Domain | [Person](classes.md#person) |
| Range | [Thing](http://www.w3.org/2002/07/owl#Thing) |

### personal mailbox

**IRI:** `http://xmlns.com/foaf/0.1/mbox` · `foaf:mbox`

A  personal mailbox, ie. an Internet mailbox associated with exactly one owner, the first owner of this mailbox. This is a 'static inverse functional property', in that  there is (across time and change) at most one individual that ever has any particular value for foaf:mbox.

| | |
|---|---|
| Domain | [Agent](classes.md#agent) |
| Range | [Thing](http://www.w3.org/2002/07/owl#Thing) |
| Characteristics | Inverse functional |

### phone

**IRI:** `http://xmlns.com/foaf/0.1/phone` · `foaf:phone`

A phone,  specified using fully qualified tel: URI scheme (refs: http://www.w3.org/Addressing/schemes.html#tel).

### primary topic

**IRI:** `http://xmlns.com/foaf/0.1/primaryTopic` · `foaf:primaryTopic`

The primary topic of some page or document.

| | |
|---|---|
| Domain | [Document](classes.md#document) |
| Range | [Thing](http://www.w3.org/2002/07/owl#Thing) |
| Characteristics | Functional |
| Inverse of | [is primary topic of](object-properties.md#isprimarytopicof) |

### publications

**IRI:** `http://xmlns.com/foaf/0.1/publications` · `foaf:publications`

A link to the publications of this person.

| | |
|---|---|
| Domain | [Person](classes.md#person) |
| Range | [Document](classes.md#document) |

### schoolHomepage

**IRI:** `http://xmlns.com/foaf/0.1/schoolHomepage` · `foaf:schoolHomepage`

A homepage of a school attended by the person.

| | |
|---|---|
| Domain | [Person](classes.md#person) |
| Range | [Document](classes.md#document) |

### theme

**IRI:** `http://xmlns.com/foaf/0.1/theme` · `foaf:theme`

A theme.

| | |
|---|---|
| Domain | [Thing](http://www.w3.org/2002/07/owl#Thing) |
| Range | [Thing](http://www.w3.org/2002/07/owl#Thing) |

### thumbnail

**IRI:** `http://xmlns.com/foaf/0.1/thumbnail` · `foaf:thumbnail`

A derived thumbnail image.

| | |
|---|---|
| Domain | [Image](classes.md#image) |
| Range | [Image](classes.md#image) |

### tipjar

**IRI:** `http://xmlns.com/foaf/0.1/tipjar` · `foaf:tipjar`

A tipjar document for this agent, describing means for payment and reward.

| | |
|---|---|
| Super-properties | [page](object-properties.md#page) |
| Domain | [Agent](classes.md#agent) |
| Range | [Document](classes.md#document) |

### topic

**IRI:** `http://xmlns.com/foaf/0.1/topic` · `foaf:topic`

A topic of some page or document.

| | |
|---|---|
| Domain | [Document](classes.md#document) |
| Range | [Thing](http://www.w3.org/2002/07/owl#Thing) |
| Inverse of | [page](object-properties.md#page) |

### topic_interest

**IRI:** `http://xmlns.com/foaf/0.1/topic_interest` · `foaf:topic_interest`

A thing of interest to this person.

| | |
|---|---|
| Domain | [Agent](classes.md#agent) |
| Range | [Thing](http://www.w3.org/2002/07/owl#Thing) |

### weblog

**IRI:** `http://xmlns.com/foaf/0.1/weblog` · `foaf:weblog`

A weblog of some thing (whether person, group, company etc.).

| | |
|---|---|
| Super-properties | [page](object-properties.md#page) |
| Domain | [Agent](classes.md#agent) |
| Range | [Document](classes.md#document) |
| Characteristics | Inverse functional |

### work info homepage

**IRI:** `http://xmlns.com/foaf/0.1/workInfoHomepage` · `foaf:workInfoHomepage`

A work info homepage of some person; a page about their work for some organization.

| | |
|---|---|
| Domain | [Person](classes.md#person) |
| Range | [Document](classes.md#document) |

### workplace homepage

**IRI:** `http://xmlns.com/foaf/0.1/workplaceHomepage` · `foaf:workplaceHomepage`

A workplace homepage of some person; the homepage of an organization they work for.

| | |
|---|---|
| Domain | [Person](classes.md#person) |
| Range | [Document](classes.md#document) |

