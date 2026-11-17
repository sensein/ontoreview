# Object properties

### access address

**IRI:** `http://www.w3.org/ns/dcat#accessURL` · `dcat:accessURL`

A URL of a resource that gives access to a distribution of the dataset. E.g. landing page, feed, SPARQL endpoint. Use for all cases except a simple download link, in which case downloadURL is preferred.

A URL of a resource that gives access to a distribution of the dataset. E.g. landing page, feed, SPARQL endpoint. Use for all cases except a simple download link, in which case downloadURL is preferred.

| | |
|---|---|
| Domain | [Distribution](classes.md#distribution) |
| Range | [rdfs:Resource](http://www.w3.org/2000/01/rdf-schema#Resource) |
| Property chain | [data access service](object-properties.md#accessservice) *o* [service end-point](object-properties.md#endpointurl) |

### catalog

**IRI:** `http://www.w3.org/ns/dcat#catalog` · `dcat:catalog`

A catalog that is listed in the catalog.

A catalog that is listed in the catalog.

| | |
|---|---|
| Super-properties | [resource](object-properties.md#resource) |
| Domain | [Catalog](classes.md#catalog) |
| Range | [Catalog](classes.md#catalog) |

### compression format

**IRI:** `http://www.w3.org/ns/dcat#compressFormat` · `dcat:compressFormat`

The compression format of the distribution in which the data is contained in a compressed form, e.g. to reduce the size of the downloadable file.

The compression format of the distribution in which the data is contained in a compressed form, e.g. to reduce the size of the downloadable file.

| | |
|---|---|
| Super-properties | [dcterms:format](http://purl.org/dc/terms/format) |
| Domain | [Distribution](classes.md#distribution) |
| Range | [dcterms:MediaType](http://purl.org/dc/terms/MediaType) |

### contact point

**IRI:** `http://www.w3.org/ns/dcat#contactPoint` · `dcat:contactPoint`

Relevant contact information for the catalogued resource. Use of vCard is recommended.

Relevant contact information for the catalogued resource. Use of vCard is recommended.

| | |
|---|---|
| Range | [vcard:Kind](http://www.w3.org/2006/vcard/ns#Kind) |

### data access service

**IRI:** `http://www.w3.org/ns/dcat#accessService` · `dcat:accessService`

A site or end-point that gives access to the distribution of the dataset.

A site or end-point that gives access to the distribution of the dataset.

| | |
|---|---|
| Range | [Data service](classes.md#dataservice) |

### dataset

**IRI:** `http://www.w3.org/ns/dcat#dataset` · `dcat:dataset`

A dataset that is listed in the catalog.

A dataset that is listed in the catalog.

| | |
|---|---|
| Super-properties | [resource](object-properties.md#resource) |
| Domain | [Catalog](classes.md#catalog) |
| Range | [Dataset](classes.md#dataset) |

### description of service end-point

**IRI:** `http://www.w3.org/ns/dcat#endpointDescription` · `dcat:endpointDescription`

A description of the service end-point, including its operations, parameters etc.

A description of the service end-point, including its operations, parameters etc.

| | |
|---|---|
| Domain | [Data service](classes.md#dataservice) |

### distribution

**IRI:** `http://www.w3.org/ns/dcat#distribution` · `dcat:distribution`

An available distribution of the dataset.

An available distribution of the dataset.

| | |
|---|---|
| Super-properties | [dcterms:relation](http://purl.org/dc/terms/relation) |
| Domain | [Dataset](classes.md#dataset) |
| Range | [Distribution](classes.md#distribution) |
| Inverse of | [dcat:isDistributionOf](http://www.w3.org/ns/dcat#isDistributionOf) |

### download URL

**IRI:** `http://www.w3.org/ns/dcat#downloadURL` · `dcat:downloadURL`

The URL of the downloadable file in a given format. E.g. CSV file or RDF file. The format is indicated by the distribution's dcterms:format and/or dcat:mediaType.

The URL of the downloadable file in a given format. E.g. CSV file or RDF file. The format is indicated by the distribution's dcterms:format and/or dcat:mediaType.

| | |
|---|---|
| Domain | [Distribution](classes.md#distribution) |
| Range | [rdfs:Resource](http://www.w3.org/2000/01/rdf-schema#Resource) |

### first

**IRI:** `http://www.w3.org/ns/dcat#first` · `dcat:first`

The first resource in an ordered collection or series of resources, to which the current resource belongs.

The first resource in an ordered collection or series of resources, to which the current resource belongs.

| | |
|---|---|
| Super-properties | [xhv:first](http://www.w3.org/1999/xhtml/vocab#first) |

### hadRole

**IRI:** `http://www.w3.org/ns/dcat#hadRole` · `dcat:hadRole`

The function of an entity or agent with respect to another entity or resource.

The function of an entity or agent with respect to another entity or resource.

| | |
|---|---|
| Domain | [prov:Attribution](http://www.w3.org/ns/prov#Attribution) *or* [Relationship](classes.md#relationship) |
| Range | [Role](classes.md#role) |

### has current version

**IRI:** `http://www.w3.org/ns/dcat#hasCurrentVersion` · `dcat:hasCurrentVersion`

This resource has a more specific, versioned resource with equivalent content [PAV].

This resource has a more specific, versioned resource with equivalent content [PAV].

| | |
|---|---|
| Super-properties | [pav:hasVersion](http://purl.org/pav/hasVersion) |

### has version

**IRI:** `http://www.w3.org/ns/dcat#hasVersion` · `dcat:hasVersion`

This resource has a more specific, versioned resource [PAV].

This resource has a more specific, versioned resource [PAV].

| | |
|---|---|
| Super-properties | [dcterms:hasVersion](http://purl.org/dc/terms/hasVersion), [prov:generalizationOf](http://www.w3.org/ns/prov#generalizationOf) |
| Inverse of | [dcat:isVersionOf](http://www.w3.org/ns/dcat#isVersionOf) |

### homepage

**IRI:** `http://xmlns.com/foaf/0.1/homepage` · `foaf:homepage`

This axiom needed so that Protege loads DCAT 3 without errors.

### in series

**IRI:** `http://www.w3.org/ns/dcat#inSeries` · `dcat:inSeries`

A dataset series of which the dataset is part.

A dataset series of which the dataset is part.

| | |
|---|---|
| Super-properties | [dcterms:isPartOf](http://purl.org/dc/terms/isPartOf) |
| Inverse of | [dcat:seriesMember](http://www.w3.org/ns/dcat#seriesMember) |

### landing page

**IRI:** `http://www.w3.org/ns/dcat#landingPage` · `dcat:landingPage`

A Web page that can be navigated to in a Web browser to gain access to the catalog, a dataset, its distributions and/or additional information.

A Web page that can be navigated to in a Web browser to gain access to the catalog, a dataset, its distributions and/or additional information.

| | |
|---|---|
| Super-properties | [foaf:page](http://xmlns.com/foaf/0.1/page) |
| Range | [foaf:Document](http://xmlns.com/foaf/0.1/Document) |

### last

**IRI:** `http://www.w3.org/ns/dcat#last` · `dcat:last`

The last resource in an ordered collection or series of resources, to which the current resource belongs.

The last resource in an ordered collection or series of resources, to which the current resource belongs.

| | |
|---|---|
| Super-properties | [xhv:last](http://www.w3.org/1999/xhtml/vocab#last) |

### media type

**IRI:** `http://www.w3.org/ns/dcat#mediaType` · `dcat:mediaType`

The media type of the distribution as defined by IANA.

The media type of the distribution as defined by IANA

| | |
|---|---|
| Super-properties | [dcterms:format](http://purl.org/dc/terms/format) |
| Domain | [Distribution](classes.md#distribution) |
| Range | [dcterms:MediaType](http://purl.org/dc/terms/MediaType) |

### packaging format

**IRI:** `http://www.w3.org/ns/dcat#packageFormat` · `dcat:packageFormat`

The package format of the distribution in which one or more data files are grouped together, e.g. to enable a set of related files to be downloaded together.

The package format of the distribution in which one or more data files are grouped together, e.g. to enable a set of related files to be downloaded together.

| | |
|---|---|
| Super-properties | [dcterms:format](http://purl.org/dc/terms/format) |
| Domain | [Distribution](classes.md#distribution) |
| Range | [dcterms:MediaType](http://purl.org/dc/terms/MediaType) |

### previous

**IRI:** `http://www.w3.org/ns/dcat#prev` · `dcat:prev`

The previous resource (before the current one) in an ordered collection or series of resources.

The previous resource (before the current one) in an ordered collection or series of resources.

| | |
|---|---|
| Super-properties | [xhv:prev](http://www.w3.org/1999/xhtml/vocab#prev) |
| Inverse of | [dcat:next](http://www.w3.org/ns/dcat#next) |

### previous version

**IRI:** `http://www.w3.org/ns/dcat#previousVersion` · `dcat:previousVersion`

The previous version of a resource in a lineage [PAV].

The previous version of a resource in a lineage [PAV].

| | |
|---|---|
| Super-properties | [prov:wasRevisionOf](http://www.w3.org/ns/prov#wasRevisionOf) |
| Inverse of | [dcat:nextVersion](http://www.w3.org/ns/dcat#nextVersion) |

### primaryTopic

**IRI:** `http://xmlns.com/foaf/0.1/primaryTopic` · `foaf:primaryTopic`

This axiom needed so that Protege loads DCAT 3 without errors.

| | |
|---|---|
| Used in | used in axioms of [Catalog Record](classes.md#catalogrecord) |

### qualified relation

**IRI:** `http://www.w3.org/ns/dcat#qualifiedRelation` · `dcat:qualifiedRelation`

Link to a description of a relationship with another resource.

Link to a description of a relationship with another resource.

| | |
|---|---|
| Domain | [Catalogued resource](classes.md#resource) |
| Range | [Relationship](classes.md#relationship) |

### record

**IRI:** `http://www.w3.org/ns/dcat#record` · `dcat:record`

A record describing the registration of a single dataset or data service that is part of the catalog.

A record describing the registration of a single dataset or data service that is part of the catalog.

| | |
|---|---|
| Domain | [Catalog](classes.md#catalog) |
| Range | [Catalog Record](classes.md#catalogrecord) |

### resource

**IRI:** `http://www.w3.org/ns/dcat#resource` · `dcat:resource`

A resource that is listed in the catalog.

A resource that is listed in the catalog.

| | |
|---|---|
| Super-properties | [dcterms:hasPart](http://purl.org/dc/terms/hasPart) |
| Sub-properties | [catalog](object-properties.md#catalog), [dataset](object-properties.md#dataset), [service](object-properties.md#service) |
| Domain | [Catalog](classes.md#catalog) |
| Range | [Catalogued resource](classes.md#resource) |
| Inverse of | [dcat:inCatalog](http://www.w3.org/ns/dcat#inCatalog) |

### serves dataset

**IRI:** `http://www.w3.org/ns/dcat#servesDataset` · `dcat:servesDataset`

A collection of data that this DataService can distribute.

A collection of data that this DataService can distribute.

| | |
|---|---|
| Domain | [Data service](classes.md#dataservice) |
| Range | [Dataset](classes.md#dataset) |

### service

**IRI:** `http://www.w3.org/ns/dcat#service` · `dcat:service`

A service that is listed in the catalog.

A service that is listed in the catalog.

| | |
|---|---|
| Super-properties | [resource](object-properties.md#resource) |
| Domain | [Catalog](classes.md#catalog) |
| Range | [Data service](classes.md#dataservice) |

### service end-point

**IRI:** `http://www.w3.org/ns/dcat#endpointURL` · `dcat:endpointURL`

The root location or primary endpoint of the service (a web-resolvable IRI).

The root location or primary endpoint of the service (a web-resolvable IRI).

| | |
|---|---|
| Domain | [Data service](classes.md#dataservice) |
| Range | [rdfs:Resource](http://www.w3.org/2000/01/rdf-schema#Resource) |

### theme

**IRI:** `http://www.w3.org/ns/dcat#theme` · `dcat:theme`

A main category of the resource. A resource can have multiple themes.

A main category of the resource. A resource can have multiple themes.

| | |
|---|---|
| Super-properties | [dcterms:subject](http://purl.org/dc/terms/subject) |

### theme taxonomy

**IRI:** `http://www.w3.org/ns/dcat#themeTaxonomy` · `dcat:themeTaxonomy`

The knowledge organization system (KOS) used to classify catalog's datasets.

The knowledge organization system (KOS) used to classify catalog's datasets.

| | |
|---|---|
| Domain | [Catalog](classes.md#catalog) |
| Range | [rdfs:Resource](http://www.w3.org/2000/01/rdf-schema#Resource) |
| sdo:rangeIncludes | owl:Ontology; skos:Collection; skos:ConceptScheme |

