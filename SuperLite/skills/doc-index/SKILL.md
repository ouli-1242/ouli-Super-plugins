---
name: doc-index
description: Use when a project has no docs/文档导航.md yet (the first artifact needs a home), or when the user asks to organize the project's docs / set up a doc index / "建个文档导航" / "整理一下文档". Owns the single-source-of-truth doc index: creates the scaffold, declares where each artifact type lives, and is the protocol every producing skill follows to save and register its output. NOT for writing a specific design/plan/log (those skills produce the artifact, then register INTO the index).
---

# Doc Index (文档导航)

## The Spine

`docs/文档导航.md` is the project's single index facade **and** the declaration of where each artifact type lives. Every producing skill (writing, code-review, handoff, research) follows this protocol:

1. **If `docs/文档导航.md` does not exist** → create the scaffold below (this skill).
2. **Read it** to confirm this project's path layout (defaults to the Chinese set below; a project may declare overrides in the index).
3. **Save the artifact** to the matching type directory.
4. **Register it** — append one row to the matching type table in 文档导航.md (path + one-line summary).

No artifact is "done" until it is saved under `docs/` **and** registered in 文档导航.md. This is the organizing discipline the whole skill set rides on.

## Default Layout

```text
docs/
├── 文档导航.md          ← 本文件（唯一索引门面 + 路径约定声明）
├── 决策记录.md          ← D-001~D-NNN 累积决策（六段式，单文件）
├── 技术依据.md          ← 官方来源/待确认标准 + 术语表（glossary）
├── 规范.md              ← 编码标准（code-review Standards 轴第一来源）
├── 运行.md              ← runbook：环境/跑起来/测试/部署/排障
├── 测试.md              ← 项目级测试策略（seams/覆盖率目标/故意不测清单）
├── 调研/                ← 可行性快验/Spike 产物（可弃但留痕）
├── 设计/                ← 冻结的模块契约/spec
├── 计划/                ← 实施计划
├── 日志/                ← 按日开发记录
├── 审查/                ← 代码审查报告
├── 交接/                ← 阶段末交接与剩余任务
└── 实验/                ← 经验数据/实验记录 + 数据资产
```

Optional (declare in the index to enable): `归档/`（被推翻的计划/设计迁此，保持活跃目录整洁）、`变更志.md`（按版本/发布切片的变更）、`追溯矩阵.md`、`风险登记.md`。

## Naming Conventions

- 计划 / 设计 / 日志 / 审查 / 调研 / 实验：`YYYY-MM-DD-简短主题.md`（**必须带主题，不要只写日期**）。
- 交接：`YYYY-MM-DD-交接与剩余任务.md`。
- **同一天同一类合并为一份**，内部分节维护，不拆多文件。
- Status 行 `**Status:** draft|approved|completed` 作为标题下第一行内容，保持可 grep。

## Authoritative Single Source

Each cross-cutting concern may have **ONE** authoritative doc (e.g. `docs/<concern>/design-spec.md`); everything else references it, never copies. 决策记录.md is the single source for decisions; 技术依据.md for sources and terms. Duplication is a defect — link, don't copy.

## Draft Isolation

`docs/计划/` and `docs/设计/` hold **approved-and-later only**. Draft-stage specs/plans live in `.scratch/` or carry a `-draft` suffix; on approval, rename/move into the formal directory and register. This keeps the active directories clean and the status line trustworthy.

## Scaffold (create when 文档导航.md is missing)

```markdown
# 文档导航

> 最后更新：YYYY-MM-DD ｜ 本文件是 docs/ 的唯一索引门面，新增文档请同步登记。

## 目录结构

[copy the Default Layout tree above, tailored to this project]

## 命名约定

[copy the Naming Conventions above]

## 活跃入口

- 交接：[最新交接路径]（当前权威）
- 最新日志：[最新日志路径]

## 当前进度

| 里程碑 | 状态 |
|---|---|
| ... | 进行中/完成 |

## 根文档

| 文档 | 简介 |
|---|---|
| 决策记录.md | D-001~ 关键决策与理由 |
| 技术依据.md | 已确认官方来源 + 待补充标准 + 术语 |
| 规范.md | 编码标准：命名/结构/错误处理/测试约定/禁用模式；注明测试代码位置（如 `backend/tests/`） |
| 运行.md | 环境装法 + 启动/测试/构建/部署命令 + 常见报错 |
| 测试.md | 整体 seam + 覆盖率目标 + 故意不测清单 |

## 计划 / 设计 / 日志 / 审查 / 交接 / 实验 / 调研

[one table per type, columns: 文档 | 简介 — append a row each time a skill produces an artifact of that type]
```

### Also create root `AGENTS.md` (agent onboarding) if absent

```markdown
# AGENTS.md

本项目用 SuperLite skill 套件（docs/ 中文文档约定）。开工前先读：

- `docs/文档导航.md` — 文档索引门面（所有产物的入口）
- `docs/决策记录.md` — 关键决策与理由（D-001~）
- `docs/规范.md` — 编码标准（code-review 按此查）
- `docs/运行.md` — 怎么跑/测/部署
- `docs/技术依据.md` — 官方来源 + 术语表

产物按类型落 `docs/<类型>/` 并在文档导航登记。无条件纪律：先测后码、证据先于声称、合并前评审、产物落盘+登记、诚实边界+红队自查。
```

## When This Skill Triggers

- A producing skill is about to save an artifact and `docs/文档导航.md` is missing → run this skill's scaffold, then proceed.
- The user explicitly asks to set up / reorganize project docs.
- Do NOT trigger just to register a single new row when the index already exists — that is a one-line append the producing skill does itself.
