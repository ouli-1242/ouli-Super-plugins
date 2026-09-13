# SuperOffice

Ouli 的通用办公 skill 组合包。与 [SuperWork](../SuperWork)（编码过程纪律）互补：SuperWork 管「怎么干活」，SuperOffice 管「干出来的办公产物」——报告、表格、幻灯片、纪要、表单，一切 Word / Excel / PPT / PDF 的真实办公任务。

## 前置依赖

- **document-skills（Anthropic 官方 docx/xlsx/pptx/pdf）是主引擎**：doc-revise / doc-review / form-fill / file-ops 的文件读写默认走它的 Python 路线。安装：Claude Code 插件市场，或从 [anthropics/skills](https://github.com/anthropics/skills) 复制对应目录。未安装时这些环节无法落地产物——`office-mcp-setup` 的诊断会提示。
- **可选引擎**（由 `office-mcp-setup` 按需配置）：wps-cli（WPS 实时控制）、markitdown-mcp（批量解析）、glmocr-table（扫描件 OCR，需智谱 API key）。

## v1.0.1 对抗性审查修正

三个独立审查代理红队后的修复：GLM-OCR 引擎补入 MCP 目录（此前 file-ops 引用了未收录的引擎——违反自家纪律 #1）；validate.ps1 增加两项真检查（Skill-tool 引用目标存在性、markdown 链接解析）；README 声明前置依赖 document-skills；版本残留 v0.1×3、计数 11/12 矛盾、undelared 拼写、双 H1、wps 验证命令（--version→version）、OfficeMCP RunPython 风险注、IM 通道 pending 措辞、doc-asset 幽灵纪律引用、路由表触发词与 description 对齐、PPT 产线断路（doc-draft 明确大纲→pptx/impress 落地）；office-mcp-setup / verify-output / wps-cli / superoffice 四条 description 按 SDO 修剪。

## v1.0.0 全动词发布

12 个 skill 全部就位：元路由器 + 八个文档动词（intake / draft / revise / review / data / file-ops / form-fill / verify）+ doc-asset + 环境使能（office-mcp-setup、wps-cli）。写作侧构成完整生命周期：**intake（消化输入）→ draft（起草）→ revise（修改）→ review（审阅）→ verify（验证交付）→ asset（沉淀反哺）**。

## 架构原则：动词层，不是名词层

办公文档的「名词」（开题报告、周报、标书、简历）是无限的，内置多少都会遇到没见过的文体。SuperOffice 只在**动词层**建能力——整理、起草、修改、审阅、汇总、转换、填表、验证——动词是有限的，覆盖 100% 的办公请求。专门化不内置在合集里，去两个地方：

1. **doc-asset 资产层**：从用户单位的真实文档/模板抽 profile（结构、措辞、字体、版式），越用越懂你的单位。出厂零专门化，用一次积累一点。
2. **按需询问**：没有资产时，起草 skill 直接要模板或样例，不猜。

## 无条件纪律（绑定所有 skill）

1. **数字与引用真实性**——数字只来自用户文件或工具计算；引用只来自真实检索；缺数据标 `[待核实]`。办公场景的头号事故是编造。
2. **模板优先**——起草前先找模板/样例，没有就确认结构，绝不凭空发明一个单位的格式。
3. **证据交付**——没有读回验证（文件能打开、页数对、打印预览正常）不得声称「文件做好了」。
4. **凭证安全**——密钥只进配置文件，不进对话、不进文档。

## Skill 清单（12 个）

### 入口路由

- `superoffice` — 元 skill。任何办公任务开始时按动词路由，承载无条件纪律与阶段重叠裁决。

### 文档生命周期（写作侧闭环）

- `doc-intake` — 整理输入：录音转写/聊天记录/邮件串/零散笔记/长文档 → 纪要、要点、行动项、摘要。逐条可溯源，缺口标 `[待确认]`。
- `doc-draft` — 万能起草：四问框架（给谁看/什么目的/什么结构/素材在哪）+ 七个结构原语；模板优先于想象；长文档先大纲确认。
- `doc-revise` — 修改：润色/缩短/扩写/换风格/格式修复五模式，先定不变量再动笔；格式修复要渲染证据。
- `doc-review` — 审阅批注：四轴（事实/逻辑/格式/风险措辞）评审别人的产物，逐条给位置+原文+依据，输出意见或 Word 原生批注，绝不代改。
- `form-fill` — 填表：映射表（字段→值→来源）是核心产物，逐字段读回对照，响应式表格按评审项逐点对应。
- `verify-output` — 产物验证：分类型的读回证据表（重算值、页数、打印预览、字体嵌入），残留缺口清单，交付环节（邮件/打印需用户确认）。

### 数据与文件

- `data-report` — 数据：口径声明先行，工具计算，**总额交叉核对强制**，输出带来源清单；openpyxl 不算公式的坑由 wps-cli 兜底。
- `file-ops` — 文件手术：格式转换/合并拆分/OCR 入表/批量重命名；先定保真要求再选引擎；OCR 的金额日期上人工确认清单。

### 资产与环境

- `doc-asset` — 模板资产：从真实文档抽 profile（结构/格式参数/称谓/措辞，逐维测量不凭记忆），落盘 `docs/办公资产/` 并登记索引；资产是默认不是法律。
- `office-mcp-setup` — 环境使能：先诊断是否真需要 MCP，再从审核目录选型、配置、验证连接、登记 `docs/环境清单.md`。
- `wps-cli` — CLI 用法件（收编自上游 [jjchen17/wps-cli](https://github.com/jjchen17/wps-cli) 并合并验证纪律）：COM 驱动真实 WPS——重算公式、刷新字段目录、导出 PDF、批量操作；help-first 原则。

## 生态采录与裁决

- [jjchen17/wps-cli](https://github.com/jjchen17/wps-cli)——v1.0.0 起直接收编上游 SKILL.md + 4 个 references，合并 SuperOffice 验证纪律与 MCP 双入口约定
- [OfficeMCP](https://github.com/OfficeMCP)、[markitdown](https://github.com/microsoft/markitdown)——office-mcp-setup 目录收录
- 裁决过但未收录的候选与理由（GongRzhe 系、Composio、lc2panda/wps-skills 等），见 `skills/office-mcp-setup/references/mcp-catalog.md` 的 Rejected 一节
- 架构与写法承接 [SuperWork](../SuperWork)（元路由器/触发面互斥/validate/渐进披露），源自 [obra/superpowers](https://github.com/obra/superpowers) 与 [mattpocock/skills](https://github.com/mattpocock/skills) 的约定

## agent 如何发现并使用

与 SuperWork 同构：agent 每次会话扫描 skills 目录，按 name + description 触发。`superoffice` 元 skill 在任何办公任务开始时路由到动词 skill；skill 间用 `Call the Skill tool with "X"` 显式转移（如 intake 的产物喂 draft，verify 的缺口退回原动词 skill）。

## 安装

把 `skills/` 内容直接复制进各 agent 的 skills 文件夹：

| 工具 | skills 目录 |
| --- | --- |
| ZCode | `~/.zcode/skills/` |
| Claude Code | `~/.claude/skills/` |
| Codex CLI | `~/.codex/skills/` |
| Cursor | `~/.cursor/skills/` |

## 仓库结构

```
SuperOffice\
├── skills\                # 12 个 skill（各 agent 共用）
├── scripts\validate.ps1   # 维护校验（升级前必跑）
└── README.md
```

## 平台依赖与已知边界

默认开发机是 Windows + WPS/MS Office。`wps-cli` 依赖 Windows COM 与本机 WPS；markitdown-mcp 需 Python。首次装机先跑 `office-mcp-setup` 的诊断。

已知边界：全部 description 按 SDO 原则编写但**未做压力测试基线**（writing-skills 的 RED 阶段）；`wps-cli` 的命令面以本机 `--help` 为准，首次真实运行时应逐工作流验证；IM 通道类 MCP（飞书/企微/钉钉）已审核未配置，按需启用。
