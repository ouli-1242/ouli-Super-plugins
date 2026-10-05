---
name: doc-intake
description: "Use when turning messy external input into structured products - meeting recordings or transcripts into minutes, chat logs or email threads into action items, scattered notes into organized drafts, long documents or web articles into summaries. \"整理一下这个录音/聊天记录\", \"做个会议纪要\", \"总结这份材料\", \"把这些零散笔记理一理\". NOT for creating a new document from scratch (doc-draft), NOT for revising an existing draft (doc-revise)."
---
# Doc Intake — turn messy input into structured products

You are digesting material someone else produced — a recording, a chat log, an email thread, a pile of notes, someone else's long document. The product is always one of a few fixed shapes. What never changes: **every claim in your product must be traceable to the source**. Intake is extraction, not creation.

## Step 1 — Fix the input type and the target product

| Input | Default product |
|---|---|
| Meeting recording / transcript | 会议纪要（decisions, action items, open questions） |
| Chat log / email thread | 要点 + 行动项 + 待回复清单 |
| Scattered notes / voice memo | 结构化清单或草稿素材（供 doc-draft 消费） |
| Long document | 摘要（规格由读者决定，见 Step 2） |

If the target product is unclear, ask one question — "纪要给谁看，要行动项吗" — before working. Do not guess a deliverable shape.

## Step 2 — Read the source completely, once, before extracting

Partial reading produces partial minutes that look complete. For a transcript: read to the end even when it is boring — decisions hide in the last ten minutes. For a summary: first ask (or fix) **who reads it and how long it may be**; a summary is an act of selection for a reader, not compression to an arbitrary length.

## Step 3 — Extract with traceability

- Every decision, number, name, and date gets a **source anchor**: timestamp for recordings, message/sender for chats, page/section for documents.
- Attribute statements to speakers verbatim where it matters ("张三承诺 9 月底交付"), never as your own paraphrase when the wording is the point.
- Quotes stay verbatim. Paraphrase only around them.
- Anything inaudible, ambiguous, or missing → mark `[待确认]` with what to confirm and whom to ask. A gap marked is honest work; a gap filled from imagination is fabrication.

## 会议纪要 — REQUIRED slots

```
会议信息：时间 / 地点或线上 / 参会人 / 记录人
决议：    每条一行，可执行、有主语（"同意 X"，不是"讨论了 X"）
行动项表：事项 / 负责人 / 期限 —— 三列缺一不可；没有负责人的行动项是遗愿
遗留问题：未达成一致的，写明双方立场
来源：    原始转写/材料的存档路径
```

## Step 4 — Verify before delivering

Re-read your product against the source once, item by item: every name spelled as in the source, every number identical, every date identical, every action item has an owner and a deadline or an explicit "期限待定". Numbers that appear in the product must be found in the source — if you cannot find one, delete it or mark `[待确认]`.

## Rationalizations

| Excuse | Reality |
|--------|---------|
| "这里没听清，按上下文补一个吧" | Marked `[待确认]` costs the user one question; a fabricated item costs a wrong commitment. |
| "发言人都熟，不用写谁说的" | Decisions without owners are re-litigated next meeting. Attribution is the product. |
| "摘要嘛，写长一点总没错" | An unread summary equals no summary. The reader's limit is a requirement, not a suggestion. |

## Downstream

Products of this skill are inputs, not endpoints: minutes and action items can seed `doc-draft`; extracted facts feed `data-report`. When the user says "把这些沉淀成我们的格式/术语", call the Skill tool with "doc-asset".
