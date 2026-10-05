# Ouli Super Plugins

个人插件合集，分为 MCP、SKILL、PROMPT 三大板块。

## 目录

### MCP

| 目录 | 包名 | 版本 | 说明 |
|---|---|---|---|
| [`MCP/FastGraph-MCP/`](MCP/FastGraph-MCP/) | [`fastgraph-mcp`](https://github.com/ouli-1242/FastGraph-mcp) | 0.3.0 | 轻量代码智能 MCP：AST + 增量索引 + 调用图 |
| [`MCP/Dhole-MCP/`](MCP/Dhole-MCP/) | [`dhole-mcp`](https://github.com/ouli-1242/dhole-mcp) | 16.2 | 网页抓取/爬取/反爬/PDF/搜索 |
| [`MCP/OpenEye-MCP/`](MCP/OpenEye-MCP/) | [`openeye-mcp`](https://github.com/ouli-1242/openeye-mcp) | 0.3.1 | 为文本模型提供视觉能力：描述/OCR/问答/布局/表格/多图 |

安装：`pip install fastgraph-mcp` / `pip install "dhole-mcp[all]"` / `pip install openeye-mcp`

### SKILL

#### 合集

| 目录 | 说明 |
|---|---|
| [`SKILL/合集/SuperWork/`](SKILL/合集/SuperWork/) | 全量精选 skill 包（17 个 skill）：TDD/debugging/review/verification + spec→plan→execute 全链条 |
| [`SKILL/合集/SuperLite/`](SKILL/合集/SuperLite/) | 日常轻量包（10 个 skill）：写作/总结/查证/决策 + 核心开发 skill |
| [`SKILL/合集/SuperOffice/`](SKILL/合集/SuperOffice/) | 办公产物包（12 个 skill）：起草/修改/审阅/数据汇总/填表 + WPS CLI |

#### 单项

| 目录 | 说明 |
|---|---|
| [`SKILL/单项/chaoxing-tasker/`](SKILL/单项/chaoxing-tasker/) | 超星学习通任务助手（浏览器自动化） |
| [`SKILL/单项/find-extensions/`](SKILL/单项/find-extensions/) | 扩展发现助手（按流行度推荐 skill/mcp/plugin） |
| [`SKILL/单项/prompt-enhance/`](SKILL/单项/prompt-enhance/) | 提示词增强助手（按需重写提示词，补齐任务/上下文/约束/输出格式） |

### PROMPT

#### 全局

| 文件 | 适用客户端 |
|---|---|
| [`PROMPT/全局/CLAUDE.md`](PROMPT/全局/CLAUDE.md) | Claude Code |
| [`PROMPT/全局/AGENTS.md`](PROMPT/全局/AGENTS.md) | OpenCode / Codex 等 AGENTS 规范客户端 |
| [`PROMPT/全局/SOUL.md`](PROMPT/全局/SOUL.md) | 身份与准则（Soul 类客户端） |
| [`PROMPT/全局/Rule.mdc`](PROMPT/全局/Rule.mdc) | Cursor（alwaysApply 全局规则） |

#### 快捷

| 文件 | 用途 |
|---|---|
| [`PROMPT/快捷/debug.md`](PROMPT/快捷/debug.md) | 定位根因、验证假设、最小修复 |
| [`PROMPT/快捷/decide.md`](PROMPT/快捷/decide.md) | 为不确定任务选一条路径 |
| [`PROMPT/快捷/explain.md`](PROMPT/快捷/explain.md) | 按读者水平解释复杂系统 |
| [`PROMPT/快捷/plan.md`](PROMPT/快捷/plan.md) | 把模糊目标拆成可执行步骤并定义成功条件 |
| [`PROMPT/快捷/redteam.md`](PROMPT/快捷/redteam.md) | 对抗性审查自己的方案 |
| [`PROMPT/快捷/review.md`](PROMPT/快捷/review.md) | 审阅交付物，指出优先修正点 |
| [`PROMPT/快捷/summarize.md`](PROMPT/快捷/summarize.md) | 压缩聊天/文档为结构化要点 |

## 说明

- 本仓库为源码备份，MCP Server 开发与发布以各自独立仓库为准。
- MIT License，作者 Ouli。
