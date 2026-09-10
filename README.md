# Ouli Super Plugins

Ouli 的个人插件合集（源码托管 / 备份仓库），包含 Claude Code skill 插件、MCP Server 与 Agent Skill。

## 插件列表

### Skill 插件（Claude Code Plugin）

| 子目录 | 插件名 | 版本 | 说明 |
|---|---|---|---|
| [`SuperWork/`](SuperWork/) | `superwork` | 1.5.0 | 全量精选 skill 组合包：TDD、debugging、code review、grilling、domain-modeling、verification 等 16 个 skill |
| [`SuperLite/`](SuperLite/) | `superlite` | 1.0.0 | 轻量 skill 包：TDD、debugging、review、verification + 通用 writing、research、grilling、handoff |

### MCP Server（Python 包，同步自各自独立仓库）

| 子目录 | 包名 | 版本 | 独立仓库 | 说明 |
|---|---|---|---|---|
| [`FastGraph-MCP/`](FastGraph-MCP/) | `fastgraph-mcp` | 0.1.0 | [ouli-1242/FastGraph-mcp](https://github.com/ouli-1242/FastGraph-mcp) | 轻量实时代码智能 MCP：AST + 增量索引 + 代码图，无 embedding、低内存、低 context；提供项目级检索、调用图与影响分析 |
| [`Hound-MCP/`](Hound-MCP/) | `hound-mcp` | 11.1.8 | [ouli-1242/hound-mcp](https://github.com/ouli-1242/hound-mcp) | 让 AI 代理访问互联网：抓取、爬取、反爬绕过、PDF（含扫描件）解析、无密钥网页搜索，共 8 个工具 |
| [`DeepEye-MCP/`](DeepEye-MCP/) | `deepeye-mcp` | 0.2.0 | [ouli-1242/deepeye-mcp](https://github.com/ouli-1242/deepeye-mcp) | 为纯文本大模型提供视觉能力：图像描述 / OCR / 视觉问答 / 布局分析 |

### Agent Skill

| 子目录 | 名称 | 说明 |
|---|---|---|
| [`chaoxing-tasker/`](chaoxing-tasker/) | `chaoxing-tasker` | 超星学习通任务助手：通过浏览器自动化完成作业、考试、签到、课点/视频、讨论任务，并汇报待办清单与完成结果 |

## 说明

- **Skill 插件**：`SuperWork/`、`SuperLite/` 各是完整独立的 Claude Code 插件（含 `.claude-plugin/` 与 `marketplace.json`，`source: "./"`）。如需直接安装，请分别单独建仓后再执行 `claude plugin install <repo-url>`。
- **MCP Server**：`FastGraph-MCP/`、`Hound-MCP/`、`DeepEye-MCP/` 为 Python 包源码，本仓库为其镜像收录，开发与发布以各自独立仓库为准。安装方式见各子目录 README（`pip install .` 或 `pip install -e .`）。
- **Agent Skill**：`chaoxing-tasker/` 为单个 `SKILL.md`，放入对应客户端的 skills 目录即可使用。
- 各子目录保留其原有的 README、依赖声明、忽略规则与第三方许可说明（如 `Hound-MCP/LICENSE`、`Hound-MCP/NOTICE.ddgs.txt`），使用前请一并阅读。
- MIT License，作者 Ouli。
