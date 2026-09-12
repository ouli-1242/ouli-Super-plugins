---
name: code-review
description: Use when reviewing changes before merge or delivery - the user asks to review a branch, PR, or work-in-progress changes ("review", "review since X", "评审一下这次的改动", "检查下改动"), or the change is large enough that review is mandatory before merging to mainline - core module touched, diff >= 15 files, or new engine/API/data-model contracts. Typically after implementation (tdd) and before declaring completion. NOT for deciding how to integrate finished work (finishing-a-development-branch).
---

Two-axis review of the diff between `HEAD` and a fixed point the user supplies:

- **Standards** — does the code conform to this repo's documented coding standards?
- **Spec** — does the code faithfully implement the originating issue / spec?

Both axes run as **parallel sub-agents** so they don't pollute each other's context, then this skill aggregates their findings.

The issue tracker should have been provided to you — if `docs/agents/issue-tracker.md` is missing, note it and rely on commit-message issue references, the user-passed spec path, and specs under `docs/设计/`, `docs/`, `specs/`, or `.scratch/`.

## Process

### 1. Pin the fixed point

Whatever the user said is the fixed point — a commit SHA, branch name, tag, `main`, `HEAD~5`, etc. If they didn't specify one, ask for it.

Capture the diff command once: `git diff <fixed-point>...HEAD` (three-dot, so the comparison is against the merge-base). Also note the list of commits via `git log <fixed-point>..HEAD --oneline`.

Before going further, confirm the fixed point resolves (`git rev-parse <fixed-point>`) and the diff is non-empty. A bad ref or empty diff should fail here — not inside two parallel sub-agents.

### 2. Identify the spec source

Look for the originating spec, in this order:

1. Issue references in the commit messages (`#123`, `Closes #45`, GitLab `!67`, etc.) — if `docs/agents/issue-tracker.md` exists, fetch via its workflow; if it's missing, skip this item and go to the next.
2. A path the user passed as an argument.
3. A spec file under `docs/设计/`, `docs/`, `specs/`, or `.scratch/` matching the branch name or feature.
4. If nothing is found, ask the user where the spec is. If they say there isn't one, the **Spec** sub-agent will skip and report "no spec available".

### 3. Identify the standards sources

Anything in the repo that documents how code should be written — first `docs/规范.md` (the SuperWork convention), then `CODING_STANDARDS.md` / `CONTRIBUTING.md` if present.

On top of whatever the repo documents, the Standards axis always carries the **smell baseline** — a fixed set of Fowler code smells that applies even when a repo documents nothing. Load `references/smell-baseline.md`; paste it in full to the Standards sub-agent (the sub-agent has no other access to it).

### 4. Spawn both sub-agents in parallel

Spawn both axes as parallel sub-agents (or run both yourself sequentially if no sub-agent tool — keep the two reports strictly separate). Use the prompt templates in `references/subagent-prompts.md`; paste the smell baseline (`references/smell-baseline.md`) into the Standards prompt.

If the spec is missing, skip the Spec sub-agent and note it.

### 5. Aggregate

Present the two reports under `## Standards` and `## Spec` headings, verbatim or lightly cleaned. Do **not** merge or rerank findings — the two axes are deliberately separate.

End with a one-line summary: total findings per axis, and the worst issue _within each axis_ (if any). Don't pick a single winner across axes.

### 5b. Persist the report

Save the report (both axes verbatim + summary) to `docs/审查/YYYY-MM-DD-<审查主题>.md`; register in 文档导航 (per doc-index). Reviews are durable, not chat. If `docs/文档导航.md` is missing, create it via doc-index.

### 6. Act on the findings

Severity drives the order of work, within each axis:

- **Critical** — broken behaviour, security, spec violation. Fix immediately, before anything else.
- **Important** — wrong-ish design or standards breach that will bite. Fix before declaring the work done.
- **Minor** — polish, naming, nits. Fix if cheap, otherwise note and move on.

Before implementing any finding, call the Skill tool with "receiving-code-review" — it is the reception discipline (verify before implementing, push back with technical reasoning when a finding is wrong). Never implement findings blindly.

## Why two axes

A change can pass one axis and fail the other (Standards-pass-Spec-fail or vice versa); reporting them separately stops one masking the other. Detail: `references/why-two-axes.md`.
