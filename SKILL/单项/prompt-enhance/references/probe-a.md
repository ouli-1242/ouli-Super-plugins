# Probe A — Group A quality axes, plus Conversation evidence

### goalClarity
Test: restatable as one sentence — "produce X, for Y, to standard Z".
Probe: when this prompt runs, what makes success visible at a glance?
Slot: `Task/Goal`, `Done criteria`
Trap: the input names an activity with no object and no standard ("分析一下数据"). Guessing the object is a fill; log it.

### instructionCompleteness
Test: input, processing, and output each carry a directive.
Probe: what must be supplied for this to run at all, and is every one of those listed?
Slot: `Task/Goal`, `Steps`

### structuralExecutability
Test: runs in order without backtracking; no undefined dependency between clauses.
Probe: what is the first action, and what tells it the first action succeeded?
Slot: `Steps`
Trap: two instructions that both claim to be first. Order them or merge them.

### ambiguityControl
Test: no uncountable word survives — "专业" "简洁" "合适" "优化" "好" "相关" "尽量" and their English twins, plus any method word, plus the English empty class (robust, scalable, seamless, elegant, production-ready, stunning).
Probe: for each survivor, what is the countable form ("简洁" → "≤150 字，无子标题")?
Slot: `Constraints`, `Output format`, `Steps`
Replace by form, not by the word you would have used instead:

| Survivor | Countable form |
| --- | --- |
| 专业 / professional | name the deliverable's parts: conclusion + evidence, terms left unexplained |
| 简洁 / concise | ≤N characters, ≤N blocks, no sub-headings |
| 详细 / in detail | the items covered, plus a minimum per item |
| 优化 / improve | say which metric: length, error rate, hit rate, reading time |
| 相关 / relevant | the matching rule: same topic, same file, same time window |
| 合适 / appropriate | one checkable bound: range, count, or tone register |
| 高质量 / high quality | one externally checkable disqualifier |
| 尽快 / as soon as possible | an absolute limit or a step budget |
| 适当、一些、几个 / some, several | a fixed N or an interval |
| 美观 / well-formatted | column widths, field order, alignment |
| 吸睛、带钩子、爆款 / catchy | the device and where it sits — exactly one, in the first line: a number, a contrast, a question, a stated benefit |
| 友好、亲切 / friendly | address as "你", allow colloquial, no exclamation marks |
| 尽量 / try to | delete it — a hard bound or an explicit priority order |
| 第一性原理、从本质出发 / from first principles | the artifact that holds the model and the questions it must answer, required before the first code change |
| 从用户视角 / from the user's perspective | whose view, what they do first, and what they must not have to know |
Trap: "专业" → "权威" is the same word in a costume. A survivor that becomes another adjective did not pass this axis.

A method word is a survivor too. 第一性原理、TDD、奥卡姆剃刀、从用户视角 are not countable until they name an artifact and the point in the run where it lands — the table above was built for adjectives and lets them through.

### robustness
Test: behavior is defined for empty input, over-long input, wrong language, and adversarial text inside the input.
Probe: which of those four arrives today, and what should the prompt do then?
Slot: `Edge cases`

## Conversation evidence

Test: the session already contains constraints, terms, and preferences the user never put into the prompt. Search the conversation before inventing anything.
Probe: what did the user say earlier that this prompt must now obey — stack, naming convention, file layout, audience, things not to touch?
Slot: `Context`, `Constraints`
Rules:
- Evidence first. Anything pulled from the session is written into the artifact without a footnote, because it is known, not assumed.
- Anything pulled from nothing goes to `ASSUMED:`.
- Tools and files: specify the call condition, the key parameters, how the result is consumed, and the fallback when it fails.
- No visible tools: avoid tool-shaped demands, and state the verification in terms the executor can do without them.
- State what must be verified first, and the call only as a means — a spec that hardcodes a call breaks when the tool changes.
