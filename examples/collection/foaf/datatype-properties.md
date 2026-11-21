# Datatype properties

### account name

**IRI:** `http://xmlns.com/foaf/0.1/accountName` · `foaf:accountName`

Indicates the name (identifier) associated with this online account.

| | |
|---|---|
| Domain | [Online Account](classes.md#onlineaccount) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |

### age

**IRI:** `http://xmlns.com/foaf/0.1/age` · `foaf:age`

The age in years of some agent.

| | |
|---|---|
| Domain | [Agent](classes.md#agent) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |
| Characteristics | Functional |

### AIM chat ID

**IRI:** `http://xmlns.com/foaf/0.1/aimChatID` · `foaf:aimChatID`

An AIM chat ID

| | |
|---|---|
| Super-properties | [nickname](datatype-properties.md#nick) |
| Domain | [Agent](classes.md#agent) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |
| Characteristics | Inverse functional |

### birthday

**IRI:** `http://xmlns.com/foaf/0.1/birthday` · `foaf:birthday`

The birthday of this Agent, represented in mm-dd string form, eg. '12-31'.

| | |
|---|---|
| Domain | [Agent](classes.md#agent) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |
| Characteristics | Functional |

### DNA checksum

**IRI:** `http://xmlns.com/foaf/0.1/dnaChecksum` · `foaf:dnaChecksum`

A checksum for the DNA of some thing. Joke.

| | |
|---|---|
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |

### family_name

**IRI:** `http://xmlns.com/foaf/0.1/family_name` · `foaf:family_name`

The family name of some person.

| | |
|---|---|
| Domain | [Person](classes.md#person) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |

### familyName

**IRI:** `http://xmlns.com/foaf/0.1/familyName` · `foaf:familyName`

The family name of some person.

| | |
|---|---|
| Domain | [Person](classes.md#person) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |

### firstName

**IRI:** `http://xmlns.com/foaf/0.1/firstName` · `foaf:firstName`

The first name of a person.

| | |
|---|---|
| Domain | [Person](classes.md#person) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |

### geekcode

**IRI:** `http://xmlns.com/foaf/0.1/geekcode` · `foaf:geekcode`

A textual geekcode for this person, see http://www.geekcode.com/geek.html

| | |
|---|---|
| Domain | [Person](classes.md#person) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |

### gender

**IRI:** `http://xmlns.com/foaf/0.1/gender` · `foaf:gender`

The gender of this Agent (typically but not necessarily 'male' or 'female').

| | |
|---|---|
| Domain | [Agent](classes.md#agent) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |
| Characteristics | Functional |

### Given name

**IRI:** `http://xmlns.com/foaf/0.1/givenName` · `foaf:givenName`

The given name of some person.

### Given name

**IRI:** `http://xmlns.com/foaf/0.1/givenname` · `foaf:givenname`

The given name of some person.

### ICQ chat ID

**IRI:** `http://xmlns.com/foaf/0.1/icqChatID` · `foaf:icqChatID`

An ICQ chat ID

| | |
|---|---|
| Super-properties | [nickname](datatype-properties.md#nick) |
| Domain | [Agent](classes.md#agent) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |
| Characteristics | Inverse functional |

### jabber ID

**IRI:** `http://xmlns.com/foaf/0.1/jabberID` · `foaf:jabberID`

A jabber ID for something.

| | |
|---|---|
| Domain | [Agent](classes.md#agent) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |
| Characteristics | Inverse functional |

### lastName

**IRI:** `http://xmlns.com/foaf/0.1/lastName` · `foaf:lastName`

The last name of a person.

| | |
|---|---|
| Domain | [Person](classes.md#person) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |

### MSN chat ID

**IRI:** `http://xmlns.com/foaf/0.1/msnChatID` · `foaf:msnChatID`

An MSN chat ID

| | |
|---|---|
| Super-properties | [nickname](datatype-properties.md#nick) |
| Domain | [Agent](classes.md#agent) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |
| Characteristics | Inverse functional |

### myersBriggs

**IRI:** `http://xmlns.com/foaf/0.1/myersBriggs` · `foaf:myersBriggs`

A Myers Briggs (MBTI) personality classification.

| | |
|---|---|
| Domain | [Person](classes.md#person) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |

### name

**IRI:** `http://xmlns.com/foaf/0.1/name` · `foaf:name`

A name for some thing.

| | |
|---|---|
| Super-properties | [label](annotation-properties.md#label) |
| Domain | [Thing](http://www.w3.org/2002/07/owl#Thing) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |

### nickname

**IRI:** `http://xmlns.com/foaf/0.1/nick` · `foaf:nick`

A short informal nickname characterising an agent (includes login identifiers, IRC and other chat nicknames).

| | |
|---|---|
| Sub-properties | [AIM chat ID](datatype-properties.md#aimchatid), [ICQ chat ID](datatype-properties.md#icqchatid), [MSN chat ID](datatype-properties.md#msnchatid), [Skype ID](datatype-properties.md#skypeid), [Yahoo chat ID](datatype-properties.md#yahoochatid) |

### plan

**IRI:** `http://xmlns.com/foaf/0.1/plan` · `foaf:plan`

A .plan comment, in the tradition of finger and '.plan' files.

| | |
|---|---|
| Domain | [Person](classes.md#person) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |

### sha1sum (hex)

**IRI:** `http://xmlns.com/foaf/0.1/sha1` · `foaf:sha1`

A sha1sum hash, in hex.

| | |
|---|---|
| Domain | [Document](classes.md#document) |

### sha1sum of a personal mailbox URI name

**IRI:** `http://xmlns.com/foaf/0.1/mbox_sha1sum` · `foaf:mbox_sha1sum`

The sha1sum of the URI of an Internet mailbox associated with exactly one owner, the  first owner of the mailbox.

| | |
|---|---|
| Domain | [Agent](classes.md#agent) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |
| Characteristics | Inverse functional |

### Skype ID

**IRI:** `http://xmlns.com/foaf/0.1/skypeID` · `foaf:skypeID`

A Skype ID

| | |
|---|---|
| Super-properties | [nickname](datatype-properties.md#nick) |
| Domain | [Agent](classes.md#agent) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |

### status

**IRI:** `http://xmlns.com/foaf/0.1/status` · `foaf:status`

A string expressing what the user is happy for the general public (normally) to know about their current activity.

| | |
|---|---|
| Domain | [Agent](classes.md#agent) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |

### Surname

**IRI:** `http://xmlns.com/foaf/0.1/surname` · `foaf:surname`

The surname of some person.

| | |
|---|---|
| Domain | [Person](classes.md#person) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |

### title

**IRI:** `http://xmlns.com/foaf/0.1/title` · `foaf:title`

Title (Mr, Mrs, Ms, Dr. etc)

### Yahoo chat ID

**IRI:** `http://xmlns.com/foaf/0.1/yahooChatID` · `foaf:yahooChatID`

A Yahoo chat ID

| | |
|---|---|
| Super-properties | [nickname](datatype-properties.md#nick) |
| Domain | [Agent](classes.md#agent) |
| Range | [rdfs:Literal](http://www.w3.org/2000/01/rdf-schema#Literal) |
| Characteristics | Inverse functional |

