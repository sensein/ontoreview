# Example

`toy_onto.ttl` is a small OWL ontology (soil sensing) with a few deliberate problems: a missing
license and creators, terms without definitions, a property without domain and range. Use it to try
the checks, the Quality issues page and the generated docs.

```bash
ontoreview ui                                   # then pick examples/toy_onto.ttl and press Build docs
ontoreview build examples/toy_onto.ttl -o examples/site/toy
ontoreview fix list examples/toy_onto.ttl
```

Generated output is not kept in the repository. To build the full set of example sites from the test
fixtures (pizza, PROV-O, FOAF, SKOS, DCAT, LinkML, CDI, …):

```bash
python scripts/build_examples.py                # writes examples/site/
python -m http.server 8000 -d examples/site     # then open http://127.0.0.1:8000/
```
