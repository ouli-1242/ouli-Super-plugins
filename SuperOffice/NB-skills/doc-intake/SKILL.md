---
name: doc-intake
description: "Use when turning messy external input into structured products - meeting recordings or transcripts into minutes, chat logs or email threads into action items, scattered notes into organized drafts, long documents or web articles into summaries. \"整理一下这个录音/聊天记录\", \"做个会议纪要\", \"总结这份材料\", \"把这些零散笔记理一理\". NOT for creating a new document from scratch (doc-draft), NOT for revising an existing draft (doc-revise)."
---
# Doc Intake — turn messy input into structured products

## Purpose

Digest material someone else produced into one of a few fixed product shapes — extraction, not creation, with every claim traceable to the source.

## When to Use / Not Use

- Use: recordings/transcripts → minutes; chat logs/email threads → action items; scattered notes → draft material; long documents → summaries.
- Do NOT use: creating a new document from scratch (doc-draft); revising an existing draft (doc-revise).

## Capability Boundary

- CAN: fix the input type and target product, extract with source anchors, produce minutes with required slots, verify against source.
- CANNOT: invent content the source does not contain; skip full-source reading.
- Depends on: the source material (audio transcription via available tooling when needed).

## Input Contract

- Required: the source material (recording/transcript/log/notes/document).
- Optional: the target reader, length limit, minutes template.
- Missing behavior: target product unclear → ask one question ("纪要给谁看，要行动项吗") before working; never guess a deliverable shape. For summaries, fix WHO reads it and HOW LONG it may be first — a summary is an act of selection for a reader.

## Output Contract

- The target product with **per-claim source anchors** (timestamp for recordings, message/sender for chats, page/section for documents); verbatim quotes preserved; paraphrase only around them; speaker attribution kept where the wording matters ("张三承诺 9 月底交付" stays attributed).
- **会议纪要 required slots:** 会议信息（时间/地点/参会人/记录人）· 决议（每条可执行、有主语）· 行动项表（事项/负责人/期限 — 三列缺一不可，没有负责人的行动项是遗愿）· 遗留问题（写明双方立场）· 来源（原始材料存档路径）。
- Gaps marked `[待确认]` with what to confirm and whom to ask.

## Constraints and Prohibitions

- **Read the source completely, once, before extracting** — partial reading produces partial minutes that look complete; decisions hide in the last ten minutes.
- Every decision, number, name, date gets a source anchor. Anything inaudible/ambiguous/missing → `[待确认]`. A gap marked is honest work; a gap filled from imagination is fabrication.
- Numbers in the product must be findable in the source — if you cannot find one, delete it or mark `[待确认]`.
- Prohibited: filling gaps from context plausibility; dropping attribution ("发言人都熟"); exceeding the reader's length limit.

## Acceptance Criteria

- Product verified against source item by item: names as spelled, numbers identical, dates identical, every action item with owner + deadline (or 期限待定).
- Self-check: can every claim be traced to its anchor? Is every gap marked rather than filled?

## Failure and Escalation

- Source incomplete or inaudible at a critical point → `[待确认]` + ask the user; never bridge with imagination.
- Product shape still ambiguous after one question → deliver the two candidate shapes and let the user pick.

## Cost and Latency Budget

- One full source read; extraction in one pass; one verify pass against source. Over budget: deliver the minutes with explicitly unfinished sections rather than a rushed full-looking product.

## Examples

- Positive: transcript → minutes with timestamps, verbatim decision quotes, an action-item table where every row has an owner.
- Negative: "这里没听清，按上下文补一个吧" — a fabricated action item costs a wrong commitment.
- Edge: an unread-long article → summary at the reader's stated limit, not an arbitrary compression.

## Evaluation and Observability

- Metrics: unanchored claims (target 0), unfilled-owner action items (target 0), `[待确认]` resolution rate.
- Log: source archive path recorded in the product (来源 slot); intake products are inputs, not endpoints — minutes seed doc-draft, extracted facts feed data-report, "沉淀成我们的格式" → doc-asset.
