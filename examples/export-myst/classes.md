# Classes

(cheesetopping)=
### Cheese topping ~~deprecated~~

**IRI:** `https://example.org/pizza#CheeseTopping` · `pizza:CheeseTopping`

Cheese.

| | |
|---|---|
| Superclasses | [Pizza topping](classes.md#pizzatopping) |

(food)=
### Food

**IRI:** `https://example.org/pizza#Food` · `pizza:Food`

Anything edible.

| | |
|---|---|
| Subclasses | [Pizza](classes.md#pizza), [Pizza base](classes.md#pizzabase), [Pizza topping](classes.md#pizzatopping) |
| Used in | in domain of [has calories](datatype-properties.md#hascalories) |

(meattopping)=
### Meat topping

**IRI:** `https://example.org/pizza#MeatTopping` · `pizza:MeatTopping`

| | |
|---|---|
| Superclasses | [Pizza topping](classes.md#pizzatopping) |
| Used in | used in axioms of [Vegetarian pizza](classes.md#vegetarianpizza) |

(pizza)=
### Pizza

**IRI:** `https://example.org/pizza#Pizza` · `pizza:Pizza`

A flat **baked** dish topped with ingredients.

| | |
|---|---|
| Superclasses | [Food](classes.md#food) |
| Restrictions | [has calories](datatype-properties.md#hascalories) *max* `1`; [has base](object-properties.md#hasbase) *some* [Pizza base](classes.md#pizzabase) |
| Disjoint with | [Pizza topping](classes.md#pizzatopping) |
| Instances | [Margherita](individuals.md#margherita) |
| Used in | in domain of [has base](object-properties.md#hasbase); in domain of [has topping](object-properties.md#hastopping); used in axioms of [Vegetarian pizza](classes.md#vegetarianpizza) |
| Examples | `Margherita` |

(pizzabase)=
### Pizza base

**IRI:** `https://example.org/pizza#PizzaBase` · `pizza:PizzaBase`

The bread base of a pizza.

| | |
|---|---|
| Superclasses | [Food](classes.md#food) |
| Used in | in range of [has base](object-properties.md#hasbase); in range of [Pizza](datatype-properties.md#name); used in axioms of [Pizza](classes.md#pizza) |

(pizzatopping)=
### Pizza topping

**IRI:** `https://example.org/pizza#PizzaTopping` · `pizza:PizzaTopping`

Something placed on a pizza.

| | |
|---|---|
| Superclasses | [Food](classes.md#food) |
| Subclasses | [Cheese topping](classes.md#cheesetopping), [Meat topping](classes.md#meattopping) |
| Disjoint with | [Pizza](classes.md#pizza) |
| Used in | in range of [has topping](object-properties.md#hastopping) |

(spicy_thing)=
### spicy_thing

**IRI:** `https://example.org/pizza#spicy_thing` · `pizza:spicy_thing`

(vegetarianpizza)=
### Vegetarian pizza

**IRI:** `https://example.org/pizza#VegetarianPizza` · `pizza:VegetarianPizza`

A pizza with no meat toppings.

| | |
|---|---|
| Equivalent to | [Pizza](classes.md#pizza) *and* (*not* ([has topping](object-properties.md#hastopping) *some* [Meat topping](classes.md#meattopping))) |

