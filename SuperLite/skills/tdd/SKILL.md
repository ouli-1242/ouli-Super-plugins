---
name: tdd
description: Use when writing or about to write production code - any feature implementation or bug fix. "implement", "开写", "实现这个功能", "red-green-refactor", integration tests. If requirements are not yet confirmed, ask the user before coding.
---

# Test-Driven Development

TDD is the red → green loop. This skill is the reference that makes that loop produce tests worth keeping: what a good test is, where tests go, the anti-patterns, and the rules of the loop. Every section applies on every cycle — consult them before and during the loop, not after.

If requirements are not yet confirmed, stop and ask the user before writing any code.

When exploring the codebase, read `CONTEXT.md` (if it exists) so test names and interface vocabulary match the project's domain language, and respect ADRs in the area you're touching.

## What a good test is

Tests verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't. A good test reads like a specification — "user can checkout with valid cart" tells you exactly what capability exists — and survives refactors because it doesn't care about internal structure.

See [tests.md](tests.md) for examples and [mocking.md](mocking.md) for mocking guidelines.

## Seams — where tests go

A **seam** is the public boundary you test at: the interface where you observe behavior without reaching inside. Tests live at seams, never against internals.

**Test only at pre-agreed seams.** Before writing any test, write down the seams under test and confirm them with the user. No test is written at an unconfirmed seam. You can't test everything — agreeing the seams up front is how testing effort lands on the critical paths and complex logic instead of every edge case.

Ask: "What's the public interface, and which seams should we test?"

When the shape of that interface is itself in question — how deep the module is, where the seam belongs, what the interface should expose — agree the module boundary with the user before testing anything: sketch the public surface in chat, confirm it, then treat it as the seam. Don't write tests against an interface that is still being reshaped.

## Anti-patterns

- **Implementation-coupled** — mocks internal collaborators, tests private methods, or verifies through a side channel (querying the database instead of using the interface). The tell: the test breaks when you refactor but behavior hasn't changed.
- **Tautological** — the assertion recomputes the expected value the way the code does (`expect(add(a, b)).toBe(a + b)`, a snapshot derived by hand the same way, a constant asserted equal to itself), so it passes by construction and can never disagree with the code. Expected values must come from an independent source of truth — a known-good literal, a worked example, the spec.
- **Horizontal slicing** — writing all tests first, then all implementation. Bulk tests verify _imagined_ behavior: you test the _shape_ of things rather than user-facing behavior, the tests go insensitive to real changes, and you commit to test structure before understanding the implementation. Work in **vertical slices** instead — one test → one implementation → repeat, each test a **tracer bullet** that responds to what the last cycle taught you.

## Rules of the loop

- **Red before green.** Write the failing test first, then only enough code to pass it. Don't anticipate future tests or add speculative features.
- **One slice at a time.** One seam, one test, one minimal implementation per cycle.
- **Never start implementation on main/master** without explicit user consent — create or switch to a feature branch first.
- **Refactoring is not part of the loop.** It belongs to the review stage, not the red → green implementation cycle. When the loop is finished, call the Skill tool with "code-review".

## The Iron Law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

If you wrote code before the failing test existed, delete it and start over — don't keep it "as reference", don't adapt it while writing tests. Implement fresh from tests.

**Exceptions (ask the user first):** throwaway prototypes, generated code, configuration files. "Just this once" is not an exception — it's rationalization.

## Watch It Fail — mandatory

If you didn't watch the test fail, you don't know it tests the right thing:

- Test **passes** immediately → you're testing existing behavior; fix the test.
- Test **errors** → fix the error and re-run until it fails for the *right* reason (feature missing, not typo).
- Test **fails for the right reason** → only now write the minimal code.

The same gate applies after the fix: watch it pass, watch the rest of the suite stay green.

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Too simple to test" | Simple code breaks. A test takes 30 seconds. |
| "I'll test after" | Tests written after pass immediately, which proves nothing — you never watched them fail, so you never proved they can catch the bug. |
| "Already manually tested" | Manual testing is ad-hoc: no record of what you covered, no way to re-run it when code changes. |
| "Deleting X hours of work is wasteful" | Sunk cost. Keeping code you can't trust is the real waste. |
| "Need to explore first" | Fine. Throw the exploration away, start with TDD. |
| "TDD will slow me down" | TDD is the pragmatic path: catches bugs before commit, prevents regressions, makes refactoring safe. "Pragmatic" shortcuts mean debugging later — slower, not faster. |
