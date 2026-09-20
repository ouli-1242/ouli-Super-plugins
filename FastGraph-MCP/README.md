# FastGraph-MCP

轻量级代码智能 [MCP](https://modelcontextprotocol.io) 服务器：AST + 增量索引 + 调用图。无 embedding、无图数据库、无 LSP，低内存、低 context。

定位是**代码导航层**：代码在哪、谁调用谁、改了影响谁、刚改了什么——补 grep（分不清定义与调用点）和 LSP（无全局调用图/影响分析）的短板。读改代码、重构、diagnostics 交给编辑器/LSP 工具。

## 特性

- **快**：首次索引中型项目数秒~十几秒；之后增量更新只重解析改动文件，典型查询 <100ms
- **轻**：无 embedding 模型、无图数据库、无 LSP；常驻内存 <50MB
- **省 context**：所有工具只返回 `file / symbol / line / relation`，不返回文件正文（仅 `read_file` / `symbol_body` 例外，且有硬上限）
- **诚实**：调用图是名字解析的近似而非类型推断；解析不了的边显式报 `unresolved_incoming`/`unresolved_outgoing`，绝不猜、绝不把"空列表"伪装成"没人用"

## 安装

```bash
pip install fastgraph-mcp           # 日常使用
pip install "fastgraph-mcp[dev]"    # 开发者
```

从源码安装：

```bash
git clone https://github.com/ouli-1242/FastGraph-mcp.git
cd FastGraph-mcp
python -m pip install .              # 日常使用（装完源码目录可删）
python -m pip install -e ".[dev]"    # 开发者（改动即时生效）
```

要求 Python ≥ 3.11。

## 快速开始

**1. 配置 MCP**（零配置：不写 `--root`、不写 `cwd`，打开哪个项目就索引哪个项目）

Claude Code（`~/.claude.json` 或项目 `.mcp.json`）：

```json
{
  "mcpServers": {
    "fastgraph": {
      "command": "python",
      "args": ["-m", "fastgraph"]
    }
  }
}
```

OpenCode（`opencode.json`）：

```json
{
  "mcp": {
    "fastgraph": {
      "type": "local",
      "enabled": true,
      "command": ["python", "-m", "fastgraph"]
    }
  }
}
```

**2. 使用**：打开任意项目，调用任意工具（推荐先 `project_overview`）即自动建索引，之后增量更新。

桌面客户端（Claude Desktop 等，以固定 cwd 启动 MCP 进程）先调一次 `activate_project(root="/abs/path")` 激活项目；换项目再调一次。要固定分析某个目录，启动参数加 `--root D:/work/my-project`（或环境变量 `FASTGRAPH_ROOT`）。

> Windows 注意：`python` 不要用微软商店别名（用 `where python` 确认）；JSON 路径推荐写正斜杠 `D:/work/project`。

## 让模型主动使用

MCP 工具对模型是可选的——不引导，模型默认用自己顺手的 grep/read。最有效的一步：把下面这段粘贴进项目的 `CLAUDE.md` / `AGENTS.md`（服务端 instructions 与工具描述已内置同样的决策表）：

```md
## 代码导航：用 FastGraph MCP，不要先用 grep
- 找代码在哪 / 找用法：先 code_search
- 打开不熟悉的文件前：先 file_symbols(path) 看结构
- 回答"谁调用了 X"：用 find_callers（结果为空但带 unresolved_incoming>0 表示有调用者未解析，不能当无人使用）
- 改函数/类之前：先 impact_analysis(symbol) 看影响面
- 改 import 前：file_deps(path)；查架构：module_cycles()
- 只读一个符号：symbol_body(name)；整文件才用 read_file
- 改完代码：changed_context() 复查波及范围
- 进陌生仓库：先 project_overview()
```

## 工具（13 个）

| 任务 | 工具 |
| --- | --- |
| 桌面端激活项目 | `activate_project(root)` |
| 陌生仓库看全局 | `project_overview()` |
| 按关键词/自然语言定位代码 | `code_search(query, kind?, limit?)` |
| 一个符号是什么 | `symbol_info(symbol)` |
| 文件结构（先看结构再读正文） | `file_symbols(path)` |
| 读文件 / 行区间 | `read_file(path, start_line?, end_line?)` |
| 只读一个符号的源码 | `symbol_body(symbol)` |
| 谁调用它（`depth≥2` 传递） | `find_callers(symbol, depth?)` |
| 它调用谁 | `find_callees(symbol, depth?)` |
| 改动前看影响面 | `impact_analysis(symbol)` |
| import 了什么 / 被谁 import | `file_deps(path)` |
| 文件间 import 环（架构健康） | `module_cycles()` |
| 改完看变更波及（支持 `base="main"` 对比整个分支） | `changed_context(base?)` |

推荐节奏：`project_overview` → `code_search` 定位 → `file_symbols`/`symbol_body` 读 → `impact_analysis` 改前 → `changed_context` 改后。

所有工具都接受可选 `root=` 参数做单次跨项目查询（按 LRU 缓存 8 个项目）。输出行号全部 1-based。另有 resource `fastgraph://overview` 与 prompt `fastgraph-workflow` 可选配。

## 支持语言

Python、TypeScript/TSX、JavaScript、Vue、Svelte、Go、Rust、Java、C/C++（`.wxml` 模板引用亦支持）。

依赖图按各语言 import 写法解析，含 tsconfig paths / vite alias / uni-app `@` 别名、Go `go.mod` 模块根、Rust crate 根、目录入口（`index.*` / `__init__.*`）。

## 调用图的边界（重要）

真实仓库上约 21%~40% 的调用边能唯一连到符号，其余要么指向外部库，要么接收者类型无法静态确定——后者**不连边、不猜**，而是计数报出：

- `find_callers` 每条结果带 `via`：`resolved`（确证的调用边）或 `text`（同名文本折叠的猜测）
- 出现 `unresolved_incoming` / `unresolved_outgoing` 字段时，**空列表 ≠ 没有调用者**，按"未知"处理，不能据此判定可删
- `self.x()`、接口实现、回调注册、动态派发不会连边——宁可漏，不可错

## 开发

```bash
python -m pytest tests/          # 测试
python bench/bench.py <项目路径>  # 性能基准（冷索引/增量/查询时延）
```

## 路线图

- [x] Phase 1-3.5：MCP Server、调用图、影响分析、git 变更感知、多语言依赖解析
- [ ] Phase 4：可选 BM25/embedding 语义搜索
- [ ] Phase 5：多项目 workspace

## License

[MIT](LICENSE)
