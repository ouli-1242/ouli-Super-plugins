---
name: grilling
description: Use when the user wants their plan, decision, or idea stress-tested through relentless questioning - "grill me", "帮我挑刺", "这个方案行不行", "stress-test this plan", "challenge my thinking". Interviews in rounds until no assumption is left silently standing. NOT for gathering requirements for new work whose design doesn't exist yet (brainstorming first). When the user explicitly asks for the documented variant ("grill-with-docs", "/grill-with-docs", "追问并落盘 ADR"), use this skill's With-Docs Mode.
---

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled — the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Each question should be formatted like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Each round the user answers reshapes the tree — settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it — don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report — ask the rest of the frontier now. The _decisions_ are the user's — put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.

## With-Docs Mode (explicit request only)

When the user explicitly asks for the documented variant — names "grill-with-docs", "/grill-with-docs", or asks for the interview to also produce docs (decisions / glossary) — call the Skill tool a second time, with "domain-modeling", and keep both active for the whole session: grilling drives the rounds above; domain-modeling captures the terminology and decisions (`技术依据.md` glossary + `决策记录.md`) as they crystallise.

Never enable this mode on an ordinary grill request — the doc-writing side effects happen only on explicit request.
