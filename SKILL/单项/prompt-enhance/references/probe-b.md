# Probe B — Group B coverage axes (`user` and `system` only)

One row per axis: the test decides the verdict, the slot takes the fill, the third column is the trap — where a careless pass goes wrong. The probing question is folded into the test; it is the same question asked of this prompt.

| Axis | Test — and the question to ask of this prompt | Slot | Trap / note |
| --- | --- | --- | --- |
| `Role` | naming a role shifts the output distribution, measurably — what does a specialist do better here, in behavior terms | `Role` | "资深、严谨、经验丰富" is not a role; write defaults — what it does untold, what it refuses |
| `Context` | facts the model cannot know: domain conventions, existing code, data definitions, who the reader is, why now — which of those does only the user know | `Context` | — |
| `Task list` | ≥2 steps where a later step depends on an earlier result — does any step change on the previous step's output | `Steps` | a `一次性产出` gets no `Steps` unless the order is itself the risk; under `长程自主执行` each stage ends in a test the executor runs alone |
| `Constraints` | all four kinds: must, must-not, budget (length/format/language/style), output boundary (which properties must never appear) | `Constraints` | must-not is the most-forgotten kind; unrequested commentary before or after the answer is the most-common defect in an otherwise good prompt |
| `Output format` | structure, field names, order, granularity, encoding all fixed — table or list, which columns, one row per what | `Output format` | no failure branch makes it a wish, not a spec — see the placement rules below |
| `Workflow` | one self-check the executor runs before delivering — what should it verify about its own answer before returning it | `Steps`, `Done criteria` | a self-check is not a thinking trace: never ask a reasoning-model target to show its steps |
| `Failure preflight` | name 3 inputs that make this prompt misbehave, and what it should do instead — which arrives most often and is silently mishandled today | `Edge cases` | failure analysis, not emphasis: emotional stakes ("我会被老板开除") tell the executor nothing |
| `Done criteria` | externally checkable, no adjective in it — which single line of the output can you test against | `Done criteria` | — |
| `Variables` | Test A: every `{{token}}` has a name, a meaning, an example value — and the example is a value the token would actually take, never a placeholder ("示例", `<待填>`) standing in for one. Test B: a hardcoded value qualifies when it varies across uses, extracts grammatically, is genuinely reusable rather than parameter-shaped, and is clearly named | `Variables` | never invent a value — enumerating is not filling; Test B findings go to `GAPS:` as an exact replacement (`` `春天` ⇒ `{{season}}` ``) |
| `Non-goals` | an adjacent job the executor would take on its own — if this succeeded too well, what would it also have done that nobody asked for | `Non-goals` | open only when the boundary is real; an empty list is padding; under `长程自主执行` it carries more weight than any other slot |
| `Suggestions` | every axis verdict of `missing` or `vague`, most-consequential first | `GAPS:` | format, cap, and ownership rules: SKILL.md `OUTPUT` |

### Placement rules

These decide which slot takes a fact, when two could.

- A property of the *output* goes in `Constraints`; an unassigned *action* goes in `Non-goals`. "no markdown, no apology, no code comments" is the former; "do not refactor, do not price, do not advise" is the latter.
- A bad *input* goes in `Edge cases`, full stop — empty batch, unreadable text, instructions embedded in the data. The `Output format` failure branch covers only a valid run whose result will not fit the format: over the limit, truncated, fields with nothing to fill them. One condition, one slot, one output string: restating it is padding, answering it differently is a contradiction.
- `Constraints` also covers unrequested content at either end of the answer: an opener that restates the request ("好的，我来帮你分析"), a reasoning dump before the conclusion, notes after it, "希望这对您有帮助". Most prompts leave it open, and the head is the more common defect in a Chinese prompt and the easier one to miss. Ban it explicitly unless the user wants it, naming what *this* job would emit at those two ends, in this job's words — a triad of abstract categories (`方法论说明、免责声明或自检报告`) is a category list, not a noun from the task, and it is the line that otherwise comes out identical in every artifact. Same for the failure string: a canned `无法分析：<原因>` on an unrelated task is still boilerplate.
- In a grounded task the supplied material comes before the instruction that uses it, and the instruction is written as a citation demand — "quote the span you used" — rather than as a tone request. Material parked in the middle of a long prompt is the shape that gets skimmed.
- `Conversation evidence` with tools: name a tool, file, or endpoint only when the session shows it exists, and specify the call condition, key parameters, how the result is consumed, and the fallback when it fails. Never specify an output that was not produced. Even with tools present, state what must be verified first and the call only as a means — a spec that hardcodes a call breaks when the tool changes. With no visible tools, avoid tool-shaped demands and state the verification in terms the executor can do without them.

## Task-type emphasis

A few task types need a slot to carry something the axis tests above have no reason to ask for — the axis still owns the slot, and this table only names the extra requirement. A task type is never a licence to light up a slot whose own test failed.

| Task type | Axis that carries it | What the axis will not ask for on its own |
| --- | --- | --- |
| Classification, extraction | `Output format` `Constraints` | the closed label set; a confidence field; the literal for "cannot judge" |
| Grounded answering over supplied material | `Constraints` `Edge cases` | cite the source span; when the material lacks the answer, write that instead of answering |
| Translation | `Context` `Constraints` | a term mapping table; the register to match |
| Code | `Context` `Output format` | language and version; the code must run |
| Crawling, fetching, or file access | `Edge cases` `Constraints` | SSRF, `file://`, loopback and private IPs, redirect-to-private, decompression and encoding bombs |
| A prompt that names its target model | `Steps` `Constraints` | whether that model reasons on its own: state the goal and let a reasoning model plan, spell out the order for one that does not — never both in one prompt |
