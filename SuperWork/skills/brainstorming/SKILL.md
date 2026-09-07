---
name: brainstorming
description: Use when the user's request is underspecified - a vague feature idea, a new project, or a design question where requirements are not yet settled. Asks clarifying questions, presents a design, and gets explicit approval BEFORE any implementation. NOT for bug reports (use diagnosing-bugs), NOT when the user already said what to do and how (implement via tdd directly), NOT for stress-testing an already-settled plan (use grilling). 中文信号："加个功能" "我想做个…" "帮我设计…"。After design approval, the next step is writing-plans.
---

# Brainstorming Ideas Into Designs

Help turn ideas into fully formed designs and specs through natural collaborative dialogue. Classify how much process the request needs, work your path — understand context, refine the idea, present a design — and get your human partner's approval.

<HARD-GATE>
Do NOT invoke any implementation skill, write any code, scaffold any
project, or take any implementation action until you have told your
human partner what you intend and they have approved it. This applies
to EVERY task on EVERY path below — the ceremony scales with the task;
the approval gate never does.
</HARD-GATE>

## Three Paths

Before your first question, classify the request and say the
classification out loud — "this looks bounded, so I'll present a short
design here rather than write a spec" — so your human partner can
override it:

- **Spike** — a feasibility question ("can we...", "is it possible...",
  "quick and dirty is fine") whose output is an answer, not code you
  keep. Present the question and what you'll try in 2-3 sentences, get
  a nod, then find out as cheaply as correctness allows. No design
  doc, no spec file. Report findings as a recommendation; anything you
  built stays labeled throwaway.
- **Bounded** — a well-scoped change to code that already exists in
  this repo: a new flag, a small endpoint, a one-file fix.
  Understanding the kind of app is not enough — bounded means the flow
  you are changing is already here to read; if not, the task is not
  bounded. Ask the clarifying questions that matter, present a short
  design IN CHAT (a few sentences to a few short paragraphs), and
  STOP. Implementation starts only after your human partner says yes —
  a bounded task's approval is as hard a gate as an architectural one.
  No spec file, no implementation plan document.
- **Architectural** — new projects, new subsystems, changes that
  restructure how components fit together or alter interfaces others
  depend on. Follow the full process: questions, approaches, sectioned
  design, written spec, then the writing-plans skill.

When in doubt between two paths, take the heavier one. The ratchet is
one-way: hidden complexity discovered mid-task upgrades the path —
stop, say so, and step up. Nothing downgrades mid-task.

## Red Flags

| Thought | Reality |
|---------|---------|
| "This is too simple to need a design" | Simple means a short design, not no design. Two sentences in chat, then approval. |
| "I'll call it bounded and skip the spec" | Reaching for a label to skip work IS the doubt — take the heavier path. |
| "It's bounded and the design is obvious — I'll start while they read it" | The gate is the approval, not the design's length. Present, then stop until you hear yes. |
| "I understand this kind of app, so it's bounded" | Bounded measures the repo, not your familiarity. A new project has no existing flow — it is architectural. |
| "The spike works, so I'll keep the code" | A spike's output is an answer. Keeping the code is a new request — classify it. |
| "It grew, but I'm almost done" / "they approved the spike, so the follow-up is approved too" | Hidden complexity upgrades the path mid-task — stop and say so. Each task gets its own classification and its own approval. |

## Checklist

Classify first, announce the path, then create a task for each item on
your path and complete them in order.

**Spike:**
1. **Explore project context** — enough to frame the probe
2. **Present question + probe plan** — 2-3 sentences
3. **Get approval** — a nod is enough
4. **Investigate** — as cheaply as correctness allows
5. **Report findings** — a recommendation; label anything built as throwaway

**Bounded:**
1. **Explore project context** — check files, docs, recent commits
2. **Ask clarifying questions** — one at a time, the ones that matter
3. **Present short design in chat** — approach, files touched, testing
4. **Get approval** — STOP and wait for an explicit yes; presenting the design and starting in the same breath is skipping the gate
5. **Implement** — call the Skill tool with "tdd"; no plan document

**Architectural:**
1. **Explore project context** — check files, docs, recent commits
2. **Offer the visual companion just-in-time** — NOT upfront; only the first time a question would genuinely be clearer shown than described (see Visual Companion below)
3. **Ask clarifying questions** — one at a time, understand purpose/constraints/success criteria
4. **Propose 2-3 approaches** — with trade-offs and your recommendation
5. **Present design** — in sections scaled to their complexity, get user approval after each section
6. **Write design doc** — save to `docs/superwork/specs/YYYY-MM-DD-<topic>-design.md` with a status line `**Status:** draft` at the top, and commit
7. **Spec self-review** — quick inline check for placeholders, contradictions, ambiguity, scope
8. **User reviews written spec** — ask user to review the spec file before proceeding; on approval update the status line to `**Status:** approved` and commit
9. **Transition to implementation** — call the Skill tool with "writing-plans" to create the implementation plan

See `references/process-flow.md` for the decision graph, and `references/design-process.md` for the how-to depth of each architectural step.

**Terminal states are path-bound.** Architectural: the ONLY skill invoked after brainstorming is writing-plans — never any other implementation skill. Bounded: after approval, call the Skill tool with "tdd" and implement directly; no plan document. Spike: the terminal state is a reported recommendation.

## After the Design (architectural path)

**Documentation:** Write the validated design (spec) to
`docs/superwork/specs/YYYY-MM-DD-<topic>-design.md`, starting with
`**Status:** draft`; on user approval update to `**Status:** approved`
(same commit). User preferences for spec location override this
default. Commit the design document.

**User Review Gate:** After the spec self-review passes, ask the user
to review the written spec before proceeding:

> "Spec written and committed to `<path>`. Please review it and let me know if you want to make any changes before we start writing out the implementation plan."

Wait for the response; on requested changes, fix them and re-run the review loop. Proceed only once the user approves.

**Implementation:** Call the Skill tool with "writing-plans" to create
a detailed implementation plan. Do NOT invoke any other skill —
writing-plans is the next step.

## Visual Companion

A browser-based companion for showing mockups, diagrams, and visual
options during brainstorming. Available as a tool — not a mode.

**Offering (just-in-time):** Do NOT offer it upfront. Wait until a
question would genuinely be clearer shown than told — a real mockup /
layout / diagram question, not merely a UI *topic*. Offer it as its
own message and wait; on acceptance start the server with `--open`,
on decline continue text-only and don't offer again.

**Per-question decision:** Decide FOR EACH QUESTION whether to use the
browser or the terminal. The test: would the user understand this
better by seeing it than reading it? Browser for visual content —
mockups, wireframes, layout comparisons, architecture diagrams.
Terminal for text — requirements, conceptual choices, tradeoff lists,
scope decisions.

Before using it, read the detailed guide: `visual-companion.md` (in
this skill's directory).
