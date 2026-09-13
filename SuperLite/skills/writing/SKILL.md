---
name: writing
description: Use when creating any written deliverable - documents, plans, reports, analyses, emails, config files, READMEs - or turning messy material into a structured one (总结文章、会议纪要、整理聊天记录成要点、翻译成文). "帮我写", "写个文档", "做个计划", "总结一下这篇", "整理一下这个聊天记录", "draft", "write up". Confirms purpose and audience first, outlines before prose for non-trivial pieces. NOT for code (tdd), NOT for stress-testing an existing plan (grilling).
---

# Writing

## The Rule

Before writing any deliverable, know **why it exists and who reads it**. If either is unclear, ask one question first: "这份是给谁看的、要达成什么？" Then match the form to the purpose — a status update for your boss is not the same document as notes for yourself.

## Process

1. **Purpose & audience** — one sentence each: who reads this, and what should they do / learn / decide afterward. If you can't state both, ask before writing.
2. **Outline first (non-trivial pieces)** — for anything longer than a few paragraphs, present the section skeleton and get a nod before filling it in. For small pieces (a short email, a config file, a one-page note), draft directly.
3. **Draft to the outline** — one section at a time. No gold-plating: the length the purpose demands, not more.
4. **Self-review** — re-read against the purpose: does every section serve it? Is anything missing the reader will need? Cut what doesn't serve.

## From messy material (总结 / 纪要 mode)

When the input is someone else's mess — a transcript, chat log, email thread, long article, scattered notes — and the ask is 总结 / 整理 / 纪要, the deliverable is **extraction, not creation**. Read the source fully once before extracting anything; every claim carries a source anchor (timestamp / sender / page); names, numbers, and dates are copied exactly, never normalized from memory. Anything inaudible or ambiguous → `[待确认]` with what to confirm — never filled from imagination. Action items get owner + deadline, or "期限待定" — an item without an owner is a wish. A summary has a reader and a length limit; fix both before compressing.

## Plans specifically

When the deliverable is a plan — trip, project, task breakdown, rollout — the outline IS the skeleton: goal → steps → order → what can fail. Confirm the goal before detailing steps; a detailed plan toward the wrong goal is waste with extra words.

## Where durable deliverables live

Save durable deliverables (plans, specs, reports) under `docs/` in the matching type dir and register them in `docs/文档导航.md` (per `doc-index`): plans → `docs/计划/`, specs/designs → `docs/设计/`, review reports → `docs/审查/`. Throwaway pieces (a quick email, a scratch note) stay in chat — don't pollute the index. If `docs/文档导航.md` is missing, create it via doc-index first.

## Anti-patterns

- Writing before knowing the audience (same content, wrong reader = wrong document)
- Expanding every section to equal depth — emphasis should follow importance, not uniformity
- Skipping self-review ("it's just a draft") — drafts with the wrong structure waste the reader's attention and your rework
