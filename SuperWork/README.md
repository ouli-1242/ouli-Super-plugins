# SuperWork

Ouli 的个人 skill 组合包（plugin）。从 [superpowers](https://github.com/obra/superpowers) 与
[matt-skills](https://github.com/mattpocock/skills) 等流行 skill 库精选，共
17 个 skill：11 个精选 + 6 个 SuperWork 自有（路由元 skill、计划执行、skill
编写、分支收尾、冲突解决、文档导航），基于全局 `AGENTS.md` 的
原则组合，按需触发，不接管对话。

## v2.2.0 多端通用打包（一个源 + 两个派生）

让同一套 skill 在 11 个 harness 上都能被可靠触发，并消灭副本漂移：

- **`agents-skills/` 是唯一源**：frontmatter 只留 `name` + `description`（Claude Code 只允许 6 个字段，多写 `argument-hint` 会直接报错；本包历史的该字段已移除）；description 单行加双引号——**未加引号的 `": "` 会被严格 YAML 判为嵌套映射，整个 skill 被静默丢弃**，本包曾有 3 个中招（含路由器）。
- **`codex-skills/`**：同内容 + Codex 专属 `agents/openai.yaml`；`handoff` 等标记 `allow_implicit_invocation: false`（不该自动触发）。此前该文件只有部分 skill 有、且与正文自相矛盾，现已统一生成。
- **`zcode-skills/`**：ZCode 官方文档写明每轮只把描述的前 **250 字符**注入上下文，故派生短版（保留中文锚点），由构建脚本自动生成、不手工维护。
- **描述预算**：长描述全部 ≤500 字符（DSH 目录截断线，实测最长 486），且含中文触发锚点；各端上限（Claude 1536 / Codex 1024 / opencode 1024 / Qoder 1024）均满足。
- **新增工具**：`scripts/descriptions.json`（描述唯一源）、`apply-descriptions.cjs`、`build-agent-folders.cjs`、`install-skills.ps1`（多端路径 + junction 安装）、`validate-multi.ps1`（多端合规 + 跨包同名检测）、`normalize-skills.ps1`。旧的 `skills/` + `scripts/validate.ps1` 已合并删除。
- **实测修复**：7 个 skill 曾因 YAML 语法在 DSH 上完全不可见；转义顺序 bug 会让描述逐次劣化——均已修复并回归验证（3 包 × 3 文件夹共 117 个 SKILL.md 零问题）。

## v2.1.0 吸收上游新增能力（retro / writing-for-agents / codebase-design）

上游两库全量重扫：superpowers 14 个 skill 零新增（全部 v1.3.0 已裁决）；mattpocock/skills 重组为
engineering / productivity / in-progress / misc / deprecated 五分类，engineering 全是已裁决项，
增量在新分类里。三个吸收、其余拒绝，且**均不新增 skill 目录**（守住 17 个的发现位数量）：

- **retro → 并入 `writing-skills`（Retro Mode）**。retro（mattpocock，in-progress，作者自标
  STUB）对会话做环境复盘：导航 / 自动化检查 / 评审规则 / 常驻 steering 文件 / 工具经济性 /
  no-ops / 信息可达性七类候选，按严重度排列后逐项实施。补上链条终点缺口：merge 之后没有
  学习回路。改造点：素材源从"翻会话日志"改为优先读 `docs/` 脊柱产物（日志/审查/交接/计划
  复选框/git log）；实施环节回接 writing-skills 自己的铁律（改 AGENTS.md 行、评审规则、skill
  正文都算编辑既有 skill，先测后写）；补充"实施角色上下文压力最大、评审角色最小，标准执法
  推给评审、机械可查推给自动化"的排序原则。七类清单与排序原则在
  `writing-skills/references/retro.md`，正文只留三步骨架与显式请求限定（同 grilling
  With-Docs Mode 惯例：仅用户点名"复盘/retro"时启用，路由表加对应行）。
- **writing-for-agents → 吸收为 `writing-skills/references/agent-docs.md`**。context pointer
  （措辞决定触发可靠性，front-load 首词、每分支一个触发词）、双负载（context load vs
  cognitive load）、信息层级（steps / in-file reference / disclosed reference 三层 +
  progressive disclosure + co-location + sprawl）、完成判据（clarity + demand）、leading
  words（含 negation 失效模式）、修剪纪律、调用方式选择（model-invoked vs user-invoked 的
  负载交换）与 router skill 一节（映射到 superwork：新 skill 登记路由表而非自立路由）。
  不独立成 skill 的理由：触发面与 writing-skills 正面相撞（都认领"写 skill / 写 AGENTS.md"）。
- **codebase-design → 吸收为 `tdd/deep-modules.md`**。深模块词汇表（module / interface /
  implementation / depth / seam / adapter / leverage / locality，Ousterhout + Feathers 体系）、
  deep vs shallow、四原则（删除测试、接口即测试面、两个 adapter 才是真 seam 等）、可测试性
  设计三则、被拒框架。挂进 tdd 的 Seams 小节（"接口形状本身待定"段落）——seam 确认纪律
  v1.1.0 就在，缺的正是这套词汇。不上游的 DEEPENING.md / DESIGN-IT-TWICE.md 两个延伸文件。
  不独立成 skill 的理由：触发面会与 brainstorming 设计阶段抢领地（独占病前科）；作为 tdd 的
  词汇参考在 seam 确认时刻按需加载，零新增发现位。brainstorming 正文不加引用——设计阶段
  的模块决策到 tdd 的 seam 确认时还会再过一遍，避免跨 skill 文件引用。

**拒绝项**（沿用 v1.3.0 裁决基准）：`implement-spec`（worktree + 子代理并发编排，
executing-plans 已覆盖编排层）；`claude-handoff`（绑死 `claude --bg` 机制）；`ask-matt`
（路由器，superwork 元 skill 等价物）；`grill-me`（无工作区版 grilling）；`loop-me` / `teach`
/ `writing-beats` / `writing-fragments` / `writing-shape`（个人工作流、教学、写作工坊，非编码
生命周期域）；`misc/` 四件套（git-guardrails、setup-pre-commit 等，环境配置基础设施，同
v1.2.0 拒 ECC infra 理由）；`to-questionnaire`（决策问卷，同 wizard 的"人机向导小众"）；
`wait-what`（一句话复述重置，可并入 domain-modeling 当模式，不值得独立发现位）。

两个来源之外的 2026 生态扫描（Firecrawl / Snyk 榜单、awesomeskill.ai、addyosmani 重访）：
主流仍是领域型 / 质量属性型 skill，属 v1.3.0 已划出范围，无值得破例的生命周期纪律来源。

已收录 skill 与上游存在漂移（tdd / code-review / diagnosing-bugs 等 1–4 个文件不等），抽样
核对均为本地定制（description 重写、中文文档约定），无需紧急回并；diagnosing-bugs 上游改过
`hitl-loop.template.sh`，下次升版本时人工比对。

## v2.0.0 仓库精简 + 中文文档约定重构

两件事：

**仓库精简**：删除平台清单（`.claude-plugin`/`.codex-plugin`/`.cursor-plugin`/`.opencode`）与人类参考副本 `AGENTS.md`/`CLAUDE.md`。用法改为**把 `skills/` 内容直接复制进各 agent 自己的 skills 文件夹**——agent 自动扫描 SKILL.md，清单只在"装插件"流程才需要，手动复制场景纯冗余。`scripts/validate.ps1` 的清单检查改为可选（缺失即跳过）。

**中文文档约定重构**：产出路径从 `docs/superwork/specs|plans/` 与 `docs/adr/0001-*.md` 迁移为扁平中文目录，并补上真实项目验证过、原套件缺失的组织纪律：

- 路径迁移：`docs/设计/`（spec）、`docs/计划/`、`docs/决策记录.md`（D-NNN 累积六段式，替代一文件一决策的 `docs/adr/`）、`docs/技术依据.md`（官方来源 + 术语表，替代 `CONTEXT.md`）。
- 新增产物类型：`docs/日志/`（按日开发记录，原无）、`docs/审查/`（评审报告落盘，原只输出对话）、`docs/交接/`（入工作区，原写临时目录）、`docs/实验/`（经验数据，原无）、`docs/调研/`（Spike 可弃留痕，原无）。
- 新增 spine：`docs/文档导航.md` 唯一索引门面 + 路径约定声明——产出 skill 落盘后在导航登记一行，无登记不算交付。
- 新增 skill：`doc-index`（导航脚手架 + 落盘登记协议）。实验记录降为 `docs/实验/` 约定（六段式结构见 doc-index），无专属 skill。
- 新增 2 无条件纪律：#4 产物落盘并登记文档导航；#5 诚实边界 + 偏离声明 + 红队自查。
- 约定：命名必带主题不写纯日期、同日同类合并一份、草稿进 `.scratch/` 批准后迁入、每个横切关注点可有唯一权威文档（引用不复制）。

## v1.5.0 自洽性修复（全量深度审查）

对 16 个 skill 做逐字交叉审查（引用完整性、阶段编号一致性、SDO 合规、
孤儿文件、链条闭合），修复项：

- **修 bug**：元 skill 红旗表两处过期阶段编号（v1.2.0 重编号的遗留）；
  finishing 的 merge 流程补冲突分支（router 声明了转移但正文缺失，导致
  遇冲突永远不会调 resolving-merge-conflicts）
- **删孤儿**：`brainstorming/spec-document-reviewer-prompt.md`、
  `writing-plans/plan-document-reviewer-prompt.md`（v1.1.0 改自审制后
  零引用的死文件）
- **SDO 修剪**（遵守 writing-skills 自己定的"description 绝不总结 workflow"）：
  superwork 的 Routes 列表（还漏了 executing-plans/finishing 两个阶段，
  一并解决）、tdd/code-review/finishing 的流程句；元 skill description 改为
  强制读正文（"don't route from memory"）
- **补链**：router Handoffs 加 verification→finishing（闭合孤立 tdd 路径
  的集成链）；tdd 加分支纪律（never start on main，原只有 executing-plans
  有）；code-review 补无子代理时的降级路径（自查两轴、报告仍分离）
- **尺寸**：diagnosing-bugs 挪"无法建环"小节进 references（原 8192 字节
  正好卡 8KB 线，无编辑余量）

已知未修：openai.yaml 覆盖 7/17（Codex UI 元数据，功能可选，待统一补齐）。

## v1.4.0 精简合并

对 17 个 skill 做逐对合并审查（判据：薄壳优先合、固定链条单父可合；多父
复用、独立触发面、8KB 上限、触发面污染不合），结论只有一处真冗余：

- **合并**：`grill-with-docs`（685 字节薄壳，正文仅一句"调 grilling +
  domain-modeling"）并入 `grilling` 的 **With-Docs Mode**——用户明确点名
  "grill-with-docs / 追问并落盘 ADR"时才同时调 domain-modeling，普通
  grill 请求不启用，保留原 manual-trigger 语义。17 → 16。
- **审查后不合**：receiving-code-review（独立触发面：外部评审意见）；
  verification / tdd / finishing（多父横切纪律）；executing-plans 与
  writing-plans（12KB 超 8KB 限 + 跨会话恢复是独立入口）；brainstorming
  与 grilling（触发语义相反，合并 = 独占病复发）。

## v1.3.0 补全裁决（demo 参考库全量审查）

v1.2.0 的裁决是抽样式的；v1.3.0 把 `C:\Users\ouli\Desktop\demo` 六个库
（superpowers、mattpocock skills、ECC、addyosmani agent-skills、agents
文档库、skills-main）全部过完后的增量裁决：

| 候选 | 来源 | 裁决 | 核心理由 |
|---|---|---|---|
| `resolving-merge-conflicts` | matt | 采纳 | 全 pack 无一覆盖 merge/rebase 冲突；1KB、5 步纪律（找双方原始意图、绝不发明行为、永不 abort）、触发零歧义 |
| `finishing-a-development-branch` | superpowers | 采纳（改造） | 链条终点缺口：verification 之后"如何集成"无纪律（merge/PR/keep 菜单、绝不自动丢弃、确认 base、合并结果重跑测试）。剥掉 worktree 机制（SuperWork 不管 worktree） |
| `doubt-driven-development` | addyosmani | 拒绝 | 机制好但触发词 "non-trivial decision" 过宽——会复现 brainstorming 独占病；价值已由 grilling/code-review/全局对抗性审查原则部分覆盖 |
| `spec-miner`（agent） | ECC | 拒绝 | 深绑 OpenSpec 生态（openspec/ 目录、delta 格式、配套 agents）；能力真实但需完全重设计 |
| wayfinder / wizard / implement / triage / to-spec / to-tickets / improve-codebase-architecture / prototype | matt | 拒绝 | 依次：依赖 issue tracker / 人机向导小众 / 被现有链条覆盖 / issue 运维超范围 / 被 brainstorming + writing-plans 覆盖 / 同左 / 被 brainstorming 覆盖 / spike 路径已覆盖 |
| addyosmani agent-skills 其余 22 skill | addyosmani | 拒绝 | 11 个与现有 skill 一一对应（idea-refine≈brainstorming、interview-me≈grilling、planning≈writing-plans 等）；其余为质量属性域（performance/security/observability/CI），非生命周期纪律 |
| superpowers 剩余 7 skill | superpowers | 拒绝 | requesting-code-review 被 code-review 覆盖；subagent-driven 被 executing-plans 覆盖；worktree/parallel-agents 工具型或范围外；systematic-debugging / test-driven 已用 matt 版替换 |
| ECC commands / contexts / workflows / scripts | ECC | 拒绝 | /plan、/code-review 与现有 skill 重叠；skill-health、auto-update、doctor 是发行基础设施（validate.ps1 是等价物）；orch-review 是 Claude-Code 原生 workflow 格式；contexts 的纪律已内嵌在 skill 里 |
| agent-skills 格式规范 / skills-main | — | 无需动作 | 确认格式合规（name+description frontmatter、自包含、per-skill references 是可移植正确选择） |

## v1.2.0 升级裁决（抽样审查）

对 demo 参考库（superpowers / ECC / agents-repo）的候选能力逐一裁决，
基准：是否填补生命周期缺口？是否已有 skill 覆盖？维护成本是否值得？

| 候选 | 裁决 | 核心理由 |
|---|---|---|
| `executing-plans`（superpowers） | 采纳 | writing-plans 产出计划后无消费纪律；tdd 管单任务循环不管多任务编排。链条 plan→execution 缺环补上 |
| `writing-skills`（superpowers） | 采纳 | SuperWork 本身是持续维护的产品；"给 skill 做 TDD"（description 只写触发条件、堵合理化漏洞）正是 v1.0.0 触发失效的解药 |
| plugin-eval 静态检查（agents-repo） | 轻量采纳 | 固化为 `scripts/validate.ps1`：frontmatter/触发词/8KB/mojibake/引用/清单六项检查，升级前必跑 |
| SessionStart hook（superpowers） | 拒绝 | hooks 仅 3/5 平台生效；元 skill 已覆盖全对话触发；hook 每会话强制烧 token，违反"不接管对话" |
| 30+ agents（ECC） | 拒绝 | 委派已内嵌在 skill 里（code-review/research 自带子代理）；独立 agents = 30+ 发现位竞争者，正是 v1.0.0 病根 |
| ~100 skills（ECC） | 拒绝 | 抽样：santa-method ≈ code-review；verification-loop ≈ verification-before-completion；search-first ≈ research；领域类（springboot/swift/seo/video）与通用生命周期论文不符 |
| commands/rules/contexts（ECC） | 拒绝 | ECC 的发行版基础设施，个人本地包不需要 |

## 触发架构（v1.1.0 重构）

skill 调用难、只会命中 brainstorming 的根因是：模型每轮只看到每个 skill 的
`name + description`（progressive disclosure），旧版 brainstorming 的
`You MUST use this before any creative work` 触发面覆盖了几乎全部开发任务，
其余 skill 被结构性遮蔽；且 skill 正文里的转移指令只有加载后才可见，链条
一断就再也接不上。v1.1.0 从三层修复：

1. **元 skill `superwork`（入口路由器）**：description 声明"任何对话/任务开
   始时"触发。正文装生命周期路由表（阶段互斥分工 + 中英文触发信号）、
   无条件纪律、红旗清单、skill 间转移约定。原来的 CLAUDE.md 路由表是模型
   看不到的死文档，现全部迁入这里。
2. **description 按生命周期互斥分工**：每个 skill 只认领一个阶段
   （需求模糊→brainstorming；设计批准→writing-plans；写代码→tdd；硬
   bug→diagnosing-bugs；声称完成→verification-before-completion；合并
   前→code-review），并带中英文触发词与负向排除。
3. **转移指令显式化**：所有"下一步用 X"改为 `Call the Skill tool with "X"`
   式显式调用（mattpocock invocation.md 的结论：命中率最高），会话断链后
   也能从磁盘产物（spec 状态行、plan 复选框、git log）重新定位阶段。

另有结构规范：SKILL.md 正文控制在 8KB 内（Codex 硬截断线），超长内容拆
`references/`（brainstorming、diagnosing-bugs 已拆）。

## 组合依据（对应 AGENTS.md 原则）

| 原则                                 | 选用 skill                                                  | 来源        |
| ------------------------------------ | ----------------------------------------------------------- | ----------- |
| No Speculation：不确定就问           | `grilling`（With-Docs Mode 落盘 ADR 与词汇表）              | matt        |
| 复杂任务先计划，先给方案             | `brainstorming`                                             | superpowers |
| Truthfulness：证据验证后才能声称完成 | `verification-before-completion`                            | superpowers |
| 结果导向、最小改动                   | `tdd`（先测后码，防止过度实现）                             | matt        |
| 自我纠错：第一性原理、对抗性审查     | `diagnosing-bugs`（拒绝臆测，先建反馈环）                   | matt        |
| 交付前验证                           | `code-review`（规范 + spec 双轴评审）                       | matt        |
| 效率：会话/上下文不浪费              | `handoff` `research`                                        | matt        |

## Skill 清单（17 个）

### 入口路由

- `superwork` — 元 skill（v1.1.0）。任何对话/任务开始时触发：按生命周期
  阶段把任务路由到具体 skill，装载无条件纪律与红旗清单。是模型侧的
  权威路由表。

### SuperWork 自有（从源库改造）

- `executing-plans`（v1.2.0，superpowers）— 消费已批准的实施计划：逐任务
  tdd 循环、逐项打勾、跨会话从计划复选框与 git log 恢复进度、遇阻即停。
  衔接 writing-plans 与 tdd 之间缺失的编排层。
- `writing-skills`（v1.2.0，superpowers）— 给 skill 做 TDD：description 只写
  触发条件不写流程（SDO 原则）、RED-GREEN-REFACTOR、按失败类型选形式
  （禁令/配方/结构槽/条件句）、堵合理化漏洞。新增或修改任何 skill 前必读。
  v2.1.0 起带 **Retro Mode**（会话环境复盘，七类清单见
  `references/retro.md`，仅显式请求触发）与 `references/agent-docs.md`
  （agent 文档写作：context pointer、双负载、信息层级、leading words，
  吸收自 matt writing-for-agents）。
- `finishing-a-development-branch`（v1.3.0，superpowers）— 工作完成后的
  集成决策：验证全量测试 → 确认 base branch → merge/PR/keep 三选菜单 →
  合并结果重跑测试；绝不自动丢弃，丢弃需逐字确认 "discard"。
- `resolving-merge-conflicts`（v1.3.0，matt）— merge/rebase 冲突五步纪律：
  找双方原始意图、能保则保、绝不发明行为、永不 abort、冲突暴露架构级
  不兼容时停下来找用户。

### 文档导航（v2.0.0）

- `doc-index`（v2.0.0）— 文档导航协议：`docs/文档导航.md` 是唯一索引门面 +
  路径约定声明。产出 skill 落盘后在导航登记一行，无登记不算交付；缺失时本
  skill 生成脚手架。

### 对齐与规划（开工前）

- `grilling` — 追问原语：按"决策树 + 轮次 + 前沿"推进的访谈，每问附推荐答案，
  直至无遗留假设。**With-Docs Mode**（v1.4.0 吸收自 grill-with-docs）：用户
  明确点名时同时调起 domain-modeling，把术语与决策落盘成 ADR 与词汇表。
- `domain-modeling` — 维护领域词汇表（CONTEXT.md）与 ADR，统一命名与沟通语言。
  `grilling` With-Docs Mode 的搭档。
- `brainstorming` — 功能/组件开发前的需求探索与设计确认。三档流程（Spike /
  Bounded / Architectural），HARD-GATE：未经确认不实现。
- `writing-plans` — 把已批准的 spec 拆成可执行的逐任务实现计划（bite-sized
  tasks、TDD、无占位符）。brainstorming 流程的下游，executing-plans 的上游。

### 实现与调试

- `tdd` — 红→绿→重构。垂直切片、单缝测试、测试先行防过度实现。附
  `tests.md`/`mocking.md` 参考；v2.1.0 起另附 `deep-modules.md`（深模块
  词汇表：module/interface/seam/depth/leverage/locality，吸收自 matt
  codebase-design，供 Seams 小节的接口形状确认按需加载）。
- `diagnosing-bugs` — 硬 bug 诊断循环：先建立 tight feedback loop 再修，
  修复必须带回归测试，拒绝臆测。

### 验证与评审（完工前）

- `verification-before-completion` — 铁律：无新鲜验证证据不得声称完成。
  防"假完成"，是 Truthfulness 原则的执行器。
- `code-review` — 双轴并行子代理评审（Standards + Spec），两份报告并列不合并。
- `receiving-code-review` — 收到评审反馈后的处理纪律：先验证再动手、拒绝表演性
  同意、YAGNI 检查、技术性反驳。`code-review` 的配套环节。

### 效率与协作

- `handoff` — 把会话压缩成交接文档，跨会话/换代理不丢上下文。
- `research` — 委托后台代理查文档/API，产出带引用的 Markdown。

## agent 如何发现并使用

agent 不读 README。每次会话它会扫描 skills 并把每个 SKILL.md 的
`name` + `description` 列入工具列表（progressive disclosure：只加载匹配任务
的完整内容）。v1.1.0 的触发设计：

- **入口**：`superwork` 元 skill 在任何任务开始时触发，按生命周期路由表
  分发到具体 skill——不再依赖 description 之间的自由竞争（那会导致
  brainstorming 独占一切）
- **自动**：任务与某 skill 的 `description` 匹配时 agent 自行加载（如
  "帮我 debug 这个 bug" → `diagnosing-bugs`；description 带中英文触发词）
- **显式与自动**：`handoff`（v2.1.1 起移除 disable-model-invocation）在用户要求交接或上下文
  跨过分档压缩线时调用（≤256k 70/90、≤500k 60/75、1M 40/60）：start 线写好交接文档，hard 线写完
  并提示用户压缩——真实压缩由 harness 执行，交接文档保证无损；`grilling` 的 With-Docs Mode 也仅在明确点名时启用；
  也可直接要求"用 X skill"
- **断链恢复**：skill 之间用 `Call the Skill tool with "X"` 显式转移；会话
  中断后从磁盘产物（spec 状态行、plan 复选框、git log）重新定位阶段

若需要让 agent 理解整套工作流（如"开工前先 grill、完工前先验证"），路由
逻辑已内置于 `skills/superwork/SKILL.md` 元 skill——不要再往 README 或
CLAUDE.md 里堆方法论（模型看不到它们）。

## 安装（多端：一个通用源 + 两个派生）

**`agents-skills/` 是唯一源**（长描述，只含 `name` + `description`），没有第二份等价副本。另外两个文件夹由它派生：

| 文件夹 | 内容 | 给谁用 |
|---|---|---|
| **`agents-skills/`** | **源：长描述原样** | DSH、Claude Code、Codex、Cursor、Qoder、Gemini CLI、opencode、CodeBuddy、Kimi、Grok——它们都只读 `name` + `description`。其中多家直接扫描共享根 `~/.agents/skills/`，装一次多端可见 |
| `codex-skills/` | 派生：同上 + `agents/openai.yaml` | Codex 专属：UI 元数据与调用策略（`policy.allow_implicit_invocation`）。Codex 在 SKILL.md 里没有别的端不认的字段，所以只差这一个可选文件 |
| `zcode-skills/` | 派生：**短描述**（≤250 字符，保留中文锚点） | ZCode 专属：官方文档写明每轮只把描述的前 **250 字符**注入上下文，超出部分模型看不到 |

```powershell
node scripts\apply-descriptions.cjs --write   # descriptions.json -> agents-skills/*/SKILL.md
node scripts\build-agent-folders.cjs          # agents-skills/ -> zcode-skills/ + codex-skills/
node scripts\build-agent-folders.cjs --check  # 只校验是否需要重建
```

改内容只改 `agents-skills/`（或先改 `scripts/descriptions.json` 再跑 apply）；**派生文件夹永远不要手改**，下次构建会被覆盖。

### 安装到各 agent

```powershell
pwsh -File scripts\install-skills.ps1 -Agent claude,dsh -DryRun   # 预览
pwsh -File scripts\install-skills.ps1 -Agent claude,dsh,codex     # 默认 junction 链接
pwsh -File scripts\install-skills.ps1 -Agent zcode                # 装派生的短描述版
```

已核实路径见 `agents.json`（DSH `~/.dsh/skills`、Claude Code `~/.claude/skills`、Codex `~/.codex/skills`、ZCode `~/.zcode/skills`、Qoder `~/.qoder-cn/skills`、opencode `~/.config/opencode/skills`、CodeBuddy `~/.codebuddy/skills`、共享根 `~/.agents/skills`；Cursor / Gemini / Grok / Kimi 走共享根或各自的 `~/.<name>/skills`）。

### 多端兼容硬规则（改任何 SKILL.md 前必读）

| 规则 | 为什么 |
|---|---|
| frontmatter 只留 `name` + `description` | **Claude Code 只允许 6 个字段**（含 `allowed-tools`/`license`/`metadata`/`compatibility`），多写 `argument-hint` 之类会直接报错；本包历史上曾带过 |
| description **单行 + 双引号** | 未加引号的 `: ` 被严格 YAML 判为嵌套映射，**整个 skill 被静默丢弃**（本包曾有 3 个中招，含路由器） |
| 长描述 ≤ 1024 字符 | 各端公布的上限（opencode/Qoder/ZCode 均 1024）；本包当前最长 514 |
| 短描述 ≤ 250 字符且中文锚点在前 220 | ZCode 的注入窗口；由构建脚本从长描述派生，不手工维护 |
| description 必须含中文触发锚点 | 你的输入以中文为主；锚点必须在值里（不能拆到单独字段） |
| 每个文件恰好一个 H1 | 部分 harness 用 H1 渲染标题 |
| `name` = 目录名、kebab-case、≤64 | DSH 强制 regex，opencode 另有 1–64 与禁止 `--` 的规则 |
| UTF-8 无 BOM | PowerShell 5.1 与部分解析器对 BOM 敏感 |

平台专属增强一律不进 frontmatter；Codex 的放在 `codex-skills/<skill>/agents/openai.yaml`，缺失不影响其他端。

### 仓库结构

```
SuperWork\
├── agents-skills\             # ★ 唯一源：17 个 skill 的长描述（11 端通用）
├── zcode-skills\              # 派生：短描述（≤250 字符，ZCode 专属）
├── codex-skills\              # 派生：+ agents/openai.yaml（Codex 专属）
├── agents.json                # 各 agent 的 skills 目录登记（安装器读它）
├── bundle.json                # 装哪些 skill + Codex 策略/短描述表
├── scripts\
│   ├── descriptions.json      # 描述唯一源（长）；改这里再 apply
│   ├── apply-descriptions.cjs # descriptions.json -> agents-skills/*/SKILL.md
│   ├── build-agent-folders.cjs# agents-skills/ -> zcode-skills/ + codex-skills/
│   ├── install-skills.ps1     # 安装器（默认 junction 链接）
│   ├── validate-multi.ps1     # 多端合规校验（升级前必跑）
│   ├── normalize-skills.ps1   # frontmatter/H1 规范化（幂等）
└── README.md
```

```powershell
node scripts\apply-descriptions.cjs --write          # 描述改动落地到 agents-skills/
node scripts\build-agent-folders.cjs                 # 重建 zcode-skills/ + codex-skills/
node scripts\build-agent-folders.cjs --check         # 只校验是否需要重建
pwsh -File scripts\validate-multi.ps1 -AllTargets    # 多端合规（含跨包同名检测）
```

## 平台依赖

- 默认开发机是 Windows。shell 脚本（`start-server.sh` / `stop-server.sh` /
  `hitl-loop.template.sh`）需要 Git Bash（`bash xxx.sh` 调用），或使用同目录的
  `.ps1` 等价版本。
- Visual Companion 服务器是 Node 脚本（`server.cjs`），需本机有 Node。

## 已定制的文件

以下文件相对源仓库有本地定制，从源仓库更新时需要人工合并（不要直接覆盖）：

- v2.1.0 新增：`skills/writing-skills/references/retro.md`（matt retro 改造：
  素材源改为 docs/ 脊柱产物优先、实施环节回接铁律、补实施/评审上下文压力
  排序原则）；`skills/writing-skills/references/agent-docs.md`（matt
  writing-for-agents + SKILL-MECHANICS 吸收，router 一节映射到 superwork）；
  `skills/tdd/deep-modules.md`（matt codebase-design 吸收，去
  DEEPENING/DESIGN-IT-TWICE 延伸引用）。改 `writing-skills/SKILL.md`
  （description 吸收复盘触发词 + Retro Mode 小节 + agent-docs 指针）、
  `tdd/SKILL.md`（Seams 小节加深模块词汇指针）、元 skill（路由表加复盘行 +
  manual-trigger 说明加 Retro Mode）
- v1.4.0：删除 `skills/grill-with-docs/`（薄壳并入 grilling）；grilling 加
  With-Docs Mode 小节并重写 description（吸收 grill-with-docs 触发词）；
  domain-modeling / 元 skill / 四个清单 / README / CLAUDE.md 同步去引用；
  版本升至 1.4.0
- v1.3.0 新增：`skills/finishing-a-development-branch/SKILL.md`（从
  superpowers 改造：删 worktree 检测/清理机制（Step 2 环境捕获与 Step 6），
  保留测试门禁、base 确认、三选菜单、discard 逐字确认、合并结果重跑测试、
  合理化反驳表；description 重写为中英触发词 + 负向排除）
- v1.3.0 新增：`skills/resolving-merge-conflicts/SKILL.md`（matt 原版
  近乎原样采纳 + description 重写 + 尾部补"架构级不兼容时停下找用户"）
- v1.3.0：元 skill 路由表加阶段 8（finishing）与冲突事件行；Handoffs 加
  executing-plans 三连调与 finishing→resolving 转移；executing-plans Step 3
  改为三连调（code-review → verification → finishing）
- v1.3.0：README 裁决表拆为"v1.2.0 抽样审查"+"v1.3.0 全量补全"两段
  （修正 v1.2.0 表述——此前写的"逐一裁决"实为抽样）
- v1.2.0 新增：`skills/executing-plans/SKILL.md`（从 superpowers 改造：删
  worktree / subagent-driven-development / finishing-a-development-branch 引用，
  接入 SuperWork 链条——per-task 调 tdd、终态调 code-review +
  verification-before-completion、断链恢复）
- v1.2.0 新增：`skills/writing-skills/SKILL.md`（从 superpowers 10KB 精简：
  删 anthropic-best-practices / testing-skills-with-subagents /
  persuasion-principles 外链与 graphviz 工具段，保留 SDO / Match the Form /
  RED-GREEN-REFACTOR 核心，融入 SuperWork 约定）
- v1.2.0 新增：`scripts/validate.ps1`（维护校验：frontmatter、name 一致、
  触发词（manual-trigger 豁免）、description ≤1024、正文 ≤8KB、mojibake、
  引用完整性（references/ 强制、同目录 .md 须存在、项目侧文件白名单）、
  清单双向一致、版本号一致。升级前必跑）
- v1.2.0：元 skill 路由表插入 executing-plans 阶段（阶段 3），阶段重编号；
  豁免规则"纯执行任务"按是否有计划文档分流；writing-plans 的 Execution
  Handoff 与 tdd 的 description 同步更新
- v1.1.0：全部 SKILL.md 的 `description` 重写——按生命周期阶段互斥
  分工 + 中英文触发词 + 负向排除（替代旧版"统一优化触发时机"）
- v1.1.0 新增：`skills/superwork/SKILL.md`（元 skill，入口路由器）、
  `skills/brainstorming/references/`（design-process.md、process-flow.md）、
  `skills/diagnosing-bugs/references/`（feedback-loop-methods.md）
- v1.1.0：`brainstorming`/`writing-plans`/`tdd`/`code-review`/
  `diagnosing-bugs`/`verification-before-completion`（及当时的 grill-with-docs，
  v1.4.0 已并入 grilling）正文中
  的 skill 间转移指令统一改为 `Call the Skill tool with "X"` 显式调用式
- v1.1.0：`code-review/SKILL.md` 修复 UTF-8 mojibake（em-dash/箭头损坏）
  并把评审阈值内联进 description（原引用"routing unconditional
  discipline #3"指向模型不可见的文档）
- v1.1.0：`CLAUDE.md`/`AGENTS.md` 精简为人类参考副本，权威路由迁入元 skill
- 全部 12 个 SKILL.md 的 `description` 字段：统一优化触发时机（负向排除、
  先后顺序），这是 agent 决定加载哪个 skill 的依据
- `brainstorming/SKILL.md`、`visual-companion.md` — `docs/superpowers/specs/` → `docs/superwork/specs/`
  改名 + Windows 说明 + 删除 elements-of-style 引用
- `writing-plans/SKILL.md` — 同上路径改名 + 执行备注（tdd → code-review → 验证）
- `tdd/SKILL.md` — 删除 `/codebase-design` 引用（未收录），改为与用户先确认
  seam 边界；融合 superpowers 的 Iron Law（无失败测试不写生产代码）、
  Watch-It-Fail 纪律与合理化反驳表
- `code-review/SKILL.md` — 删除 `/setup-matt-pocock-skills` 引用（未收录），
  issue tracker 缺失时降级为 commit/路径/specs 兜底；融合 superpowers 的
  Critical/Important/Minor 三级分级与处理顺序
- `diagnosing-bugs/SKILL.md` — 补充 Windows 的 PowerShell HITL 脚本说明；
  融合 superpowers 的"3+ 修复失败 → 质疑架构"机制
- `verification-before-completion/SKILL.md` — 补充与 code-review 的配合说明

本地新增文件（源仓库没有）：`skills/superwork/`（元 skill）、
`skills/brainstorming/references/`、`skills/diagnosing-bugs/references/`、
`AGENTS.md` / `CLAUDE.md`（人类参考副本，v2.0.0 已删除）、`start-server.ps1`、
`stop-server.ps1`、`hitl-loop.ps1`（Windows 原生 PowerShell 版，行为与
`.sh` 等价）。

## 来源与许可

- [obra/superpowers](https://github.com/obra/superpowers)（MIT）
- [mattpocock/skills](https://github.com/mattpocock/skills)（MIT）

本项目为上述技能的子集组合，并对上表列出的文件做了本地定制；从源仓库更新
时手动复制对应文件，保留定制内容。