# SuperLite

Ouli 的轻量 skill 组合包，[SuperWork](../SuperWork) 的姊妹篇：**日常非代码工作 +
简单项目**共用。9 个 skill = 8 个领域 skill（完整复制，零蒸馏）+ 1 个 mini
路由元 skill。路由器只做三件事：紧凑路由表（8 行）、三条无条件纪律的会话级
绑定（补上"琐碎任务无 skill 触发时纪律兜底"的缺口）、重叠裁决——不带
Handoffs 网与红旗表（8 个 skill 间转移极少且已内嵌正文）。

固定上下文成本 ~800 tokens，典型会话（含路由器加载）~1500 tokens，约为
SuperWork 的 40%。

## 定位边界

| 场景 | 用哪个 |
|---|---|
| 日常杂项、信息检索、写作、决策分析、简单项目 | **SuperLite** |
| 架构级任务、spec → plan → 执行全链条、需要设计门禁 | SuperWork |

**不可同装**：两个包的 skill 同名（tdd 等），同一环境装两个会静默冲突。
二选一。

## Skill 清单（8 + 1 个）

### 入口路由

- `superlite` — mini 路由元 skill。任何任务开始时触发：路由表分发 + 三条
  无条件纪律的会话级绑定（先测后码 / 证据先于完成 / 合并前评审）。

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
- `handoff` — 会话压缩成交接文档（仅手动 `/handoff`）。

## 与 SuperWork 的差异

- 8 个领域 skill 完整复制自 SuperWork v1.5.0，跨引用已修剪（指向
  brainstorming/executing-plans/writing-plans 等未收录 skill 的转移指令
  改为直接行为指引）
- `verification-before-completion` 增加 Non-Code Deliverables 一节
- `writing` 为 SuperLite 新写（SuperWork 无此 skill）
- 元 skill 是 **mini 路由器**（~2.5KB）：无 Handoffs 网、无红旗表，
  纪律压缩为三条以内嵌 + 会话级绑定双形态存在

## 维护

- 代码纪律 4 项与 SuperWork 同源：SuperWork 侧的方法论改进需手动同步
  到本包（复制 + 修剪跨引用）
- 改动后跑 `powershell -File scripts/validate.ps1`

## 安装

同 SuperWork 的四平台接入方式，把 SuperLite 目录当作插件根即可
（opencode 用 `.opencode/plugin/superlite.js`，Claude Code 用
`.claude-plugin/`，Codex 用 `.codex-plugin/`，Cursor 用 `.cursor-plugin/`）。

## 来源与许可

skill 内容源自 [obra/superpowers](https://github.com/obra/superpowers)（MIT）
与 [mattpocock/skills](https://github.com/mattpocock/skills)（MIT）的 SuperWork
定制版；`writing` 为本项目原创。MIT。
