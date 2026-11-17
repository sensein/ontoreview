# Annotation properties

### role (property)

**IRI:** `http://www.w3.org/ns/org#roleProperty` · `org:roleProperty`

This is a metalevel property which is used to annotate an `org:Role` instance with a sub-property of `org:memberOf` that can be used to directly indicate the role for easy of query. The intended semantics is a Membership relation involving the Role implies the existence of a direct property relationship through an inference rule of the form:  `{ [] org:member ?p; org:organization ?o; org:role [org:roleProperty ?r] } -> {?p ?r ?o}`.

| | |
|---|---|
| Domain | [Role](classes.md#role) |
| Range | [rdf:Property](http://www.w3.org/1999/02/22-rdf-syntax-ns#Property) |

