---
name: doc-revise
description: "Use when changing an existing text the user owns or is responsible for - polishing wording, shortening or expanding, changing tone or style, fixing broken layout and formatting, converting between format conventions. \"润色一下\", \"改短一点\", \"换个语气\", \"排版乱了帮我修\", \"改成正式一点的措辞\". NOT for giving opinions on someone else's material (doc-review), NOT for creating content that does not exist yet (doc-draft), NOT for summarizing external input (doc-intake)."
---
# Doc Revise — change what is asked, preserve what is not

## Purpose

Make the requested change to an existing text while keeping everything else intact — the fastest way to lose trust is to "improve" a number, a commitment, or a name while polishing a sentence.

## When to Use / Not Use

- Use: polishing, shortening, expanding, tone/style change, layout/format repair, format-convention conversion on a text the user owns.
- Do NOT use: opinions on someone else's material (doc-review); creating content that doesn't exist (doc-draft); summarizing input (doc-intake).

## Capability Boundary

- CAN: fix the revision mode and invariants, choose the tool route, verify the edit landed with evidence.
- CANNOT: change un-requested content; fix layout by hand paragraph-by-paragraph at document scale.
- Depends on: the document skills' Python route (closed files); wps-cli (WPS engine / open documents).

## Input Contract

- Required: the existing text and the requested change.
- Optional: target length (缩短), target register (换风格), the unit's format profile.
- Missing behavior: mode ambiguous → ask, or infer and state the mode plus invariants before editing. Expansion without new material is padding → ask for material instead.

## Output Contract

- The revised text with the requested change present and invariants byte-identical where they must be; for 缩短, the information-point checklist delivered with the text; for 格式修复, **rendered evidence** (print preview or screenshot), never a description.

## Constraints and Prohibitions

- **Fix the mode and declare the invariants before editing:**
  | Mode | Task | Invariants |
  |---|---|---|
  | 润色 | Smooth expression | 数字、结论、承诺、称谓、事实 |
  | 缩短 | Cut to target length | 信息点清单 — nothing below may vanish |
  | 扩写 | Add substance | 既有事实与立场 — no padding, no invented detail |
  | 换风格 | Match register | 内容与结论 — style only |
  | 格式修复 | Layout/fonts/spacing/TOC | 文字内容 — formatting only |
- **Route by the change**: wording-level on a closed file → edit directly or hand back text; document-scale layout repair → script it or wps-cli; the user's document is open in WPS while they watch → wps-cli, not a side copy that silently diverges.
- **Verify the edit landed**: read the changed document back — requested change present, invariants intact, numbers/names/dates untouched.
- Prohibited: "顺手把这个数字也改准确点" (you cannot know the right number — flag it, don't edit it); moving conclusions while polishing the road; un-requested changes the user must now hunt for; claiming format fixed by eyeball.

## Acceptance Criteria

- The requested change present; invariants verified byte-identical (or checklist delivered for 缩短); rendered evidence for layout claims.
- Self-check: is every change traceable to the request? Did any number/name/conclusion shift?

## Failure and Escalation

- Invariant appears wrong in the original (a likely typo'd figure) → flag to the user; do not silently correct.
- Layout repair exceeds available tooling → say so; never hand-fix at document scale and claim success.

## Cost and Latency Budget

- One edit pass + one read-back; 缩短 adds a checklist. Over budget: deliver the flagged problem list instead of a partially verified revision.

## Examples

- Positive: 润色 mode → smoother sentences, five numbers verified byte-identical, conclusion untouched.
- Negative: shortening that dropped one of the eleven information points — the checklist exists to catch exactly this.
- Edge: 格式修复 on a 40-page doc → wps-cli batch style application + print-preview screenshot, not 40 pages of hand-fixed spacing.

## Evaluation and Observability

- Metrics: un-requested changes per revision (target 0), invariant violations (target 0), layout claims with rendered evidence (target 100%).
- Log: flagged-not-edited issues listed for the user; "以后都按这个风格" → doc-asset profile update.
