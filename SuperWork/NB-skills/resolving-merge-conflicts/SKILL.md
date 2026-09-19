---
name: resolving-merge-conflicts
description: "Use when a git merge or rebase is in progress and has conflicts to resolve - \"解决冲突\", \"merge conflict\", \"rebase 卡住了\". Reads both sides' original intent, preserves both where possible, never invents new behavior, never aborts. NOT for deciding whether to merge (finishing-a-development-branch), NOT for reviewing code (code-review)."
---
# Resolving Merge Conflicts

## Purpose

Resolve every conflict hunk from both sides' original intent — preserving both where possible, inventing nothing, aborting nothing.

## When to Use / Not Use

- Use: a merge or rebase is in progress with conflicts to resolve.
- Do NOT use: deciding whether to merge (finishing-a-development-branch); reviewing code (code-review).

## Capability Boundary

- CAN: read conflict history, recover both sides' intent, resolve hunks, run post-merge checks, complete the merge/rebase.
- CANNOT: invent behavior not present on either side; silently pick a winner on architectural incompatibility.
- Depends on: git history (commit messages, PRs, tickets) as the source of intent.

## Input Contract

- Required: the in-progress merge/rebase state (`git status` + conflicted files).
- Optional: the merge's stated goal; related commits/PRs/issues.
- Missing behavior: intent of a side cannot be recovered from history → ask the user rather than guess.

## Output Contract

- A completed merge/rebase commit in which every hunk resolution is traceable to one or both sides' original intent (or a documented, goal-justified trade-off), with the project's automated checks passing.

## Constraints and Prohibitions

- **Never `--abort`.** Always resolve. Find the primary sources for each conflict — commit messages, PRs, original issues — and understand why each change was made before touching the hunk.
- Preserve both intents where possible. Where incompatible, pick the side matching the merge's stated goal and note the trade-off. **Never invent new behavior** as a "compromise".
- If the conflicts reveal incompatible architectural changes — this is a design conversation, not hunk resolution: stop and surface to the user instead of silently picking a winner.
- After resolution: discover and run the project's automated checks (typecheck → tests → format) and fix anything the merge broke.

## Acceptance Criteria

- Merge/rebase completed; all hunks traceable to original intents; automated checks green.
- Self-check: for each resolution, can I name the intent (or trade-off) it preserves? Did I invent any behavior?

## Failure and Escalation

- Intent unrecoverable → ask the user; do not guess.
- Architectural incompatibility → stop and surface; the fix is a design decision, not a hunk edit.

## Cost and Latency Budget

- Intent recovery per conflict (history reads), then one check suite. Over budget: resolve the clear hunks, list the ambiguous ones for the user.

## Examples

- Positive: both sides renamed the same function differently — keep one name via a mechanical rename commit, note the decision, run checks.
- Negative: writing a " blend" of two logic branches that exists in neither history.
- Edge: the two sides restructured the same module in incompatible ways → stop, present both architectures, let the user decide.

## Evaluation and Observability

- Metrics: resolutions that later had to be reworked, invented behavior (target 0), aborts (target 0).
- Log: per-conflict intent notes into the merge commit message.
