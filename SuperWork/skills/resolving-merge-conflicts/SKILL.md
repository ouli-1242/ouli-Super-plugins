---
name: resolving-merge-conflicts
description: Use when a git merge or rebase is in progress and has conflicts to resolve - "解决冲突", "merge conflict", "rebase 卡住了", "conflict markers in the file". Reads both sides' original intent, preserves both where possible, never invents new behavior, never aborts. NOT for deciding whether to merge (finishing-a-development-branch), NOT for reviewing code (code-review).
---

# Resolving Merge Conflicts

1. **See the current state** of the merge/rebase. Check git history, and the conflicting files.

2. **Find the primary sources** for each conflict. Understand deeply why each change was made, and what the original intent was. Read the commit messages, check the PRs, check original issues/tickets.

3. **Resolve each hunk.** Preserve both intents where possible. Where incompatible, pick the one matching the merge's stated goal and note the trade-off. Do **not** invent new behaviour. Always resolve; never `--abort`.

4. Discover the project's **automated checks** and run them, typically typecheck, then tests, then format. Fix anything the merge broke.

5. **Finish the merge/rebase.** Stage everything and commit. If rebasing, continue the rebase process until all commits are rebased.

If the conflicts reveal that the two sides made incompatible architectural changes, stop and surface this to your human partner instead of picking a winner silently — that is a design conversation, not a hunk resolution.
