---
name: tdd
description: "Use when writing or about to write production code for an approved task - any feature implementation or bug fix. \"开写\", \"实现这个功能\", \"TDD\", \"red-green-refactor\". NOT when requirements are still unclear (brainstorming first), NOT when a written multi-task plan is being executed (executing-plans orchestrates that and calls this per task), NOT for work that needs a plan written first (writing-plans)."
---
# Test-Driven Development

## Purpose

Keep the red → green loop honest: tests worth keeping, written first, at seams agreed with the user.

## When to Use / Not Use

- Use: writing or about to write production code for an approved task — any feature or bug fix.
- Do NOT use: requirements unclear (brainstorming); a written plan is being executed (executing-plans calls this per task); work that needs a plan first (writing-plans).

## Capability Boundary

- CAN: choose seams, write failing tests, drive minimal implementations, guard the loop.
- CANNOT: write production code before a failing test exists; test at unconfirmed seams.
- Depends on: the project's test runner; git; `docs/测试.md` (project seams/coverage/untested list), `技术依据.md` glossary and `决策记录.md` for vocabulary and constraints when exploring.

## Input Contract

- Required: an approved task (feature description or bug with a clear fix path).
- Optional: project seam declarations (`docs/测试.md`).
- Missing behavior: requirements unclear → stop, route to brainstorming. If requirements are not confirmed, do not write code.

## Output Contract

- Working code delivered through vertical slices, each preceded by a failing test at a confirmed seam; every fix ships with a regression test; tests read like specifications of public behavior and survive refactors.

## Constraints and Prohibitions

```
THE IRON LAW
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

- **Test only at pre-agreed seams.** Before writing any test, write down the seams and confirm them with the user (consult `docs/测试.md` if present). When the interface's shape itself is in question, agree the module boundary with the user first — never test an interface still being reshaped (vocabulary: `deep-modules.md`).
- **Watch it fail — mandatory.** Passes immediately → you are testing existing behavior; fix the test. Errors → fix until it fails for the right reason. Only then write minimal code. After the fix: watch it pass, and watch the rest of the suite stay green.
- **One slice at a time**: one seam, one test, one minimal implementation per cycle. Never anticipate future tests or add speculative features.
- Refactoring is not part of the loop — when the loop is finished, hand the change to code-review.
- Code written before the failing test existed gets deleted, not kept "as reference".
- Exceptions (throwaway prototypes, generated code, config files) require asking the user first. "Just this once" is not an exception.
- Anti-patterns that void the test: **implementation-coupled** (mocks internals; breaks under refactor while behavior is unchanged); **tautological** (expected value recomputed the way the code computes it — expected values must come from an independent source of truth); **horizontal slicing** (all tests first, then all implementation — tests imagined behavior).
- **Rationalizations kill the loop** — "too simple to test", "I'll test after", "already manually tested" are red flags with known counters: `references/rationalizations.md`.
- Prohibited: starting implementation on main/master without explicit consent.

## Acceptance Criteria

- Every production change is preceded in history by a failing test run for the right reason.
- Self-check: can I name the seam each test lives at and who agreed to it? Did I watch every test fail before making it pass?

## Failure and Escalation

- No test runner in the project → stop and ask how to proceed before writing code.
- Bug surfaces mid-loop → diagnosing-bugs, not an untested fix.
- Test cannot be made deterministic → stop and raise; do not ship a flaky guard.

## Cost and Latency Budget

- Cycles are small by construction; more than ~10 red-green cycles without a check-in → report progress and re-scope with the user.

## Examples

- Positive: write `checkout with empty cart rejects` → watch it fail with "cart validation missing" → minimal guard → green → commit.
- Negative: `expect(add(a,b)).toBe(a+b)` — tautology; passes by construction, proves nothing.
- Edge: exploration spike is legitimate — throw the exploration away and start the real change with TDD.

## Evaluation and Observability

- Metrics: production commits without a preceding failing test (target 0), tests invalidated by refactors, tautological tests caught in review.
- Log: seam agreements recorded in the task/commit; violations to `docs/日志/`.

## References (L2, load on demand)

- What a good test is, with examples: `tests.md`
- Mocking guidelines: `mocking.md`
- Deep module / seam vocabulary: `deep-modules.md`
- Excuses that defeat the Iron Law, with counters: `references/rationalizations.md`
