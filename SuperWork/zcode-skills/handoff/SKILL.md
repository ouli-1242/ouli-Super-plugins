---
name: handoff
description: "Use when the user wants to compress, transfer, or continue the session elsewhere - 「交接」「handoff」「压缩会话」「会话太长了」「开新会话」「换个会话继续」 - or when a harness compaction notice appears in the conversation. 中文信号：「交接」「压缩会话」「会话太长了」「开新会话」「换个会话继续」"
---
# Handoff

Ask the user one thing before writing: **what will the next session be used for?** The answer decides which state is worth carrying.

## 触发时机：只认 agent 能真实看到的信号

agent **读不到**自己的上下文占用百分比，也没有估算它的可靠手段——任何"到达某百分比就自动触发"的设计都不成立，压缩提示不能依赖它。

agent 真正能看到的触发信号只有三类：

1. **用户明确要求**：「交接」「压缩会话」「开新会话」「会话太长了」。
2. **harness 压缩通知**：上下文中出现压缩 / 汇总的系统消息（自动 compact，或用户 /summarize、/compact、/compress 之后）——立即补写交接文档。
3. **新会话接续**：新会话发现 `docs/交接/` 下已有交接文档，先读它再动手。

因此交接文档**不是等触发才写**，而是随进度持续维护：长会话中每完成一个可交付单元（commit、测试通过、功能点、一次验证），就更新「今日交付 / 剩余任务」。压缩时机不可预测，文档保持常新，才能保证任何时刻压缩都无损——这是 agent 能做的全部准备，压缩本身仍由 harness 执行（自动 compact、用户的 /summarize、/compact、/compress，或结束会话开新窗口）。agent 无权也无力删掉自己的上下文，不要假装压缩发生过。

Write a handoff document summarising the current conversation so a fresh agent can continue the work. Save it to `docs/交接/YYYY-MM-DD-交接与剩余任务.md` **in the workspace** (not a temp dir) — handoffs must be greppable and survive across sessions. If `docs/文档导航.md` is missing, create it via the doc-index skill first; register the handoff row in the 交接 table.

Include a "suggested skills" section in the document, which suggests skills that the agent should invoke.

Do not duplicate content already captured in other artifacts (specs, plans, decisions, logs, commits, diffs). Reference them by path — the 文档导航 index and 决策记录 are the recovery anchors, not this doc.

## Required slots

1. **立即接续命令** — exact shell commands to reproduce state (git status, the test command). Durable run commands (setup/run/test/deploy) live in `docs/运行.md` — reference it, don't re-derive here.
2. **今日交付** — what shipped, with commit SHAs and key artifacts.
3. **剩余任务** — what the next session should do, in priority order.
4. **诚实边界** — what was NOT done / unverified / blocked, stated plainly. Required, not optional.
5. **suggested skills** — which SuperWork skills the next agent should invoke and why.

Redact any sensitive information — API keys, passwords, PII. If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.
