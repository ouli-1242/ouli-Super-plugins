---
name: domain-modeling
description: "Use when the user wants to pin down domain terminology or a ubiquitous language, or record an architectural decision - \"统一术语\", \"这个词到底什么意思\", \"记个架构决策\", \"ADR\". Actively builds and sharpens the project's domain model: decisions accumulate in docs/决策记录.md (D-NNN, six-part), the glossary lives in docs/技术依据.md. NOT for general design discussion - only for language and decision records. Pairs with grilling's With-Docs Mode; consumed by tdd and diagnosing-bugs."
---
# Domain Modeling

## Purpose

Actively build and sharpen the project's domain model: challenge terms as they drift, capture decisions when they qualify, and keep the glossary and decision record current in the moment.

## When to Use / Not Use

- Use: pinning down terminology/ubiquitous language; recording an architectural decision; explicitly requested alongside grilling (With-Docs Mode).
- Do NOT use: general design discussion; merely reading `技术依据.md` for vocabulary — that's a habit any skill can have, not this skill.

## Capability Boundary

- CAN: challenge term drift, sharpen fuzzy language, probe boundaries with scenarios, cross-check claims against code, write glossary entries and ADRs.
- CANNOT: let the glossary become a spec/scratch-pad; record decisions that don't meet the three-condition bar.
- Depends on: `docs/技术依据.md` (glossary section), `docs/决策记录.md` (D-NNN, six-part); formats in `references/ADR-FORMAT.md` / `references/CONTEXT-FORMAT.md`.

## Input Contract

- Required: the term or decision under discussion.
- Optional: existing glossary/decisions; the relevant code.
- Missing behavior: files don't exist → create lazily, only when the first term/decision actually resolves; register new files in 文档导航.

## Output Contract

- Glossary entries in `docs/技术依据.md` (pure language: terms, definitions, boundaries — zero implementation detail), updated inline the moment a term resolves.
- Decision entries in `docs/决策记录.md` as D-NNN in the six-part ADR format, appended only for qualifying decisions.
- Multi-context repos: follow the per-context map declared in 文档导航; otherwise one `技术依据.md` and context tags on decision titles (e.g. `[ordering]`).

## Constraints and Prohibitions

- **The glossary is a glossary and nothing else** — not a spec, scratch pad, or implementation-decision dump.
- Update the glossary inline as terms resolve; never batch them up.
- **Record a decision only when all three hold:** (1) hard to reverse; (2) surprising without context ("why did they do it this way?"); (3) the result of a real trade-off with genuine alternatives. Any one missing → skip.
- Active moves during the session: challenge glossary conflicts immediately ("your glossary defines cancellation as X, but you mean Y — which is it?"); sharpen vague terms ("'account' — the Customer or the User?"); stress-test relationships with concrete edge-case scenarios; cross-reference claims with the code and surface contradictions ("the code cancels whole Orders, but you just said partial cancellation is possible — which is right?").

## Acceptance Criteria

- Glossary and decisions reflect the session's resolved language and qualifying decisions, in the canonical formats, registered in 文档导航.
- Self-check: does any glossary entry contain implementation detail? Was any decision recorded that fails one of the three conditions?

## Failure and Escalation

- Term conflict unresolvable in session → record both readings as an open question, don't pick silently.
- User declines to record a qualifying decision → note the refusal in chat; do not write the file.

## Cost and Latency Budget

- Inline capture, no batching; a decision entry is a short six-part record, not an essay. Over budget: capture the term/decision in one line and refine later.

## Examples

- Positive: user says "partial cancellation is possible" while code only cancels whole orders → contradiction surfaced → term/behavior clarified → glossary updated in the same turn.
- Negative: glossary entry "Cancellation uses the CancelledOrder aggregate with a state machine" — implementation detail leaked into language.
- Edge: a reversible naming choice with no real trade-off → not recorded as a D-NNN decision.

## Evaluation and Observability

- Metrics: later sessions contradicting the glossary (drift rate), decisions recorded that fail the three-condition bar (target 0), terms captured inline vs batched.
- Log: glossary/决策记录 are the observability record; 文档导航 registration is the completeness signal.

## References (L2, load on demand)

- Six-part ADR format for `决策记录.md`: `references/ADR-FORMAT.md`
- Per-context map format for multi-context repos: `references/CONTEXT-FORMAT.md`
