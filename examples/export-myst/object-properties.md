# Object properties

(hasbase)=
### has base

**IRI:** `https://example.org/pizza#hasBase` · `pizza:hasBase`

| | |
|---|---|
| Super-properties | [has ingredient](object-properties.md#hasingredient) |
| Domain | [Pizza](classes.md#pizza) |
| Range | [Pizza base](classes.md#pizzabase) |
| Characteristics | Functional |
| Used in | used in axioms of [Pizza](classes.md#pizza) |

(hasingredient)=
### has ingredient

**IRI:** `https://example.org/pizza#hasIngredient` · `pizza:hasIngredient`

Any ingredient.

| | |
|---|---|
| Sub-properties | [has base](object-properties.md#hasbase) |
| Characteristics | Transitive |

(hastopping)=
### has topping

**IRI:** `https://example.org/pizza#hasTopping` · `pizza:hasTopping`

Relates a pizza to its toppings.

| | |
|---|---|
| Domain | [Pizza](classes.md#pizza) |
| Range | [Pizza topping](classes.md#pizzatopping) |
| Inverse of | [is topping of](object-properties.md#istoppingof) |
| Used in | used in axioms of [Vegetarian pizza](classes.md#vegetarianpizza) |

(istoppingof)=
### is topping of

**IRI:** `https://example.org/pizza#isToppingOf` · `pizza:isToppingOf`

| | |
|---|---|
| Inverse of | [has topping](object-properties.md#hastopping) |

