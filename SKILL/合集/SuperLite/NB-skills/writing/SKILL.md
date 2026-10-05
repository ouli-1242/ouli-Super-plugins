---
name: writing
description: "Use when creating any written deliverable - documents, plans, reports, analyses, emails, config files, READMEs - or turning messy material into a structured one (总结文章、会议纪要、整理聊天记录成要点、翻译成文). \"帮我写\", \"写个文档\", \"做个计划\", \"总结一下这篇\", \"整理一下这个聊天记录\". Confirms purpose and audience first, outlines before prose for non-trivial pieces. NOT for code (tdd), NOT for stress-testing an existing plan (grilling)."
---
# Writing

## Purpose

Produce written deliverables matched to purpose and audience, and extract structured summaries from messy material without inventing content.

## When to Use / Not Use

- Use: any written deliverable — documents, plans, reports, analyses, emails, config files, READMEs; turning messy material into a structured one (总结 / 纪要 / 整理 / 翻译).
- Do NOT use: code (tdd); stress-testing an existing plan (grilling).

## Capability Boundary

- CAN: fix purpose/audience, outline, draft to the outline, extract from sources with anchors, place durable outputs.
- CANNOT: write before knowing why and for whom; fill gaps in source material from imagination.
- Depends on: the source material; doc-index when the project has a `docs/` spine.

## Input Contract

- Required: the writing task or the source material.
- Optional: audience constraints, length limits, templates.
- Missing behavior: purpose or audience unclear → ask one question ("这份是给谁看的、要达成什么？") before writing. Messy material → read it fully once before extracting anything.

## Output Contract

- Normal mode: the deliverable, at the length the purpose demands — every section serving the stated purpose.
- Messy-material mode (总结/纪要): extraction, not creation — every claim carries a source anchor (timestamp / sender / page); names, numbers, dates copied exactly, never normalized from memory; anything inaudible/ambiguous marked `[待确认]` with what to confirm; action items get owner + deadline or "期限待定" (an item without an owner is a wish); a stated reader and length limit.
- Plan mode: the outline IS the skeleton — goal → steps → order → what can fail; the goal is confirmed before step detail.
- Durable placement: in a project, plans → `docs/计划/`, designs → `docs/设计/`, reviews → `docs/审查/`, kept minutes → `docs/日志/`, registered in 文档导航. Daily one-offs stay in chat unless asked to save.

## Constraints and Prohibitions

- Purpose and audience come first — same content for the wrong reader is the wrong document.
- Outline before prose for anything beyond a few paragraphs; draft directly for small pieces (short email, config file, one-page note).
- No gold-plating: the length the purpose demands, not more; emphasis follows importance, not uniform section depth.
- Messy-material hard rules: full read before extraction; anchors on every claim; exact copies of names/numbers/dates; `[待确认]` over invention.
- Prohibited: writing before the audience is known; skipping self-review ("it's just a draft"); inventing content the source doesn't contain.

## Acceptance Criteria

- The deliverable states (or visibly serves) its purpose and audience; every section survives the self-review cut.
- Self-check: does every section serve the purpose? Are all numbers/quotes anchored to the source? Would the reader know what to do after reading?

## Failure and Escalation

- Audience/purpose unanswerable → one clarifying question; no answer → deliver with the assumption stated.
- Source material contradictory → record both readings; do not reconcile silently.
- Missing data for a required section → `[待确认]` marker, never invention.

## Cost and Latency Budget

- One full source read (extraction mode), outline round-trip for non-trivial pieces, one self-review pass. Over budget: deliver the outline + open questions instead of rushed prose.

## Examples

- Positive: meeting transcript → minutes with timestamps, `[待确认]` on the inaudible budget figure, action items each with an owner.
- Negative: "normalized" a phone number from memory because the audio was unclear.
- Edge: a price comparison for a friend — daily one-off; delivered in chat, no docs spine created.

## Evaluation and Observability

- Metrics: audience-unknown deliveries (target 0), unanchored claims in extraction mode (target 0), reader follow-up questions caused by structure.
- Log: durable deliverables registered in 文档导航; `[待确认]` items tracked to resolution.
