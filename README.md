# Ouli Super Plugins

个人插件合集，包含 Agent Skill 插件、MCP Server、Agent Skill 与提示词配置。

## 目录

### Skill 插件

| 目录 | 说明 |
|---|---|
| `SuperWork/` | 全量精选 skill 包（17 个 skill）：TDD/debugging/review/verification + spec→plan→execute 全链条 |
| `SuperLite/` | 日常轻量包（10 个 skill）：写作/总结/查证/决策 + 核心开发 skill |
| `SuperOffice/` | 办公产物包（12 个 skill）：起草/修改/审阅/数据汇总/填表 + WPS CLI |

### MCP Server（Python 包）

| 目录 | 包名 | 版本 | 说明 |
|---|---|---|---|
| `FastGraph-MCP/` | `fastgraph-mcp` | 0.2.0 | 轻量代码智能 MCP：AST + 增量索引 + 调用图 |
| `Dhole-MCP/` | `dhole-mcp` | 14.1 | 网页抓取/爬取/反爬/PDF/搜索，8 个工具 |
| `DeepEye-MCP/` | `deepeye-mcp` | 0.2.0 | 为文本模型提供视觉能力：描述/OCR/问答/布局 |

安装：`pip install fastgraph-mcp` / `pip install "dhole-mcp[all]"` 

### Agent Skill

| 目录 | 说明 |
|---|---|
| `chaoxing-tasker/` | 超星学习通任务助手（浏览器自动化） |
| `find-extensions/` | 扩展发现助手（按流行度推荐 skill/mcp/plugin） |

### 提示词配置

| 文件 | 适用客户端 |
|---|---|
| `CLAUDE.md` | Claude Code |
| `codex-AGENTS.md` | Codex |
| `dsh-AGENTS.md` | DSH |
| `opencode-AGENTS.md` | OpenCode |
| `hermesSOUL.md` | Hermes（身份与准则） |
| `hermesWORK.md` | Hermes（操作流程） |
| `RULE.md` / `Rule.mdc` | 通用 / Cursor |
| `1bs.md` | 第一性原理 + 对抗性审阅 |
| `2unc.md` | 不确定性枚举与验证 |

## 说明

- 本仓库为源码备份，MCP Server 开发与发布以各自独立仓库为准。
- MIT License，作者 Ouli。
