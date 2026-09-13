# Handoffs Between Skills

Skills pass control to the next stage with an explicit call, never a bare `/name` mention:

- `brainstorming` (architectural path, spec approved) → call the Skill tool with `"writing-plans"`
- `brainstorming` (bounded/spike path, design approved) → call the Skill tool with `"tdd"`
- `writing-plans` (plan written and approved) → call the Skill tool with `"executing-plans"`
- `executing-plans` (per task) → call the Skill tool with `"tdd"`; (all tasks done) → call the Skill tool with `"code-review"`, then `"verification-before-completion"`, then `"finishing-a-development-branch"` to integrate the work
- `code-review` (report produced) → call the Skill tool with `"receiving-code-review"`
- `tdd` (loop finished, cleanup time) → call the Skill tool with `"code-review"`
- `verification-before-completion` (change verified; user signals integration or the change was large per discipline #3) → call the Skill tool with `"finishing-a-development-branch"`
- `finishing-a-development-branch` (merge hits conflicts) → call the Skill tool with `"resolving-merge-conflicts"`

If a conversation was interrupted and you are resuming mid-flow, re-derive the stage from the artifacts on disk (spec status lines, plan checkboxes, git log, and the 文档导航 index) and re-enter the route table at that stage.
