---
name: finishing-a-development-branch
description: Use when implementation is complete and tests pass, to decide how to integrate the work - "合并分支", "提个 PR", "merge this back", "收尾这个分支". The integration choice (merge / PR / keep) belongs to the user; branch deletion requires typed confirmation. NOT before tests pass (verification-before-completion first), NOT for reviewing the code itself (code-review first), NOT while merge conflicts are unresolved (resolving-merge-conflicts).
---

# Finishing a Development Branch

**Announce at start:** "I'm using the finishing-a-development-branch skill to complete this work."

**Core principle:** Verify tests → Confirm base branch → Present options → Execute choice → Clean up the branch. The integration decision is your human partner's, never yours.

## Step 1: Verify Tests

Run the project's full test suite (`npm test` / `cargo test` / `pytest` / `go test ./...`).

**If tests fail**, report the failures and stop — the menu comes after a green suite:

```
Tests failing (<N> failures). Must fix before completing:

[Show failures]
```

**If tests pass:** continue to Step 2.

## Step 2: Determine Base Branch

The base branch is whatever this work forked from — usually named in the plan, the conversation, or the branch's upstream. If it is not already known, ask: "This branch split from <your best guess> - is that correct?"

Confirm before merging: merging into the wrong base is expensive to undo.

## Step 3: Present Options

```
Implementation complete. What would you like to do?

1. Merge back to <base-branch> locally
2. Push and create a Pull Request
3. Keep the branch as-is (I'll handle it later)

Which option?
```

Present the menu exactly as written — concise, every option from the list. Wait for the answer; the integration decision is theirs. Discarding the work happens only in response to your human partner explicitly asking for it (see below).

## Step 4: Execute Choice

### Option 1: Merge Locally

```bash
git checkout <base-branch>
git pull
git merge <feature-branch>
```

**If the merge hits conflicts:** stop here and call the Skill tool with "resolving-merge-conflicts" — that skill owns the conflict-resolution discipline (both sides' intent, never invent behavior, never `--abort`). Return to this skill's remaining steps once the merge completes.

Then run the full test suite **on the merged result**. If tests fail on the merged result: stop, leave the branch in place, and investigate — nothing has been pushed, so the merge is local and recoverable.

Once the merged result is green, delete the feature branch:

```bash
git branch -d <feature-branch>
```

Worktree cleanup belongs to whatever created the worktree (SuperWork does not manage worktrees) — clean up only the branch here.

### Option 2: Push and Create PR

```bash
git push -u origin <feature-branch>
```

Then create the pull/merge request against <base-branch> with the forge's tooling — its CLI if one is available, or the creation URL most forges print when you push — following the repo's PR template and conventions if present, and report the URL to your human partner.

### Option 3: Keep As-Is

Report: "Keeping branch <name>."

### If your human partner asks to discard the work

This path exists only as a response to an explicit request to throw the work away. Confirm first:

```
This will permanently delete:
- Branch <name>
- All commits: <commit-list>

Type 'discard' to confirm.
```

Wait for that exact confirmation. When it arrives, force-delete the branch (`git branch -D <feature-branch>`). Never treat "yeah, get rid of it" as the confirmation.

## Quick Reference

| Option | Merge | Push | Cleanup Branch |
|--------|-------|------|----------------|
| 1. Merge locally | yes | - | yes |
| 2. Create PR | - | yes | - |
| 3. Keep as-is | - | - | - |
| Discard (explicit request only) | - | - | yes (force) |

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Tests passed earlier this session" | Run the suite on the tree you are about to integrate. A green run only proves the tree it ran on. |
| "They obviously want it merged" | Integration is your human partner's decision. Present the menu and wait. |
| "They seem done with this feature — I'll offer to discard it" | The menu is complete as written. Discard happens only when they ask in so many words. |
| "'Yeah, get rid of it' counts as confirmation" | Only the typed word `discard` authorizes deletion. |
| "The merged-result failure is probably flaky" | A failing merged result stops everything. Branch stays put while you investigate. |
| "The base branch is obviously main" | Confirm the fork point or ask. Merging into the wrong base is expensive to undo. |
| "The push was rejected — force-push will fix it" | A rejected push means the remote moved. Investigate; force-push only on your human partner's explicit request. |
