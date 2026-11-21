# Annotation properties

### aq

**IRI:** `http://www.w3.org/ns/prov#aq` · `prov:aq`

| | |
|---|---|
| Super-properties | [seeAlso](annotation-properties.md#seealso) |

### category

**IRI:** `http://www.w3.org/ns/prov#category` · `prov:category`

Classify prov-o terms into three categories, including 'starting-point', 'qualifed', and 'extended'. This classification is used by the prov-o html document to gently introduce prov-o terms to its users. 

### comment

**IRI:** `http://www.w3.org/2000/01/rdf-schema#comment` · `rdfs:comment`

### component

**IRI:** `http://www.w3.org/ns/prov#component` · `prov:component`

Classify prov-o terms into six components according to prov-dm, including 'agents-responsibility', 'alternate', 'annotations', 'collections', 'derivations', and 'entities-activities'. This classification is used so that readers of prov-o specification can find its correspondence with the prov-dm specification.

### constraints

**IRI:** `http://www.w3.org/ns/prov#constraints` · `prov:constraints`

A reference to the principal section of the PROV-CONSTRAINTS document that describes this concept.

| | |
|---|---|
| Super-properties | [seeAlso](annotation-properties.md#seealso) |

### definition

**IRI:** `http://www.w3.org/ns/prov#definition` · `prov:definition`

A definition quoted from PROV-DM or PROV-CONSTRAINTS that describes the concept expressed with this OWL term.

| | |
|---|---|
| Sub-properties | [editorsDefinition](annotation-properties.md#editorsdefinition) |

### dm

**IRI:** `http://www.w3.org/ns/prov#dm` · `prov:dm`

A reference to the principal section of the PROV-DM document that describes this concept.

| | |
|---|---|
| Super-properties | [seeAlso](annotation-properties.md#seealso) |

### editorialNote

**IRI:** `http://www.w3.org/ns/prov#editorialNote` · `prov:editorialNote`

A note by the OWL development team about how this term expresses the PROV-DM concept, or how it should be used in context of semantic web or linked data.

### editorsDefinition

**IRI:** `http://www.w3.org/ns/prov#editorsDefinition` · `prov:editorsDefinition`

When the prov-o term does not have a definition drawn from prov-dm, and the prov-o editor provides one.

| | |
|---|---|
| Super-properties | [definition](annotation-properties.md#definition) |

### inverse

**IRI:** `http://www.w3.org/ns/prov#inverse` · `prov:inverse`

PROV-O does not define all property inverses. The directionalities defined in PROV-O should be given preference over those not defined. However, if users wish to name the inverse of a PROV-O property, the local name given by prov:inverse should be used.

### isDefinedBy

**IRI:** `http://www.w3.org/2000/01/rdf-schema#isDefinedBy` · `rdfs:isDefinedBy`

### label

**IRI:** `http://www.w3.org/2000/01/rdf-schema#label` · `rdfs:label`

### n

**IRI:** `http://www.w3.org/ns/prov#n` · `prov:n`

A reference to the principal section of the PROV-DM document that describes this concept.

| | |
|---|---|
| Super-properties | [seeAlso](annotation-properties.md#seealso) |

### order

**IRI:** `http://www.w3.org/ns/prov#order` · `prov:order`

The position that this OWL term should be listed within documentation. The scope of the documentation (e.g., among all terms, among terms within a prov:category, among properties applying to a particular class, etc.) is unspecified.

### qualifiedForm

**IRI:** `http://www.w3.org/ns/prov#qualifiedForm` · `prov:qualifiedForm`

This annotation property links a subproperty of prov:wasInfluencedBy with the subclass of prov:Influence and the qualifying property that are used to qualify it. 

Example annotation:

    prov:wasGeneratedBy prov:qualifiedForm prov:qualifiedGeneration, prov:Generation .

Then this unqualified assertion:

    :entity1 prov:wasGeneratedBy :activity1 .

can be qualified by adding:

   :entity1 prov:qualifiedGeneration :entity1Gen .
   :entity1Gen 
       a prov:Generation, prov:Influence;
       prov:activity :activity1;
       :customValue 1337 .

Note how the value of the unqualified influence (prov:wasGeneratedBy :activity1) is mirrored as the value of the prov:activity (or prov:entity, or prov:agent) property on the influence class.

| | |
|---|---|
| Super-properties | [seeAlso](annotation-properties.md#seealso) |

### seeAlso

**IRI:** `http://www.w3.org/2000/01/rdf-schema#seeAlso` · `rdfs:seeAlso`

| | |
|---|---|
| Sub-properties | [aq](annotation-properties.md#aq), [constraints](annotation-properties.md#constraints), [dm](annotation-properties.md#dm), [n](annotation-properties.md#n), [qualifiedForm](annotation-properties.md#qualifiedform), [sharesDefinitionWith](annotation-properties.md#sharesdefinitionwith), [unqualifiedForm](annotation-properties.md#unqualifiedform) |

### sharesDefinitionWith

**IRI:** `http://www.w3.org/ns/prov#sharesDefinitionWith` · `prov:sharesDefinitionWith`

| | |
|---|---|
| Super-properties | [seeAlso](annotation-properties.md#seealso) |

### todo

**IRI:** `http://www.w3.org/ns/prov#todo` · `prov:todo`

### unqualifiedForm

**IRI:** `http://www.w3.org/ns/prov#unqualifiedForm` · `prov:unqualifiedForm`

Classes and properties used to qualify relationships are annotated with prov:unqualifiedForm to indicate the property used to assert an unqualified provenance relation.

| | |
|---|---|
| Super-properties | [seeAlso](annotation-properties.md#seealso) |

### versionInfo

**IRI:** `http://www.w3.org/2002/07/owl#versionInfo` · `owl:versionInfo`

