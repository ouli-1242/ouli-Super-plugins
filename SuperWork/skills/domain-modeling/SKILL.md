---
name: domain-modeling
description: Use when the user wants to pin down domain terminology or a ubiquitous language, or record an architectural decision - "统一术语", "这个词到底什么意思", "glossary", "ubiquitous language", "记个架构决策", "record this decision", "ADR". Actively builds and sharpens the project's domain model: decisions accumulate in docs/决策记录.md (D-NNN, six-part), the glossary lives in docs/技术依据.md. NOT for general design discussion - only for language and decision records. Pairs with grilling's With-Docs Mode; consumed by tdd and diagnosing-bugs.
---

# Domain Modeling

Actively build and sharpen the project's domain model as you design. This is the *active* discipline — challenging terms, inventing edge-case scenarios, and writing the glossary and decisions down the moment they crystallise. (Merely *reading* `技术依据.md` for vocabulary is not this skill — that's a one-line habit any skill can do. This skill is for when you're changing the model, not just consuming it.)

## File structure

```text
docs/
├── 文档导航.md          ← 索引门面（doc-index skill 维护）
├── 决策记录.md          ← D-001~D-NNN 累积决策（单文件，六段式）
└── 技术依据.md          ← 官方来源 + 术语表（glossary 节）
```

Create files lazily — only when you have something to write. If no `docs/决策记录.md` exists, create it when the first decision is resolved; if no `docs/技术依据.md` exists, create it when the first term is resolved. Register each new file in 文档导航 (per doc-index).

**Multi-context repos:** if `docs/文档导航.md` declares per-context glossary homes, follow that map; otherwise keep one `技术依据.md` and tag decisions in `决策记录.md` with their context (e.g. `[ordering]` in the title).

## During the session

### Challenge against the glossary

When the user uses a term that conflicts with the existing language in `技术依据.md`, call it out immediately. "Your glossary defines 'cancellation' as X, but you seem to mean Y — which is it?"

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term. "You're saying 'account' — do you mean the Customer or the User? Those are different things."

### Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about the boundaries between concepts.

### Cross-reference with code

When the user states how something works, check whether the code agrees. If you find a contradiction, surface it: "Your code cancels entire Orders, but you just said partial cancellation is possible — which is right?"

### Update the glossary inline

When a term is resolved, update the glossary section of `技术依据.md` right there. Don't batch these up — capture them as they happen. Use the format in [术语表格式](./CONTEXT-FORMAT.md).

The glossary is totally devoid of implementation details. Do not treat it as a spec, a scratch pad, or a repository for implementation decisions. It is a glossary and nothing else.

### Offer decisions sparingly

Only offer to record a decision in `决策记录.md` when all three are true:

1. **Hard to reverse** — the cost of changing your mind later is meaningful
2. **Surprising without context** — a future reader will wonder "why did they do it this way?"
3. **The result of a real trade-off** — there were genuine alternatives and you picked one for specific reasons

If any of the three is missing, skip it. Use the format in [决策记录格式](./ADR-FORMAT.md).
