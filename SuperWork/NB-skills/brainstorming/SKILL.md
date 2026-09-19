---
name: brainstorming
description: "Use when the user's request is underspecified - a vague feature idea, a new project, or a design question where requirements are not yet settled. Asks clarifying questions, presents a design, and gets explicit approval BEFORE any implementation. NOT for bug reports (diagnosing-bugs), NOT when the user already said what to do and how (tdd), NOT for a stress-tested settled plan (grilling). 中文信号：「加个功能」「我想做个…」「帮我设计…」「这个需求怎么做」。"
---
# Brainstorming Ideas Into Designs

## Purpose

Turn an underspecified idea into an approved design through collaborative dialogue — and ensure nothing is implemented before explicit approval.

## When to Use / Not Use

- Use: vague feature idea, new project, design question with unsettled requirements.
- Do NOT use: bug reports (diagnosing-bugs); the user already said what and how (tdd); stress-testing a settled plan (grilling).

## Capability Boundary

- CAN: classify the request's weight, ask the clarifying questions that matter, present designs at matching depth, write and register a spec.
- CANNOT: write production code, scaffold a project, or take any implementation action before approval.
- Depends on: doc-index (persistence protocol), writing-plans (architectural successor), tdd (bounded successor).

## Input Contract

- Required: the user's idea or request.
- Optional: repo context, existing specs, templates, prior decisions (`决策记录.md`).
- If incomplete: ask the questions that matter, one at a time. If the user is unavailable, stop at the approval gate — never self-approve.

## Output Contract

- **Spike**: a recommendation in chat; optionally a one-pager at `docs/调研/YYYY-MM-DD-<topic>.md` (labeled throwaway), registered in 文档导航. Anything built stays labeled throwaway.
- **Bounded**: a short design in chat (approach, files touched, testing) + an explicit "yes".
- **Architectural**: a spec at `docs/设计/YYYY-MM-DD-<topic>-design.md`, first content line `**Status:** draft`, updated to `**Status:** approved` on approval, committed and registered in 文档导航. No placeholders, no contradictions. User-specified locations override.

## Constraints and Prohibitions

```
<HARD-GATE> No implementation action until you have presented what you
intend and the user approved it. The ceremony scales with the task; the
gate never does. </HARD-GATE>
```

- Announce the path classification (Spike / Bounded / Architectural) before the first question, so the user can override.
- **The ratchet is one-way**: hidden complexity discovered mid-task upgrades the path — stop, say so, step up. Nothing downgrades mid-task.
- When in doubt between two paths, take the heavier one.
- **Terminal states are path-bound**: Architectural → only writing-plans next; Bounded → tdd directly, no plan document; Spike → a reported recommendation, no spec file.
- Prohibited: presenting a design and starting implementation in the same breath; treating a nod at the classification as design approval.

## Acceptance Criteria

- The design was explicitly approved by the user before any implementation.
- Architectural: spec on disk, registered in 文档导航, status line accurate.
- Self-check: did I stop after presenting the design? Is the spec free of placeholders and ambiguity?

## Failure and Escalation

- Design rejected → revise and re-present; do not iterate silently.
- Hidden complexity discovered mid-task → stop, announce the path upgrade.
- Questions exhausted without clarity → surface what is unresolved; do not guess.
- User unavailable at the gate → stop and wait; the gate has no self-serve override.

## Cost and Latency Budget

- Bounded: ≤ 5 clarifying questions, short design in chat.
- Architectural: question rounds until purpose/constraints/success criteria are clear; design presented in sections.
- Exploration ≤ 10 tool calls before the first question. Spike: as cheap as correctness allows.

## Examples

- Positive (Bounded): 3 questions → short design in chat → STOP → user says yes → tdd.
- Negative: presenting the design and writing code in the same turn — the gate was skipped regardless of design quality.
- Edge: "can we even do X quickly?" → Spike; the deliverable is an answer, not code to keep.

## Evaluation and Observability

- Metrics: HARD-GATE violations (target 0), first-pass design approval rate, mid-task path re-classifications.
- Log: every gate violation to `docs/日志/` with the task context.

## References (L2, load on demand)

- Decision graph for the three paths: `references/process-flow.md`
- How-to depth for each architectural step: `references/design-process.md`
- Skip-the-gate rationalizations: `references/red-flags.md`
