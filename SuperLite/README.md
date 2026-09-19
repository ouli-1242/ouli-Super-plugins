# SuperLite

个人轻量 skill 组合包：面向**日常非代码工作 + 简单项目**。10 个 skill = 9 个领域 skill + 1 个 mini 路由元 skill。

## ★ NB-skills（前沿模型合同版）

`NB-skills/` 是本包的**前沿模型专用变体**：同名单独成套（`superlite` 路由 + 9 个域 skill），按「能力合同」规范改写——**正文为英文**，过程菜谱替换为结果约束 / 边界约束 / 安全约束 / 验收约束（目标 + 能力边界 + 输入输出契约 + 失败升级 + 成本预算 + 停止条件），每个 skill 附 `contract.yaml`（risk_level、permissions、acceptance_criteria、fallback_variant、review_cycle 等完整元数据；references 为 L2 按需加载）。

- skill 名与触发 description 与 `agents-skills/` 相同（保留中文触发锚点），**同一 harness 二选一安装**，勿与父包同装。
- 结构：`NB-skills/<skill>/SKILL.md + contract.yaml`，无构建脚本、无派生目录——本目录即唯一源。
- 安装：把 `NB-skills/<skill>` junction/复制进目标 harness 的 skills 目录（如 `~/.claude/skills/`）。

## 特性

- **轻量**：10 个 skill、mini 路由器（~3KB），固定上下文成本 ~1000 tokens、典型会话 ~1800 tokens。
- **日常优先**：写作、查证、决策、轻量编码一站式——总结材料、查攻略、做决定、写邮件、修小 bug。
- **纪律兜底**：五条无条件纪律的会话级绑定（先测后码 / 证据先于完成 / 合并前评审 / 落盘登记 / 诚实边界+红队），琐碎任务无 skill 触发时也不丢纪律。
- **路由即说明**：`superlite` 元 skill 按紧凑路由表（9 行）分发，重叠裁决内置；不带 Handoffs 网与红旗表。

## Skill 清单（9 + 1 个）

### 入口路由

- `superlite` — mini 路由元 skill。任何任务开始时触发：路由表分发 + 五条无条件纪律的会话级绑定。

### 代码纪律（简单项目用）

- `tdd` — 红→绿循环。铁律：没有失败测试不写生产代码；Watch-It-Fail；只在预先确认的 seam 上测试。
- `diagnosing-bugs` — 硬 bug 六阶段：先建能变红的反馈环，禁止臆测修复；3 次修复失败 = 架构问题。
- `code-review` — Standards + Spec 双轴评审，阈值内联（核心模块 / diff ≥ 15 文件 / 新契约时合并前必做）。
- `verification-before-completion` — 证据先于声称，适用于任何交付物（代码、文档、分析、报告）。

### 通用工作（日常用）

- `writing`（SuperLite 专属）— 任何书面交付物：文档、计划、报告、邮件、配置。目的与读者先行，非琐碎件先大纲后成文。
- `research` — 委托后台代理查一手来源，产出带引用的 Markdown，防编造事实。
- `grilling` — 决策压力测试：决策树 + 轮次 + 前沿的追问，直至无默默假设。
- `handoff` — 把会话压缩成交接文档，落 `docs/交接/`（用户要求或 harness 压缩通知时调用）。
- `doc-index` — 文档导航协议：`docs/文档导航.md` 是唯一索引门面 + 路径约定声明；产出 skill 落盘后登记一行，无登记不算交付。

## 适用场景

日常杂项、信息检索、写作、决策分析、简单项目。

## 设计要点

- `verification-before-completion` 泛化到非代码交付物；`writing` 为本包专属新增。
- 元 skill 是 mini 路由器：无 Handoffs 网、无红旗表，纪律以内嵌 + 会话级绑定双形态存在。

## 安装

### 推荐：安装器（junction 链接，本包即唯一源）

```powershell
pwsh -File scripts\install-skills.ps1 -Agent claude,dsh -DryRun   # 预览
pwsh -File scripts\install-skills.ps1 -Agent claude,dsh,codex     # 安装
pwsh -File scripts\install-skills.ps1 -Agent codex -Copy          # 独立副本
```

已核实路径：DSH `~/.dsh/skills`、Claude Code `~/.claude/skills`、Codex `~/.codex/skills`、Cursor `~/.cursor/skills`、opencode `~/.config/opencode/skills`、`~/.agents/skills`。

### 备选：手工复制

把 `agents-skills/` 内容直接复制进各 agent 的 skills 文件夹（会产生分叉副本，建议用安装器）：

| 工具        | skills 目录                  |
| ----------- | ---------------------------- |
| DSH         | `~/.dsh/skills/`             |
| Claude Code | `~/.claude/skills/`          |
| Codex CLI   | `~/.codex/skills/`           |
| Cursor      | `~/.cursor/skills/`          |
| opencode    | `~/.config/opencode/skills/` |

## 多端兼容硬规则

agent 只靠 `name` + `description` 发现 skill：frontmatter 只留这两个字段；description **单行 + 双引号**（未加引号的 `: ` 会让整个 skill 被静默丢弃）、≤ 500 字符、必含 `中文信号：` 锚点；每文件恰好一个 H1；`name` = 目录名且 kebab-case；UTF-8 无 BOM。

## 仓库结构

```
SuperLite\
├── agents-skills\             # ★ 唯一源：10 个 skill 的长描述（多端通用）
├── zcode-skills\              # 派生：短描述（ZCode 专属）
├── codex-skills\              # 派生：+ agents/openai.yaml（Codex 专属）
├── agents.json                # 各 agent 的 skills 目录登记
├── scripts\
│   ├── descriptions.json      # 描述唯一源（长）
│   ├── apply-descriptions.cjs # descriptions.json -> agents-skills/
│   ├── build-agent-folders.cjs# agents-skills/ -> zcode-skills/ + codex-skills/
│   ├── install-skills.ps1     # 安装器（默认 junction 链接）
│   ├── validate-multi.ps1     # 多端合规校验
│   └── normalize-skills.ps1   # frontmatter/H1 规范化（幂等）
└── README.md
```

## 维护

- 改 description：先改 `scripts/descriptions.json`，再跑 `node scripts\apply-descriptions.cjs --write` 与 `node scripts\build-agent-folders.cjs`。
- 改动后跑 `powershell -File scripts/validate-multi.ps1 -AllTargets`。

## 许可

本项目为个人自用 skill 组合包，按 MIT 许可分发。