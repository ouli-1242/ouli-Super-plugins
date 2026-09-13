# Retro Mode — Session Retrospective Checklist

Loaded by `writing-skills` Retro Mode (explicit user request only: "复盘", "retro", "这次会话哪里可改进").

Goal: improve the coding agent's **environment** so future runs are better — not to relitigate the code or re-review the diff (that is `code-review`). The output is a severity-ordered list of environment improvements; each approved item is then implemented through the parent skill's discipline (RED-GREEN for the edit, SDO for the description).

## Process

1. **Read the primary sources** for the session the user names (default: the current session). On-disk artifacts first — `docs/日志/`, `docs/审查/` reports, `docs/交接/` handoffs, plan checkboxes, `git log` — then conversation context. These artifacts are the SuperWork spine; raw session logs are secondary.
2. **Mine candidates** in the seven categories below. Each candidate states its own _use when_ signal — a category with no signal match yields no candidate, not a forced one.
3. **Present candidates in order of severity.** For each: what to change, where it lives (steering file / skill / automated check / doc pointer), and the failure it would have prevented this session.
4. **Implement approved items through the parent skill's discipline.** An AGENTS.md line, a review rule, or a skill edit is an edit to an existing skill — the Iron Law applies. Register any new doc per `doc-index` (discipline #4).

## The seven categories

- **Navigation** — how easy was it for the agent to find the right files? Hidden dependencies between files? Would a navigation pointer (a line in the doc index or a steering file) have cut the search? _Use when_ the session took a long time to find a piece of information.
- **Automated checks** — is there a check that would have caught the error the agent made? Linting, typing, tests, `validate.ps1` extensions, filesystem linters. _Use when_ the agent made a mistake a machine could have caught.
- **Coding standards** — should the reviewer get a new rule to enforce, or an existing rule removed/clarified? These feed the Standards axis of `code-review`. _Use when_ the reviewer failed to catch a mistake.
- **Always-loaded steering** (global `AGENTS.md` / `CLAUDE.md`) — any instruction that should move out of always-loaded context into a skill, a review rule, or an automated check? _Use when_ a steering file is large or unwieldy. Every line there pays context load every turn (`references/agent-docs.md` → The two loads).
- **Tool economy** — expensive tool calls that could be streamlined? Custom tooling (CLIs, MCPs) that is token-inefficient? _Use when_ the session burned tokens on a call that returned little.
- **No-ops** — instructions in steering files that do not change the agent's behavior versus its defaults. The test is model-relative: run the document, don't debate it. When a sentence fails, delete the whole sentence. _Use when_ steering files are large.
- **Information access** — crucial information the agent did not have: tee dev-server logs to disk, provide read-only access to third-party services, export the missing state. _Use when_ the agent was blind to something it needed.

## Ranking principle: implementation vs review

All work runs in two roles. The **implementation** role carries the most context pressure — exploration, writing code, debugging failures. The **review** role carries the least — it receives a diff, no exploration, rarely writes code. Therefore: standards enforcement belongs to review, not implementation; mechanically-catchable mistakes belong to automated checks, not to either role's memory; navigation belongs in pointers, not in anyone's recall. When two candidates tie on severity, prefer the one that removes load from the implementation role.
