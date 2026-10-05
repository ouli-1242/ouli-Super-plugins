---
name: doc-index
description: "Use when a project has no docs/文档导航.md yet (the first artifact needs a home), or when the user asks to organize the project's docs / set up a doc index / \"建个文档导航\" / \"整理一下文档\". Owns the single-source-of-truth doc index: creates the scaffold, declares where each artifact type lives, and is the protocol every producing skill follows to save and register its output. NOT for writing a specific design/plan/log (those skills produce the artifact, then register INTO the index)."
---
# Doc Index (文档导航)

## Purpose

Own the project's single doc index: `docs/文档导航.md` is both the index facade and the declaration of where every artifact type lives — and no artifact is done until it is saved AND registered.

## When to Use / Not Use

- Use: `docs/文档导航.md` doesn't exist and an artifact needs a home; the user asks to set up or reorganize project docs.
- Do NOT use: writing a specific design/plan/log (the producing skill does that, then registers here); registering a single row when the index already exists (a one-line append the producing skill does itself).

## Capability Boundary

- CAN: scaffold the index and directory layout, declare path conventions, define the registration protocol.
- CANNOT: produce the artifacts themselves; allow duplication of authoritative documents.
- Depends on: the filesystem only.

## Input Contract

- Required: a trigger (missing index + artifact needing a home, or an explicit reorganize request).
- Optional: project-specific path overrides (declared in the index).
- Missing behavior: no docs/ at all → scaffold from the default layout below, tailored to the project.

## Output Contract

- `docs/文档导航.md` containing: the directory-structure tree (tailored), naming conventions, 活跃入口 (latest handoff/log), 当前进度 table, root-doc table (决策记录.md / 技术依据.md / 规范.md / 运行.md / 测试.md), and one table per type directory (文档 | 简介) that skills append rows to.
- Optionally a root `AGENTS.md` onboarding file pointing at the index and the five disciplines.
- The protocol every producing skill follows: **(1)** index missing → scaffold it; **(2)** read it to confirm the project's path layout; **(3)** save the artifact to the matching type directory; **(4)** register one row (path + one-line summary).

## Constraints and Prohibitions

- **Default layout**: `docs/` holds 决策记录.md, 技术依据.md, 规范.md, 运行.md, 测试.md at root, plus 调研/ 设计/ 计划/ 日志/ 审查/ 交接/ 实验/ (each with a declared purpose — e.g. 审查/ = review reports, 交接/ = handoffs). Optional directories (归档/, 变更志.md, 追溯矩阵.md, 风险登记.md) exist only when declared in the index.
- **Naming**: `YYYY-MM-DD-<主题>.md` — the topic is mandatory, never date-only; handoffs use `YYYY-MM-DD-交接与剩余任务.md`; same-day same-type merges into ONE file with sections; the `**Status:** draft|approved|completed` line stays first content under the title, greppable.
- **Single authoritative source per concern** — everything else references, never copies; duplication is a defect (决策记录.md owns decisions; 技术依据.md owns sources and terms).
- **Draft isolation**: `docs/计划/` and `docs/设计/` hold approved-and-later only; drafts live in `.scratch/` or carry a `-draft` suffix until approved, then move + register.
- Prohibited: registering artifacts outside the declared layout; re-scaffolding when the index exists.

## Acceptance Criteria

- Every artifact in the repo is findable via 文档导航.md; every registered path exists; the layout declaration matches reality.
- Self-check: does the newest artifact have a registration row? Is any authoritative doc duplicated elsewhere?

## Failure and Escalation

- Project already uses a different docs layout → adopt the project's (the index declares it) rather than forcing the default.
- Registration conflict (two indexes) → merge to one; the facade is singular by definition.

## Cost and Latency Budget

- Scaffold once; registration rows are one line each. Over budget: register the path now, add the summary line at the next touch.

## Examples

- Positive: executing-plans finishes → log saved to `docs/日志/2026-09-19-支付重构.md` → one row appended → done.
- Negative: a review report left only in chat — the artifact does not exist as far as the protocol is concerned.
- Edge: draft spec in `.scratch/` — correctly isolated; on approval it moves to `docs/设计/` and gets its row.

## Evaluation and Observability

- Metrics: artifacts-on-disk-but-unregistered (target 0), duplicate authoritative docs (target 0), stale index vs reality.
- Log: 文档导航.md itself is the record.
