# Competency questions

### CQ1. Which pizzas have a meat topping?

**Status:** answerable (1 results)

**Terms:** [has topping](object-properties.md#hastopping), [Meat topping](classes.md#meattopping)

**Expected answer:** The pepperoni pizza.

From the menu-planning use case.

```sparql
SELECT ?pizza WHERE { ?pizza pizza:hasTopping ?t . ?t a pizza:MeatTopping . }
```

### CQ2. What kinds of base can a pizza have?

**Status:** answerable (2 results)

**Terms:** [has base](object-properties.md#hasbase)

```sparql
SELECT DISTINCT ?base WHERE { ?p pizza:hasBase ?base . }
```

### CQ3. Which pizzas contain fish?

**Status:** not answerable (0 results)

**Terms:** [has topping](object-properties.md#hastopping)

The ontology has no fish toppings yet, so this question is not answerable.

```sparql
SELECT ?pizza WHERE { ?pizza pizza:hasTopping ?t . ?t a pizza:FishTopping . }
```

### CQ4. Is every pizza made of food?

**Status:** answerable (1 results)

**Terms:** [Food](classes.md#food), [Pizza](classes.md#pizza)

```sparql
ASK { pizza:Pizza rdfs:subClassOf pizza:Food }
```

### CQ5. How many calories does a pizza have?

**Status:** not tested

**Terms:** [has calories](datatype-properties.md#hascalories)

### CQ1. Which toppings exist?

**Status:** answerable (2 results)

**Terms:** [Pizza topping](classes.md#pizzatopping)

**Expected answer:** Meat and cheese toppings

```sparql
SELECT ?t WHERE { ?t rdfs:subClassOf pizza:PizzaTopping }
```

### CQ2. Broken query?

**Status:** query error

```sparql
SELECT WHERE {
```

Error: Expected SelectQuery, found 'WHERE' (at char 7), (line:1, col:8)

