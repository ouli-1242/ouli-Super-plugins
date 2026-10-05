# Contract — `system`

The `system` mode runs on the same slots as SKILL.md. This file fixes what each slot must contain in this mode, what is banned, and how short is too short.

Before inventing anything, run `Conversation evidence`: the session usually already contains constraints, terms, and preferences the user never put into the prompt. Evidence from the session goes into the artifact; invention goes to `ASSUMED:`.

## Constraint pass on a role prompt

Goal: turn an identity claim into a runnable role specification.

`Role` slot rules: write behavior, not traits. Allowed: "默认给结论不给过程"; "不确定时标注 UNVERIFIED 而不是猜"; "被问价时只报公开价". Not allowed: "经验丰富" "专业严谨". A role slot that survives must change what the model does on a blank day.

Open `Edge cases` always — role prompts most often fail on off-topic input, and none state what to do then.

Banned in this mode: an `## Initialization` opening section ("As `<Role>`, you must follow the Constraints…") — that is the source project's habit of restating the role back to itself, and it costs lines without constraining behavior. Also banned: a `Skills` list of abilities the role "has"; if an ability matters, it belongs in `Constraints` or `Steps` as something done.

## Floor

Four required slots is a floor, not a target. Fewer than four means the scan did not complete. There is no upper count: a conditional slot that passes its own test is not padding, even when seven of them are open — a prompt with three variables genuinely needs `Variables`, and one with real failure modes genuinely needs `Edge cases`. Padding is judged per slot by ANTI-PADDING rule 1 (would this text also be true for another task?), never by how many slots are lit.
