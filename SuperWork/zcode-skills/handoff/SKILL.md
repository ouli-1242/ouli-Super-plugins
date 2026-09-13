---
name: handoff
description: "Use when the user asks to transfer or compress the session - 「交接」「handoff」「压缩会话」「会话太长了」 - or when context usage crosses its tier's compression line, tiered by window size: ≤256k start 70% / hard 90%; ≤500k 60% / 75%; ~1M 40% / 60%. 中文信号：「交接」「压缩会话」"
---
# Handoff

Ask the user one thing before writing: **what will the next session be used for?** The answer decides which state is worth carrying.

## Compression line（上下文压缩线，按窗口分档）

| Context window | start（写好交接文档） | hard line（写完并提示用户压缩） |
|---|---|---|
| ≤256k | 70% | 90% |
| ≤500k | 60% | 75% |
| ~1M | 40% | 60% |

**两层含义，必须分清**：

- agent 能做的唯一准备是**写好交接文档**——这不是压缩本身，而是让随后的压缩无损。到 start 线就把它写好（任务进行中则先完成/打点），写完告诉用户「交接已就绪，可随时压缩」。
- **真实的上下文压缩由 harness 执行**：自动 compact、用户的 /compact、或结束会话开新窗口。到 hard 线：立即写完文档（在途任务精确打点：已完成什么、做到哪一半、确切下一步、未提交变更），然后明确提示用户「现在就压缩或开新会话」。agent 无权也无力删掉自己的上下文，不要假装压缩发生过。

百分比按窗口大小估算，永远不是精测——拿不准就早写。start 线的意义是让压缩随时无损；hard 线是给估算误差和突发长输入留的最后余量。当前窗口的档位读不到时，按最大的窗口（1M / 40-60）保守执行，或直接问用户。

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
