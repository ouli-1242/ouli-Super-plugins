# Deep Modules — vocabulary for seams and interfaces

Absorbed from mattpocock's `codebase-design`. Loaded by the `tdd` skill when the shape of an interface is in question — designing or improving a module's interface, deciding where a seam goes, deepening a shallow module, making code testable. Use these terms exactly; don't substitute "component," "service," "API," or "boundary." Consistent language is the whole point.

## Glossary

**Module**: anything with an interface and an implementation. Deliberately scale-agnostic: a function, class, package, or tier-spanning slice. _Avoid_: unit, component, service.

**Interface**: everything a caller must know to use the module correctly — the type signature, but also invariants, ordering constraints, error modes, required configuration, and performance characteristics. _Avoid_: API, signature (too narrow — type-level surface only).

**Implementation**: what's inside the module, its body of code. Distinct from **Adapter**: a thing can be a small adapter with a large implementation (a Postgres repo) or a large adapter with a small implementation (an in-memory fake). Reach for "adapter" when the seam is the topic; "implementation" otherwise.

**Depth**: leverage at the interface — how much behavior a caller (or test) can exercise per unit of interface it must learn. **Deep** = lots of behavior behind a small interface; **shallow** = the interface is nearly as complex as the implementation.

**Seam** _(Michael Feathers)_: a place where you can alter behavior without editing in that place; the _location_ where a module's interface lives. Where to put the seam is its own design decision, distinct from what goes behind it. _Avoid_: boundary (overloaded with DDD's bounded context).

**Adapter**: a concrete thing that satisfies an interface at a seam — role (what slot it fills), not substance (what's inside).

**Leverage**: what callers get from depth. One implementation pays back across N call sites and M tests.

**Locality**: what maintainers get from depth — change, bugs, knowledge, and verification concentrate in one place. Fix once, fixed everywhere.

Relationships: a Module has exactly one Interface; Depth is a property of a Module measured against its Interface; a Seam is where that Interface lives; an Adapter sits at a Seam and satisfies the Interface; Depth produces Leverage for callers and Locality for maintainers.

## Deep vs shallow

Deep module = small interface + lots of implementation. Shallow module = large interface + little implementation — avoid:

```
Deep:                    Shallow (avoid):
┌──────────────┐         ┌──────────────────────┐
│sm interface  │         │  large interface     │
├──────────────┤         ├──────────────────────┤
│ complex      │         │  thin pass-through   │
│ logic hidden │         └──────────────────────┘
└──────────────┘
```

When designing an interface, ask: Can I reduce the number of methods? Simplify the parameters? Hide more complexity inside?

## Principles

- **Depth is a property of the interface, not the implementation.** A deep module may internally be small, mockable, swappable parts — they just aren't the interface. A module can have **internal seams** (private, used by its own tests) as well as the **external seam** at its interface.
- **The deletion test.** Imagine deleting the module. If complexity vanishes, it was a pass-through. If complexity reappears across N callers, it was earning its keep.
- **The interface is the test surface.** Callers and tests cross the same seam. If you want to test _past_ the interface, the module is probably the wrong shape.
- **One adapter means a hypothetical seam; two adapters mean a real one.** Don't introduce a seam unless something actually varies across it.

## Designing for testability

Good interfaces make testing natural — this is where seam confirmation and the test plan meet:

1. **Accept dependencies, don't create them.** `processOrder(order, paymentGateway)` tests at the seam; `processOrder(order)` that news up `StripeGateway()` inside forces testing past the interface.
2. **Return results, don't produce side effects.** `calculateDiscount(cart): Discount` asserts on a value; `applyDiscount(cart): void` mutates and forces verification through a side channel.
3. **Small surface area.** Fewer methods = fewer tests needed; fewer params = simpler test setup.

## Rejected framings

- **Depth as a ratio of implementation-lines to interface-lines** (Ousterhout's original): rewards padding the implementation. Use depth-as-leverage instead.
- **"Interface" = the `interface` keyword or a class's public methods**: too narrow — the interface includes every fact a caller must know.
- **"Boundary"**: overloaded with DDD's bounded context. Say **seam** or **interface**.
