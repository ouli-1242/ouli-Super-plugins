# Contract — `user`

The `user` mode runs on the same slots as SKILL.md. This file fixes what each slot must contain in this mode, what is banned, and how short is too short.

Before inventing anything, run `Conversation evidence`: the session usually already contains constraints, terms, and preferences the user never put into the prompt. Evidence from the session goes into the artifact; invention goes to `ASSUMED:`.

## Precision pass on a requirement

Goal: turn a vague ask into a sharp ask. The artifact is still a request for the model to perform, not the performed result.

Five moves, each a test you must be able to answer after writing:
1. Detail mining — name the abstract nouns and say what each one concretely refers to.
2. Parameter clarification — attach a number or a named field to every vague requirement.
3. Scope definition — state the boundary: what is inside the task, what is not.
4. Quantified standards — replace quality words with thresholds (length, count, coverage).
5. Example supplementation — where a threshold cannot carry the meaning, give one short worked sample of the expected output.

Open `Constraints` and `Output format` always. Keep flexibility: specify the target and the limits, not the wording. Over-specifying turns a requirement into a script and is a failure of this mode, not a virtue.

Banned in this mode: executing the request; asking the user anything — SKILL.md `OUTPUT` routes user-only decisions to `GAPS:` and the artifact ships regardless.

## Floor

Four required slots is a floor, not a target. Fewer than four means the scan did not complete. There is no upper count: a conditional slot that passes its own test is not padding, even when seven of them are open — a prompt with three variables genuinely needs `Variables`, and one with real failure modes genuinely needs `Edge cases`. Padding is judged per slot by ANTI-PADDING rule 1 (would this text also be true for another task?), never by how many slots are lit.
