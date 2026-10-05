---
name: code-review
description: "Use when reviewing changes before merge or delivery - the user asks to review a branch, PR, or work-in-progress changes (\"review\", \"评审一下这次的改动\", \"检查下改动\"), or the change is large enough that review is mandatory before merging to mainline: core module touched, diff >= 15 files, or new engine/API/data-model contracts. Typically after implementation (tdd) and before declaring completion."
---
# Code Review

## Purpose

Produce a two-axis review of a diff — Standards conformance and Spec fidelity — kept deliberately separate so neither axis masks the other.

## When to Use / Not Use

- Use: reviewing a branch/PR/work-in-progress diff on request; mandatory review thresholds (core module touched / diff ≥ 15 files / new engine, API, or data-model contracts).
- Do NOT use as a substitute for verification — review first, then verify (verification-before-completion).

## Capability Boundary

- CAN: pin the diff base, locate spec and standards sources, run both axes (parallel sub-agents or sequential, kept separate), aggregate, persist the report.
- CANNOT: merge or re-rank findings across axes; skip the smell baseline.
- Depends on: git; `docs/规范.md` / `CODING_STANDARDS.md` / `CONTRIBUTING.md` when present; `references/smell-baseline.md` (always applies); sub-agent tool (optional).

## Input Contract

- Required: the diff's fixed point (commit SHA, branch, tag, `HEAD~5`, …).
- Optional: a spec path.
- Missing behavior: no fixed point given → ask for it before anything else. Spec unfindable after the search chain (`docs/设计/`, `docs/`, `specs/`, `.scratch/`, commit-message refs) → the Spec axis reports "no spec available"; review proceeds.

## Output Contract

- A report with exactly two sections — `## Standards` and `## Spec` — each kept verbatim from its axis, followed by a one-line summary per axis: total findings and the worst issue within THAT axis. No single winner across axes.
- Severity within each axis: **Critical** (broken behavior, security, spec violation — fix immediately), **Important** (fix before declaring done), **Minor** (fix if cheap, else note).
- Report persisted to `docs/审查/YYYY-MM-DD-<审查主题>.md` and registered in 文档导航 (when a project exists).

## Constraints and Prohibitions

- Pin the fixed point first: `git diff <fixed-point>...HEAD` (three-dot, merge-base). Confirm the ref resolves and the diff is non-empty BEFORE spawning any sub-agent.
- Standards sources: `docs/规范.md` first, then `CODING_STANDARDS.md` / `CONTRIBUTING.md`; the smell baseline goes to the Standards sub-agent in full regardless (it has no other access).
- The two axes never merge, never re-rank against each other — a change can pass one and fail the other.
- **Findings reception (inline in this pack):** before implementing any finding, verify it against the codebase first and push back with technical reasoning when it is wrong. Never implement findings blindly; never agree performatively.
- Prohibited: presenting a merged single report.

## Acceptance Criteria

- Both axes produced (or a stated "no spec available"), report on disk and registered, severities assigned within each axis.
- Self-check: did the diff get pinned and proven non-empty first? Are the two reports unmerged?

## Failure and Escalation

- Ref won't resolve / empty diff → report and stop; ask for the correct fixed point.
- No sub-agent tool → run both axes yourself sequentially, keeping the reports strictly separate.
- Findings disputed → verification and pushback are part of this skill's reception constraints.

## Cost and Latency Budget

- Two sub-agent dispatches (or two sequential passes); one aggregation; one persistence write. Over budget: deliver the two raw reports without extra polishing.

## Examples

- Positive: Standards finds "magic numbers, no tests on new module" (Important); Spec finds "requirement 3 not implemented" (Critical) — both reported, Critical drives the work order within its axis.
- Negative: merging both axes into one ranked list "by importance" — the axes exist so neither masks the other.
- Edge: user says there is no spec → Spec axis reports "no spec available"; the Standards axis still runs.

## Evaluation and Observability

- Metrics: findings later verified as wrong (false-positive rate per axis), Critical findings fixed before merge, reports persisted (target 100%).
- Log: the persisted report IS the record; disputed findings and pushbacks noted in chat or the report.

## References (L2, load on demand)

- Fixed smell baseline for the Standards axis: `references/smell-baseline.md`
- Sub-agent prompt templates: `references/subagent-prompts.md`
- Rationale for two axes: `references/why-two-axes.md`
