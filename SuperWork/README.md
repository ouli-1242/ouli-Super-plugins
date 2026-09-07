# SuperWork

Ouli 的个人 skill 组合包（plugin）。从 [superpowers](https://github.com/obra/superpowers) 与
[matt-skills](https://github.com/mattpocock/skills) 等流行 skill 库精选，共
16 个 skill：11 个精选 + 5 个 SuperWork 自有（路由元 skill、计划执行、skill
编写、分支收尾、冲突解决），基于全局 `AGENTS.md` 的原则组合，按需触发，
不接管对话。

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

已知未修：openai.yaml 覆盖 7/16（Codex UI 元数据，功能可选，待统一补齐）。

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

## Skill 清单（16 个）

### 入口路由

- `superwork` — 元 skill（v1.1.0）。任何对话/任务开始时触发：按生命周期
  阶段把任务路由到具体 skill，装载无条件纪律与红旗清单。是模型侧的
  权威路由表（CLAUDE.md/AGENTS.md 只是人类参考副本）。

### SuperWork 自有（从源库改造）

- `executing-plans`（v1.2.0，superpowers）— 消费已批准的实施计划：逐任务
  tdd 循环、逐项打勾、跨会话从计划复选框与 git log 恢复进度、遇阻即停。
  衔接 writing-plans 与 tdd 之间缺失的编排层。
- `writing-skills`（v1.2.0，superpowers）— 给 skill 做 TDD：description 只写
  触发条件不写流程（SDO 原则）、RED-GREEN-REFACTOR、按失败类型选形式
  （禁令/配方/结构槽/条件句）、堵合理化漏洞。新增或修改任何 skill 前必读。
- `finishing-a-development-branch`（v1.3.0，superpowers）— 工作完成后的
  集成决策：验证全量测试 → 确认 base branch → merge/PR/keep 三选菜单 →
  合并结果重跑测试；绝不自动丢弃，丢弃需逐字确认 "discard"。
- `resolving-merge-conflicts`（v1.3.0，matt）— merge/rebase 冲突五步纪律：
  找双方原始意图、能保则保、绝不发明行为、永不 abort、冲突暴露架构级
  不兼容时停下来找用户。

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
  `tests.md`/`mocking.md` 参考。
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
- **显式**：`handoff` 带 `disable-model-invocation: true`，仅由你主动调用
  （`/handoff`）；`grilling` 的 With-Docs Mode 也仅在明确点名时启用；
  也可直接要求"用 X skill"
- **断链恢复**：skill 之间用 `Call the Skill tool with "X"` 显式转移；会话
  中断后从磁盘产物（spec 状态行、plan 复选框、git log）重新定位阶段

若需要让 agent 理解整套工作流（如"开工前先 grill、完工前先验证"），路由
逻辑已内置于 `skills/superwork/SKILL.md` 元 skill——不要再往 README 或
CLAUDE.md 里堆方法论（模型看不到它们）。

## 安装状态

各工具的安装方法：

| 工具        | 安装位置                                            | 安装命令/操作                                                                                                 |
| ----------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| opencode    | `~/.config/opencode/plugins/SuperWork`              | 复制整个 SuperWork 目录到该位置（连同 `superwork.js` 到 `plugins/` 根），重启                                      |
| Claude Code | `~/.claude/plugins/marketplaces/superwork`          | `claude plugin marketplace add ~/.claude/plugins/marketplaces/superwork` + `claude plugin install superwork@superwork` |
| Codex CLI   | `~/.codex/plugins/superwork/`                       | 复制到该目录，`codex plugin add superwork@personal`                                                           |
| Cursor      | `~/.cursor/plugins/local/superwork/`                | 复制 `.cursor-plugin/` 与 `skills/` 到该目录                                                                  |

### 各工具接入形态

```
SuperWork\
├── .opencode\plugin\superwork.js      # opencode 插件（自动注册 skills 路径）
├── .claude-plugin\plugin.json         # Claude Code 插件清单（skills 数组）
├── .claude-plugin\marketplace.json    # Claude Code 本地 marketplace
├── .codex-plugin\plugin.json          # Codex 插件清单（skills 指向 ./skills）
├── .cursor-plugin\plugin.json         # Cursor 本地插件清单
├── skills\                            # 16 个 skill（四个工具共用）
├── scripts\validate.ps1               # 维护校验（升级前必跑）
└── README.md
```

## 平台依赖

- 默认开发机是 Windows。shell 脚本（`start-server.sh` / `stop-server.sh` /
  `hitl-loop.template.sh`）需要 Git Bash（`bash xxx.sh` 调用），或使用同目录的
  `.ps1` 等价版本。
- Visual Companion 服务器是 Node 脚本（`server.cjs`），需本机有 Node。

## 已定制的文件

以下文件相对源仓库有本地定制，从源仓库更新时需要人工合并（不要直接覆盖）：

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
- `brainstorming/SKILL.md`、`spec-document-reviewer-prompt.md`、
  `visual-companion.md` — `docs/superpowers/specs/` → `docs/superwork/specs/`
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
`AGENTS.md` / `CLAUDE.md`（人类参考副本，内容一致）、`start-server.ps1`、
`stop-server.ps1`、`hitl-loop.ps1`（Windows 原生 PowerShell 版，行为与
`.sh` 等价）。

## 来源与许可

- [obra/superpowers](https://github.com/obra/superpowers)（MIT）
- [mattpocock/skills](https://github.com/mattpocock/skills)（MIT）

本项目为上述技能的子集组合，并对上表列出的文件做了本地定制；从源仓库更新
时手动复制对应文件，保留定制内容。