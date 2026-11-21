# Classes

### Catalog

**IRI:** `http://www.w3.org/ns/dcat#Catalog` · `dcat:Catalog`

A curated collection of metadata about resources.

A curated collection of metadata about resources (e.g., datasets and data services in the context of a data catalog).

| | |
|---|---|
| Superclasses | [Dataset](classes.md#dataset) |
| Used in | in domain of [catalog](object-properties.md#catalog); in domain of [dataset](object-properties.md#dataset); in domain of [record](object-properties.md#record); in domain of [resource](object-properties.md#resource); in domain of [service](object-properties.md#service); in domain of [theme taxonomy](object-properties.md#themetaxonomy); in range of [catalog](object-properties.md#catalog) |

### Catalog Record

**IRI:** `http://www.w3.org/ns/dcat#CatalogRecord` · `dcat:CatalogRecord`

A record in a data catalog, describing the registration of a single dataset or data service.

A record in a data catalog, describing the registration of a single dataset or data service.

| | |
|---|---|
| Restrictions | [primaryTopic](object-properties.md#primarytopic) *only* [Catalogued resource](classes.md#resource); [primaryTopic](object-properties.md#primarytopic) *exactly* `1` |
| Used in | in range of [record](object-properties.md#record) |

### Catalogued resource

**IRI:** `http://www.w3.org/ns/dcat#Resource` · `dcat:Resource`

Resource published or curated by a single agent.

Resource published or curated by a single agent.

| | |
|---|---|
| Subclasses | [Data service](classes.md#dataservice), [Dataset](classes.md#dataset) |
| Used in | in domain of [qualified relation](object-properties.md#qualifiedrelation); in range of [resource](object-properties.md#resource); used in axioms of [Catalog Record](classes.md#catalogrecord) |

### Data service

**IRI:** `http://www.w3.org/ns/dcat#DataService` · `dcat:DataService`

A site or end-point providing operations related to the discovery of, access to, or processing functions on, data or related resources.

A site or end-point providing operations related to the discovery of, access to, or processing functions on, data or related resources.

| | |
|---|---|
| Superclasses | [Catalogued resource](classes.md#resource), [dctype:Service](http://purl.org/dc/dcmitype/Service) |
| Used in | in domain of [description of service end-point](object-properties.md#endpointdescription); in domain of [serves dataset](object-properties.md#servesdataset); in domain of [service end-point](object-properties.md#endpointurl); in range of [data access service](object-properties.md#accessservice); in range of [service](object-properties.md#service) |

### Dataset

**IRI:** `http://www.w3.org/ns/dcat#Dataset` · `dcat:Dataset`

A collection of data, published or curated by a single source, and available for access or download in one or more representations.

A collection of data, published or curated by a single source, and available for access or download in one or more representations.

| | |
|---|---|
| Superclasses | [Catalogued resource](classes.md#resource) |
| Subclasses | [Catalog](classes.md#catalog), [Dataset series](classes.md#datasetseries) |
| Used in | in domain of [distribution](object-properties.md#distribution); in range of [dataset](object-properties.md#dataset); in range of [serves dataset](object-properties.md#servesdataset) |

### Dataset series

**IRI:** `http://www.w3.org/ns/dcat#DatasetSeries` · `dcat:DatasetSeries`

A collection of datasets that are published separately, but share some common characteristics that groups them.

A collection of datasets that are published separately, but share some characteristics that group them.

| | |
|---|---|
| Superclasses | [Dataset](classes.md#dataset) |

### Distribution

**IRI:** `http://www.w3.org/ns/dcat#Distribution` · `dcat:Distribution`

A specific representation of a dataset. A dataset might be available in multiple serializations that may differ in various ways, including natural language, media-type or format, schematic organization, temporal and spatial resolution, level of detail or profiles (which might specify any or all of the above).

A specific representation of a dataset. A dataset might be available in multiple serializations that may differ in various ways, including natural language, media-type or format, schematic organization, temporal and spatial resolution, level of detail or profiles (which might specify any or all of the above).

| | |
|---|---|
| Used in | in domain of [access address](object-properties.md#accessurl); in domain of [byte size](datatype-properties.md#bytesize); in domain of [compression format](object-properties.md#compressformat); in domain of [download URL](object-properties.md#downloadurl); in domain of [media type](object-properties.md#mediatype); in domain of [packaging format](object-properties.md#packageformat); in range of [distribution](object-properties.md#distribution) |

### Relationship

**IRI:** `http://www.w3.org/ns/dcat#Relationship` · `dcat:Relationship`

An association class for attaching additional information to a relationship between DCAT Resources.

An association class for attaching additional information to a relationship between DCAT Resources.

| | |
|---|---|
| Used in | in domain of [hadRole](object-properties.md#hadrole); in range of [qualified relation](object-properties.md#qualifiedrelation) |

### Role

**IRI:** `http://www.w3.org/ns/dcat#Role` · `dcat:Role`

A role is the function of a resource or agent with respect to another resource, in the context of resource attribution or resource relationships.

A role is the function of a resource or agent with respect to another resource, in the context of resource attribution or resource relationships.

| | |
|---|---|
| Superclasses | [skos:Concept](http://www.w3.org/2004/02/skos/core#Concept) |
| Used in | in range of [hadRole](object-properties.md#hadrole) |

