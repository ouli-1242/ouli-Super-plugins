# SuperOffice

个人通用办公 skill 组合包：处理报告、表格、幻灯片、纪要、表单，一切 Word / Excel / PPT / PDF 的真实办公任务。

## ★ NB-skills（前沿模型合同版）

`NB-skills/` 是本包的**前沿模型专用变体**：同名单独成套（`superoffice` 路由 + 11 个动词 skill），按「能力合同」规范改写——**正文为英文**，过程菜谱替换为结果约束 / 边界约束 / 安全约束 / 验收约束（目标 + 能力边界 + 输入输出契约 + 失败升级 + 成本预算 + 停止条件），每个 skill 附 `contract.yaml`（risk_level、permissions、acceptance_criteria、fallback_variant、review_cycle 等完整元数据；references 为 L2 按需加载）。

- skill 名与触发 description 与 `agents-skills/` 相同（保留中文触发锚点），**同一 harness 二选一安装**，勿与父包同装。
- 结构：`NB-skills/<skill>/SKILL.md + contract.yaml`，无构建脚本、无派生目录——本目录即唯一源。
- 安装：把 `NB-skills/<skill>` junction/复制进目标 harness 的 skills 目录（如 `~/.claude/skills/`）。

## 特性

- **动词层设计**：只在动词层建能力（整理 / 起草 / 修改 / 审阅 / 汇总 / 转换 / 填表 / 验证），动词是有限的，覆盖 100% 的办公请求；专门化不内置，靠 `doc-asset` 从你的真实文档/模板按需积累。
- **完整生命周期**：intake（消化输入）→ draft（起草）→ revise（修改）→ review（审阅）→ verify（验证交付）→ asset（沉淀反哺）。
- **12 个 skill**：元路由器 + 文档生命周期闭环 + 数据与文件 + 环境使能。
- **引擎可选**：document-skills（Anthropic 官方）为主引擎，wps-cli / markitdown-mcp / glmocr-table 按需接入。

## 架构原则：动词层，不是名词层

办公文档的「名词」（开题报告、周报、标书、简历）是无限的，内置多少都会遇到没见过的文体。专门化来自两处：

1. **doc-asset 资产层**：从你的真实文档/模板抽 profile（结构、措辞、字体、版式），越用越懂你的单位；出厂零专门化，用一次积累一点。
2. **按需询问**：没有资产时，起草 skill 直接要模板或样例，不猜。

## 无条件纪律（绑定所有 skill）

1. **数字与引用真实性**——数字只来自用户文件或工具计算；引用只来自真实检索；缺数据标 `[待核实]`。
2. **模板优先**——起草前先找模板/样例，没有就确认结构，绝不凭空发明格式。
3. **证据交付**——没有读回验证（文件能打开、页数对、打印预览正常）不得声称「文件做好了」。
4. **凭证安全**——密钥只进配置文件，不进对话、不进文档。

## 前置依赖

- **document-skills（Anthropic 官方 docx/xlsx/pptx/pdf）是主引擎**：doc-revise / doc-review / form-fill / file-ops 默认走其 Python 路线。安装：Claude Code 插件市场，或从 [anthropics/skills](https://github.com/anthropics/skills) 复制对应目录；未安装时这些环节无法落地产物，`office-mcp-setup` 的诊断会提示。
- **可选引擎**（由 `office-mcp-setup` 按需配置）：wps-cli（WPS 实时控制）、markitdown-mcp（批量解析）、glmocr-table（扫描件 OCR，需智谱 API key）。

## Skill 清单（12 个）

### 入口路由

- `superoffice` — 元 skill。任何办公任务开始时按动词路由，承载无条件纪律与阶段重叠裁决。

### 文档生命周期（写作侧闭环）

- `doc-intake` — 整理输入：录音转写 / 聊天记录 / 邮件串 / 零散笔记 / 长文档 → 纪要、要点、行动项、摘要；逐条可溯源，缺口标 `[待确认]`。
- `doc-draft` — 万能起草：四问框架（给谁看 / 什么目的 / 什么结构 / 素材在哪）+ 七个结构原语；模板优先于想象；长文档先大纲确认。
- `doc-revise` — 修改：润色 / 缩短 / 扩写 / 换风格 / 格式修复五模式，先定不变量再动笔。
- `doc-review` — 审阅批注：四轴（事实 / 逻辑 / 格式 / 风险措辞）评审别人的产物，逐条给位置 + 原文 + 依据；绝不代改。
- `form-fill` — 填表：映射表（字段→值→来源）是核心产物，逐字段读回对照。
- `verify-output` — 产物验证：分类型的读回证据表（重算值、页数、打印预览、字体嵌入）+ 残留缺口清单；交付（邮件 / 打印）需用户确认。

### 数据与文件

- `data-report` — 数据：口径声明先行，工具计算，**总额交叉核对强制**，输出带来源清单。
- `file-ops` — 文件手术：格式转换 / 合并拆分 / OCR 入表 / 批量重命名；先定保真要求再选引擎。

### 资产与环境

- `doc-asset` — 模板资产：从真实文档抽 profile（结构 / 格式参数 / 称谓 / 措辞），落盘 `docs/办公资产/` 并登记索引；资产是默认不是法律。
- `office-mcp-setup` — 环境使能：先诊断是否真需要 MCP，再从审核目录选型、配置、验证连接、登记 `docs/环境清单.md`。
- `wps-cli` — CLI 用法件（收编自上游 [jjchen17/wps-cli](https://github.com/jjchen17/wps-cli)）：COM 驱动真实 WPS——重算公式、刷新字段目录、导出 PDF、批量操作；help-first 原则。

## agent 如何发现并使用

agent 每次会话扫描 skills 目录，按 name + description 触发。`superoffice` 元 skill 在任何办公任务开始时路由到动词 skill；skill 间用 `Call the Skill tool with "X"` 显式转移（如 intake 的产物喂 draft，verify 的缺口退回原动词 skill）。

## 安装

### 推荐：安装器（junction 链接，本包即唯一源）

```powershell
pwsh -File scripts\install-skills.ps1 -Agent claude,dsh -DryRun        # 预览
pwsh -File scripts\install-skills.ps1 -Agent claude,dsh                # 10 个核心
pwsh -File scripts\install-skills.ps1 -Agent claude -IncludeOptional   # 含 office-mcp-setup / wps-cli
```

`bundle.json` 的 `optional` 列出依赖本机环境的两个 skill（`office-mcp-setup`、`wps-cli`），不装不影响其余 10 个。

### 备选：手工复制

把 `agents-skills/` 内容直接复制进各 agent 的 skills 文件夹（会产生分叉副本，建议用安装器）：

| 工具        | skills 目录         |
| ----------- | ------------------- |
| DSH         | `~/.dsh/skills/`    |
| Claude Code | `~/.claude/skills/` |
| Codex CLI   | `~/.codex/skills/`  |
| Cursor      | `~/.cursor/skills/` |

## 多端兼容硬规则

agent 只靠 `name` + `description` 发现 skill：frontmatter 只留这两个字段；description **单行 + 双引号**（未加引号的 `: ` 会让整个 skill 被静默丢弃）、≤ 500 字符、必含 `中文信号：` 锚点；每文件恰好一个 H1；`name` = 目录名且 kebab-case；UTF-8 无 BOM。

## 仓库结构

```
SuperOffice\
├── agents-skills\             # ★ 唯一源：12 个 skill 的长描述（多端通用）
├── zcode-skills\              # 派生：短描述（ZCode 专属）
├── codex-skills\              # 派生：+ agents/openai.yaml（Codex 专属）
├── agents.json                # 各 agent 的 skills 目录登记
├── bundle.json                # 核心 10 个 + 可选 2 个
├── scripts\
│   ├── descriptions.json      # 描述唯一源（长）
│   ├── apply-descriptions.cjs # descriptions.json -> agents-skills/
│   ├── build-agent-folders.cjs# agents-skills/ -> zcode-skills/ + codex-skills/
│   ├── install-skills.ps1     # 安装器（默认 junction 链接）
│   ├── validate-multi.ps1     # 多端合规校验
│   └── normalize-skills.ps1   # frontmatter/H1 规范化（幂等）
└── README.md
```

## 平台依赖与已知边界

- 默认开发机是 Windows + WPS/MS Office；`wps-cli` 依赖 Windows COM 与本机 WPS；markitdown-mcp 需 Python。首次装机先跑 `office-mcp-setup` 的诊断。
- 已知边界：全部 description 按 SDO 原则编写但未做压力测试基线；`wps-cli` 的命令面以本机 `--help` 为准，首次真实运行时应逐工作流验证；IM 通道类 MCP（飞书 / 企微 / 钉钉）已审核未配置，按需启用。

## 许可

本项目为个人自用 skill 组合包，按 MIT 许可分发。