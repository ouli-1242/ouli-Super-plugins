---
name: doc-revise
description: "Use when changing an existing text the user owns or is responsible for - polishing wording, shortening or expanding, changing tone or style, fixing broken layout and formatting, converting between format conventions. \"润色一下\", \"改短一点\", \"换个语气\", \"排版乱了帮我修\", \"改成正式一点的措辞\". NOT for giving opinions on someone else's material (doc-review), NOT for creating content that does not exist yet (doc-draft), NOT for summarizing external input (doc-intake)."
---
# Doc Revise — change what is asked, preserve what is not

Revision works on a text that already exists. The whole skill is one balance: make the requested change while keeping everything else intact. The fastest way to lose a user's trust is to "improve" a number, a commitment, or a name while polishing a sentence.

## Step 1 — Fix the mode and the invariants

Ask (or infer and state) which mode, then declare what must not change:

| Mode | Task | Typical invariants |
|---|---|---|
| 润色 | Smooth expression, keep meaning | 数字、结论、承诺、称谓、事实 |
| 缩短 | Cut to a target length | 信息点清单 — nothing below may vanish |
| 扩写 | Add substance | 既有事实与立场 — no padding, no invented detail |
| 换风格 | Match a target register | 内容与结论; style only |
| 格式修复 | Layout, fonts, spacing, TOC, page numbers | 文字内容 — formatting only |

For 缩短: before cutting, list the information points you identified, then cut, then check every point survives. Expansion without new material is padding — ask for material instead.

## Step 2 — Choose the tool by the change

- Wording-level changes on a closed file: edit directly (document skills' Python route) or hand back text in the conversation — whichever the user's workflow prefers.
- Layout/format repair at document scale: script it (batch style application, field refresh) or drive WPS via the Skill tool with "wps-cli" when the WPS engine or an open document is involved. Never hand-fix formatting paragraph by paragraph.
- The user's document is open in WPS and they watch you edit → wps-cli, not a side copy that silently diverges.

## Step 3 — Verify the edit landed

Read the changed document back: the requested change is present, the invariants are byte-identical where they must be (numbers, names, dates), and for 格式修复 the layout proof is a **print preview or rendered screenshot**, not a description. For 缩短, deliver the information-point checklist with the text.

## Rationalizations

| Excuse | Reality |
|--------|---------|
| "顺手把这个数字也改准确点" | You cannot know the right number — only the source or the user can. Flag it, don't edit it. |
| "润色时把结论也顺一句" | Conclusions are the owner's. Polish the road, never move the destination. |
| "格式我目测修好了" | Layout claims need rendered evidence — preview or screenshot. |
| "改多了没关系，用户会挑" | Every un-requested change is one the user must now hunt for. Restraint is the feature. |

## Downstream

Reviewing someone else's material with feedback → `doc-review`. The revised document ready to hand over → `verify-output`. "以后我们的润色都按这个风格" → `doc-asset`.
