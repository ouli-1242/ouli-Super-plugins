# SuperLite

Ouli 的轻量 skill 组合包，[SuperWork](../SuperWork) 的姊妹篇：**日常非代码工作 +
简单项目**共用。10 个 skill = 9 个领域 skill（完整复制，零蒸馏）+ 1 个 mini
路由元 skill。路由器只做三件事：紧凑路由表（9 行）、五条无条件纪律的会话级
绑定（补上"琐碎任务无 skill 触发时纪律兜底"的缺口）、重叠裁决——不带
Handoffs 网与红旗表（9 个 skill 间转移极少且已内嵌正文）。

固定上下文成本 ~1000 tokens，典型会话（含路由器加载）~1800 tokens，约为
SuperWork 的 45%。

## v2.2.1 handoff 开启自动调用

`handoff` 移除 `disable-model-invocation`，description 重写为触发条件式：用户要求交接/压缩会话，或上下文将满且工作未完时自触发；普通任务收尾不触发。新增分档压缩线（≤256k 窗口 70/90、≤500k 60/75、1M 40/60）：start 线写好交接文档，hard 线写完并提示用户压缩——真实压缩由 harness 执行（auto-compact / /compact / 新会话），交接文档保证无损。

## v2.2.0 日常化（更轻量灵活）

- **superlite 路由表日常优先**：写作/查证/决策三行提到最前并扩日常触发词；description 定位改为"daily use and simple projects"。
- **纪律 #4 改条件式**：有 `docs/` 脊柱的项目才落盘登记；日常一次性产物（总结、草稿邮件、小对比）留聊天，除非用户要求保存——不为临时输出造仪式。
- **writing 吸收「整理材料」模式**（lite 版 doc-intake，SuperWork v1.4.0 薄壳合并的同一手法）：总结/纪要/整理聊天记录由 writing 承接——溯源抽取、逐字引述、`[待确认]`、行动项必有负责人。**不加新 skill，保持 9+1**。
- **research/grilling 触发词扩到日常**（查攻略/价格对比；该选哪个/帮我参谋）；research 产出分流：项目落盘、日常进聊天。
- **豁免表扩日常**：快速总结、一句话翻译、"这俩有啥区别"——直接答，不路由不仪式。

## v2.1.0 同步 SuperWork

把 SuperWork v2.1.0 的内容增量移植过来（lite 适配层保留：套件名、"缺位 skill 直接问用户"的兜底措辞不动）：

- **tdd**：新增 `deep-modules.md`（深模块词汇表：module/interface/seam/depth/leverage/locality，SuperWork v2.1.0 吸收自 mattpocock codebase-design）+ Seams 小节挂钩。
- **verification-before-completion**：红队自查从单段扩为三问（怎么错 / 没验证什么 / 真实使用会坏什么），诚实边界落点保持 lite 约定（交付物/交接，无 日志/）；`Non-Code Deliverables` 一节保留（lite 的泛化定位）。
- **doc-index**：补实验记录六段结构（`docs/实验/`：假设/设置/指标/数据/结论/诚实边界；负结果照实记、合成数据不得宣称真实准确率、引用前重跑）。
- **superlite 元 skill**：纪律 #5 加 偏离声明（实际做了 vs 要求/计划）。
- **不移植**（依赖 SuperWork 专属 skill 或属于其领地）：grilling 的 With-Docs Mode（需 domain-modeling）、code-review 的 finishing-a-development-branch 排除句、tdd description 的 brainstorming/executing-plans 排除句（SuperLite 无这些 skill，保持"直接问用户"兜底）、writing-skills 的 Retro Mode（无此 skill）。
- 定位边界不变：SuperLite 保持 9 + 1 结构，不扩容。

## v2.0.0 同步 SuperWork

按维护契约把 SuperWork v2.0.0 的中文文档约定同步过来（lite 裁剪版）：

- 路径迁移：handoff→`docs/交接/`、research→`技术依据.md`/`docs/设计/`、code-review 落盘 `docs/审查/`；tdd/diagnosing-bugs 的 `CONTEXT.md`+`ADR`→`技术依据.md`+`决策记录.md`。
- 新增 `doc-index` skill（文档导航 spine）+ superlite 纪律 #4 落盘登记 / #5 诚实边界+红队（lite 版：诚实边界进交接/交付物，无独立 日志/ 因无 executing-plans）。
- 不加 `experiment` skill（实验属 SuperWork 领地，保持 lite）。
- 修 `validate.ps1` 的清单检查为可选（原会因清单缺失而 FAIL）。

## 定位边界

| 场景 | 用哪个 |
|---|---|
| 日常杂项、信息检索、写作、决策分析、简单项目 | **SuperLite** |
| 架构级任务、spec → plan → 执行全链条、需要设计门禁 | SuperWork |

**不可同装**：两个包的 skill 同名（tdd 等），同一环境装两个会静默冲突。
二选一。

## Skill 清单（9 + 1 个）

### 入口路由

- `superlite` — mini 路由元 skill。任何任务开始时触发：路由表分发 + 五条
  无条件纪律的会话级绑定（先测后码 / 证据先于完成 / 合并前评审 / 落盘登记 /
  诚实边界+红队）。

### 代码纪律（简单项目用）

- `tdd` — 红→绿循环。铁律：没有失败测试不写生产代码；Watch-It-Fail；只在
  预先确认的 seam 上测试。
- `diagnosing-bugs` — 硬 bug 六阶段：先建能变红的反馈环，禁止臆测修复；
  3 次修复失败 = 架构问题。
- `code-review` — Standards + Spec 双轴评审，阈值内联（核心模块 / diff ≥ 15
  文件 / 新契约时合并前必做）。
- `verification-before-completion` — 证据先于声称。**已泛化**：适用于任何
  交付物（代码、文档、分析、报告），不只代码。

### 通用工作（日常用）

- `writing`（SuperLite 专属）— 任何书面交付物：文档、计划、报告、邮件、
  配置。目的与读者先行，非琐碎件先大纲后成文，写完对照目的自审。
- `research` — 委托后台代理查一手来源，产出带引用的 Markdown。防编造事实。
- `grilling` — 决策压力测试：决策树 + 轮次 + 前沿的追问，直至无默默假设。
- `handoff` — 会话压缩成交接文档，落 `docs/交接/`（v2.2.1 起允许自动调用：会话将满且工作未完时自触发）。
- `doc-index`（v2.0.0 同步）— 文档导航协议：`docs/文档导航.md` 是唯一索引
  门面 + 路径约定声明。产出 skill 落盘后在导航登记一行，无登记不算交付。

## 与 SuperWork 的差异

- 9 个领域 skill 复制自 SuperWork（8 个源自 v1.5.0 + `doc-index` 随 v2.0.0
  同步加入），跨引用已修剪（指向 brainstorming/executing-plans/writing-plans
  等未收录 skill 的转移指令改为直接行为指引）
- `verification-before-completion` 增加 Non-Code Deliverables 一节
- `writing` 为 SuperLite 新写（SuperWork 无此 skill）
- 元 skill 是 **mini 路由器**（~3KB）：无 Handoffs 网、无红旗表，
  纪律五条以内嵌 + 会话级绑定双形态存在

## 维护

- 代码纪律 4 项与 SuperWork 同源：SuperWork 侧的方法论改进需手动同步
  到本包（复制 + 修剪跨引用）
- 改动后跑 `powershell -File scripts/validate.ps1`

## 安装

**把 `skills/` 内容直接复制进各 agent 自己的 skills 文件夹**——agent 自动扫描 SKILL.md，无需平台清单（SuperLite 不带任何 manifest）。

| 工具        | skills 目录                     | 操作                          |
| ----------- | ------------------------------- | ----------------------------- |
| DSH         | `~/.dsh/skills/`                | 复制 `skills/*` 子目录到此处  |
| Claude Code | `~/.claude/skills/`             | 同上                          |
| Codex CLI   | `~/.codex/skills/`              | 同上                          |
| Cursor      | `~/.cursor/skills/`             | 同上                          |
| opencode    | 见 opencode 自身的 skills 路径  | 同上                          |

> v2.0.0 起 SuperLite 不再带平台清单；若要恢复"装插件"分发，重新加对应 `plugin.json` 即可。

## 来源与许可

skill 内容源自 [obra/superpowers](https://github.com/obra/superpowers)（MIT）
与 [mattpocock/skills](https://github.com/mattpocock/skills)（MIT）的 SuperWork
定制版；`writing` 为本项目原创。MIT。
