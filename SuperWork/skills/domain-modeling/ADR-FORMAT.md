# 决策记录格式 (Decision Record Format)

Decisions accumulate in a **single file** `docs/决策记录.md`, numbered `D-001`, `D-002`, … in order. Do **not** create one file per decision — the value is a readable history in one place. Append new decisions at the end; increment the number by scanning for the highest existing `D-NNN`.

If `docs/决策记录.md` does not exist, create it (lazily, on the first decision) and register it in 文档导航 (per doc-index).

## Six-part template (the standard form)

```md
## D-00N：{Short title of the decision}

- **状态**：已接受 / 已接受，等待… / 已推翻（见 D-00M）
- **背景**：1-3 句，决策前的处境与触发事实。
- **决策**：选了什么。一两句点明。
- **约束**：不可逾越的红线 / 不变式 / 副作用边界。
- **理由**：为什么是这个而不是别的；备选为什么输。

**备选否决**（仅当被否决的选项值得记忆时才写）
- 选项 X — 否决理由，一两句。

**修订**（仅当后续推翻/扩展本决策时才追加一节）
- YYYY-MM-DD：新事实/新决策；指向新 D-00M。
```

前五段（状态/背景/决策/约束/理由）是必填槽；备选否决与修订是可选段，按需追加。一条决策可以只有三行——价值在于记录**做了这个决定以及为什么**，不是填满段落。

## 状态写法

- `已接受` — 默认。
- `已接受，等待…` — 有前置条件未解除时。
- 推翻用 `~~已接受~~ → 已推翻（见 D-00M）`（strikethrough 保留可读历史），**不删除**原条目。
- 部分解除/修订在**修订**节追加，不原地改写决策句。

## When to record a decision (all three must be true)

1. **Hard to reverse** — the cost of changing your mind later is meaningful
2. **Surprising without context** — a future reader will look at the code and wonder "why on earth did they do it this way?"
3. **The result of a real trade-off** — there were genuine alternatives and you picked one for specific reasons

If a decision is easy to reverse, skip it — you'll just reverse it. If it's not surprising, nobody will wonder why. If there was no real alternative, there's nothing to record beyond "we did the obvious thing."

### What qualifies

- **Architectural shape.** Monorepo vs polyrepo; event-sourced write model vs CRUD.
- **Integration patterns between contexts.** Domain events vs synchronous HTTP.
- **Technology choices that carry lock-in.** Database, message bus, auth provider, deployment target — not every library, just the ones that take a quarter to swap out.
- **Boundary and scope decisions.** "Customer data is owned by the Customer context; others reference it by ID only." The explicit no-s are as valuable as the yes-s.
- **Deliberate deviations from the obvious path.** "Manual SQL instead of an ORM because X." Stops the next engineer "fixing" something deliberate.
- **Constraints not visible in the code.** Compliance, partner-API latency ceilings.
- **Rejected alternatives when the rejection is non-obvious.** GraphQL vs REST for subtle reasons — otherwise someone suggests it again in six months.
