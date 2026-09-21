# SuperWork

个人编码生命周期 skill 组合包：17 个 skill 覆盖从需求到集成的完整流程，由入口路由器按生命周期阶段分发，不接管对话、按需触发。

## ★ NB-skills（前沿模型合同版）

`NB-skills/` 是本包的**前沿模型专用变体**：同名单独成套（`superwork` 路由 + 16 个域 skill），按「能力合同」规范改写——**正文为英文**，过程菜谱替换为结果约束 / 边界约束 / 安全约束 / 验收约束（目标 + 能力边界 + 输入输出契约 + 失败升级 + 成本预算 + 停止条件），每个 skill 附 `contract.yaml`（risk_level、permissions、acceptance_criteria、fallback_variant、review_cycle 等完整元数据；references 为 L2 按需加载）。

- skill 名与触发 description 与 `agents-skills/` 相同（保留中文触发锚点），**同一 harness 二选一安装**，勿与父包同装。
- 结构：`NB-skills/<skill>/SKILL.md + contract.yaml`，无构建脚本、无派生目录——本目录即唯一源。
- 安装：`pwsh -File scripts\install-skills.ps1 -Agent claude -Variant NB`（或手动把 `NB-skills/<skill>` junction/复制进目标 harness 的 skills 目录，如 `~/.claude/skills/`）。
- 一致性护栏：`pwsh -File scripts\validate-nb.ps1` 校验每对 SKILL.md/contract.yaml 的同步（id、fallback_variant、引用路径、依赖 skill 名）。

## 特性

- **入口路由器**：`superwork` 元 skill 在任何对话/任务开始时触发，按生命周期路由表分发到具体 skill，避免多 skill 描述的"自由竞争"导致命中错误。
- **17 个 skill**：11 个精选 + 6 个自有（路由元 skill、计划执行、skill 编写、分支收尾、冲突解决、文档导航）。
- **按生命周期互斥分工**：每个 skill 只认领一个阶段（需求→brainstorming；计划→writing-plans；编码→tdd；调试→diagnosing-bugs；完工→verification-before-completion；合并→code-review），description 只写触发条件（SDO）+ 中英文锚点 + 负向排除。
- **多端单源**：`agents-skills/` 为唯一源（11 端通用），`zcode-skills/`（短描述 ≤250 字符）与 `codex-skills/`（+ openai.yaml）由构建脚本派生，改一处即刻生效。

## Skill 清单（17 个）

### 入口路由

- `superwork` — 元 skill。任何对话/任务开始时触发：按生命周期阶段路由任务，装载无条件纪律与红旗清单。

### 自有 skill

- `executing-plans` — 消费已批准的实施计划：逐任务 tdd 循环、逐项打勾、跨会话从计划复选框与 git log 恢复进度、遇阻即停。
- `writing-skills` — 给 skill 做 TDD：description 只写触发条件（SDO）、RED-GREEN-REFACTOR、按失败类型选形式；新增或修改任何 skill 前必读。带 Retro Mode（会话环境复盘）与 agent 文档写作参考。
- `finishing-a-development-branch` — 工作完成后的集成决策：验证全量测试 → 确认 base branch → merge/PR/keep 三选菜单 → 合并结果重跑测试；绝不自动丢弃。
- `resolving-merge-conflicts` — merge/rebase 冲突五步纪律：找双方原始意图、能保则保、绝不发明行为、永不 abort、架构级不兼容时停下找用户。
- `doc-index` — 文档导航协议：`docs/文档导航.md` 是唯一索引门面 + 路径约定声明；产出 skill 落盘后登记一行，无登记不算交付。

### 对齐与规划（开工前）

- `grilling` — 追问原语：决策树 + 轮次推进的访谈，直至无遗留假设；**With-Docs Mode** 在明确点名时同时调起 domain-modeling 落盘 ADR 与词汇表。
- `domain-modeling` — 维护领域词汇表与 ADR，统一命名与沟通语言。
- `brainstorming` — 需求探索与设计确认，三档流程（Spike / Bounded / Architectural），HARD-GATE：未经确认不实现。
- `writing-plans` — 把已批准的 spec 拆成可执行的逐任务实现计划。

### 实现与调试

- `tdd` — 红→绿→重构。垂直切片、单缝测试、测试先行防过度实现；附深模块词汇参考（module/interface/seam/depth/leverage/locality）。
- `diagnosing-bugs` — 硬 bug 诊断循环：先建 tight feedback loop 再修，修复必带回归测试，拒绝臆测。

### 验证与评审（完工前）

- `verification-before-completion` — 无新鲜验证证据不得声称完成。
- `code-review` — Standards + Spec 双轴并行子代理评审，两份报告并列不合并。
- `receiving-code-review` — 评审反馈处理纪律：先验证再动手、拒绝表演性同意、技术性反驳。

### 效率与协作

- `handoff` — 把会话压缩成交接文档，跨会话/换代理不丢上下文。
- `research` — 委托后台代理查一手来源，产出带引用的 Markdown。

## agent 如何发现并使用

agent 不读 README。每次会话它扫描 skills 目录，把每个 SKILL.md 的 `name` + `description` 列入工具列表（progressive disclosure：只加载匹配任务的完整内容）。

- **入口**：`superwork` 元 skill 在任何任务开始时路由分发。
- **自动**：任务与某 skill 的 description 匹配时自动加载（如"帮我 debug 这个 bug" → `diagnosing-bugs`）。
- **显式**：`handoff` 在用户要求交接/压缩会话或上下文出现 harness 压缩通知时调用；`grilling` 的 With-Docs Mode、`writing-skills` 的 Retro Mode 仅明确点名时启用；也可直接要求"用 X skill"。
- **断链恢复**：skill 间用 `Call the Skill tool with "X"` 显式转移；会话中断后从磁盘产物（spec 状态行、plan 复选框、git log）重新定位阶段。

不要往项目自己的 README/CLAUDE.md 里堆本套件的方法论——路由逻辑已在元 skill 正文中，且模型看不到项目 README。

## 安装

### 推荐：安装器（junction 链接，本包即唯一源）

```powershell
pwsh -File scripts\install-skills.ps1 -Agent claude,dsh -DryRun   # 预览
pwsh -File scripts\install-skills.ps1 -Agent claude,dsh,codex     # 安装
pwsh -File scripts\install-skills.ps1 -Agent zcode                # 短描述版（ZCode）
```

已核实路径见 `agents.json`（DSH / Claude Code / Codex / ZCode / Qoder / opencode / Cursor / CodeBuddy / 共享根 `~/.agents/skills` 等）。

### 三目录架构与改动流程

`agents-skills/` 是唯一源（长描述，11 端通用）；`zcode-skills/`（短描述 ≤250 字符）与 `codex-skills/`（+ openai.yaml）由它派生。**改内容只改 agents-skills/（或先改 `scripts/descriptions.json` 再 apply），派生文件夹永不手改**（下次构建会被覆盖）：

```powershell
node scripts\apply-descriptions.cjs --write   # descriptions.json -> agents-skills/*/SKILL.md
node scripts\build-agent-folders.cjs          # agents-skills/ -> zcode-skills/ + codex-skills/
node scripts\build-agent-folders.cjs --check  # 只校验是否需要重建
```

## 多端兼容硬规则（改任何 SKILL.md 前必读）

| 规则                                            | 原因                                                            |
| ----------------------------------------------- | --------------------------------------------------------------- |
| frontmatter 只留 `name` + `description`         | Claude Code 只允许 6 个字段，多写会直接报错                     |
| description 单行 + 双引号                       | 未加引号的 `: ` 被严格 YAML 判为嵌套映射，整个 skill 被静默丢弃 |
| 长描述 ≤ 1024 字符                              | 各端公布的上限                                                  |
| 短描述 ≤ 250 字符且中文锚点靠前                 | ZCode 每轮只注入描述前 250 字符                                 |
| description 必含中文触发锚点                    | 你的输入以中文为主                                              |
| 每文件恰好一个 H1，`name` = 目录名且 kebab-case | 部分 harness 的渲染与校验要求                                   |
| UTF-8 无 BOM                                    | PowerShell 5.1 与部分解析器对 BOM 敏感                          |

## 仓库结构

```
SuperWork\
├── agents-skills\             # ★ 唯一源：17 个 skill 的长描述（11 端通用）
├── zcode-skills\              # 派生：短描述（ZCode 专属）
├── codex-skills\              # 派生：+ agents/openai.yaml（Codex 专属）
├── agents.json                # 各 agent 的 skills 目录登记 + model_tiers（变体选择）+ 复核日期
├── bundle.json                # 装哪些 skill + Codex 策略/短描述表 + NB 变体声明
├── shared\
│   └── disciplines.yaml       # 单源：五条纪律、评审阈值、产物类型/命名、路由硬规则
├── evals\                     # 基线证据存档（RED/GREEN，见 evals/README.md）
├── docs\
│   └── skill-gaps.md          # skill 缺口观察日志（同一缺口 3 次出现才可立项）
├── scripts\
│   ├── descriptions.json      # 描述唯一源（长）
│   ├── apply-descriptions.cjs # descriptions.json -> agents-skills/
│   ├── build-agent-folders.cjs# agents-skills/ -> zcode-skills/ + codex-skills/
│   ├── install-skills.ps1     # 安装器（默认 junction；-Variant NB 装合同版；-StrictRisk 拦 L2）
│   ├── validate-multi.ps1     # 多端合规校验（-AllTargets 含 NB-skills）
│   ├── validate-nb.ps1        # NB-skills 合同/正文同步 + 双变体规则对账
│   ├── audit-docs.ps1         # 项目 docs/ 与文档导航一致性审计
│   ├── check-contract-review.ps1 # contract review_cycle 到期报告（-FailOnDue 可拦）
│   └── normalize-skills.ps1   # frontmatter/H1 规范化（幂等）
└── README.md
```

## 校验与维护

```powershell
node scripts\build-agent-folders.cjs --check         # 派生目录是否过期
pwsh -File scripts\validate-multi.ps1 -AllTargets    # 多端合规（含跨包同名检测）
pwsh -File scripts\validate-nb.ps1                   # NB-skills 合同/正文同步 + 双变体规则对账
pwsh -File scripts\check-contract-review.ps1         # contract 到期审查报告
pwsh -File scripts\audit-docs.ps1 -ProjectRoot <项目路径>   # 项目 docs/ 与文档导航一致性
```

**已知限制**：同一 harness 内按任务切换模型（如 `/model`）时，skill 变体是静态安装产物，无法跟随模型动态切换——NB/agents 变体按 harness 的主力模型在 `agents.json` 的 `model_tiers` 里登记，换主力模型即重装对应变体。

## 平台依赖

- 默认开发机为 Windows；shell 脚本（`start-server.sh` 等）需 Git Bash，或使用同目录的 `.ps1` 等价版本。
- Visual Companion 服务器为 Node 脚本（`server.cjs`），需本机有 Node。

## 许可

本项目为个人自用 skill 组合包，按 MIT 许可分发。