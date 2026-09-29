<div align="center">

# FastGraph-MCP

**轻量级代码智能 MCP：AST + 增量索引 + 调用图。无 embedding、无图数据库、无 LSP，低内存、低 context。**

<a href="https://pypi.org/project/fastgraph-mcp/"><img src="https://img.shields.io/pypi/v/fastgraph-mcp.svg" alt="PyPI version"></a>
<img src="https://img.shields.io/pypi/pyversions/fastgraph-mcp.svg" alt="Python 3.11+">
<a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
<img src="https://img.shields.io/badge/transport-stdio-blueviolet.svg" alt="MCP stdio transport">

</div>

定位是**代码导航层**：代码在哪、谁调用谁、改了影响谁、刚改了什么——补 grep（分不清定义与调用点）和 LSP（无全局调用图/影响分析）的短板。读改代码、重构、diagnostics 交给编辑器/LSP 工具。

## 特性

- **快**：实测冷索引 preact 242 文件 2.6s / vue core 538 文件 6.6s / element-plus 1,979 文件（含 829 个 `.vue`）20.7s；查询本身 0.1~2ms。每次调用另付一次目录扫描（538 文件 ~19ms，2k 文件 ~99ms，17.7k 文件 ~0.8s），改动一个文件后的刷新 140~380ms，取决于该文件自身的调用边密度
- **规模上限**：冷索引的主要成本在调用边解析，因此随**边数**而非文件数增长——kubernetes 的 `staging/src/k8s.io/api`（496 个生成代码密集的 Go 文件、11.8 万条调用边）要 23s，而文件数更多的普通仓库快得多。sentry（17,703 个可索引文件 = 8.1k Python + 8.6k TSX，66 万条调用边）首次索引是几十分钟量级，规划者请把它当"单包/单服务"工具用。**大仓库首次调用不再阻塞**：单次调用最多索引 20 秒就先用已建好的部分回答，并在 `refresh.pending_files` + `hint` 里明说结果不完整（此时"查不到"= 还不知道，不是不存在）；后续调用自动续建，想一次建完就调 `reindex()`（预算可用环境变量 `FASTGRAPH_INDEX_BUDGET_S` 调大或调小）。实测 4,788 文件的包：7 次调用、最长一次 41s 建完，与一次阻塞 157s 建出来的索引**逐条指纹完全相同**；收尾那次唯一没被预算切的阶段是全量依赖边重建，它在 17,700 文件 / 14.7 万 import 上实测 9.7s。写盘按 128 文件一批提交，中断、超时或 IDE 重启都不丢已完成的部分
- **轻**：无 embedding 模型、无图数据库、无 LSP；索引一个中型仓库额外占用约 10MB（进程基础占用 ~56MB，其中绝大部分是 MCP SDK 与 pydantic 的导入开销，非本项目可控），万级文件仓库约 ~80MB / 索引文件 ~316MB
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

> `-P` 不是可省的（Python ≥ 3.11）：`python -m x` 会把进程 cwd 排到 `sys.path` 最前面，而桌面客户端就是以你的项目目录为 cwd 启动 MCP 进程的。项目里只要有与标准库同名的顶层包/模块（`types/`、`json/`、`logging/`……），解释器在加载 `runpy` 阶段就崩了，服务器在 MCP 握手之前退出（sentry 的 `src/sentry/types/` 就会触发）。`-P` 只关掉「不把 cwd/脚本目录加进 sys.path」这一件事。`python -I -m fastgraph` 或直接调用装好的 `fastgraph` 命令同样有效，但 `-I` 是隔离模式，还会忽略 `PYTHONPATH` 与用户 site-packages——用 `pip install --user`／靠 PYTHONPATH 跑源码开发版的人会因此找不到包。

Claude Code（`~/.claude.json` 或项目 `.mcp.json`）：

```json
{
  "mcpServers": {
    "fastgraph": {
      "command": "python",
      "args": ["-P", "-m", "fastgraph"]
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
      "command": ["python", "-P", "-m", "fastgraph"]
    }
  }
}
```

**2. 使用**：打开任意项目，调用任意工具（推荐先 `project_overview`）即自动建索引，之后增量更新。

桌面客户端（Claude Desktop、Qoder 等，以固定 cwd 启动 MCP 进程——Qoder 实测以用户主目录为 cwd）先调一次 `activate_project(root="/abs/path")` 激活项目；换项目再调一次。要固定分析某个目录，启动参数加 `--root D:/work/my-project`（或环境变量 `FASTGRAPH_ROOT`）。

> Windows 注意：`python` 不要用微软商店别名（用 `where python` 确认）；JSON 路径推荐写正斜杠 `D:/work/project`。

**3. 索引存在哪**：`<项目>/.fastgraph/index.sqlite`（SQLite WAL，纯本地，删掉即重建）。实测规模：17,703 文件的仓库索引 316MB。该目录自带 `.gitignore`（内容为 `*`），不会出现在你项目的 `git status` 里，也不需要改你自己的 `.gitignore`。要额外排除目录/文件，编辑 `.fastgraph/.fastgraphignore`（首次索引自动生成带注释的模板，默认已排除 `.venv`/`node_modules`/`dist`/密钥文件等）；被排除的文件会从索引里删除。首次索引分批落盘（每 256 个文件提交一次），中断或 IDE 重启后续建而不从头开始。

## 让模型主动使用

MCP 工具对模型是可选的——不引导，模型默认用自己顺手的 grep/read。最有效的一步：把下面这段粘贴进项目的 `CLAUDE.md` / `AGENTS.md`（服务端 instructions 与工具描述已内置同样的决策表）：

```md
## 代码导航：用 FastGraph MCP，不要先用 grep
- 找代码在哪 / 找用法：先 code_search
- 打开不熟悉的文件前：先 file_symbols(path) 看结构
- 回答"谁调用了 X"：用 find_callers（结果为空但带 unresolved_incoming>0 表示有调用者未解析；若两者都没有而带 imported_by，说明它是被读取的枚举/常量，都不能当无人使用）
- 改函数/类之前：先 impact_analysis(symbol) 看影响面
- 改 import 前：file_deps(path)；查架构：module_cycles()
- 只读一个符号：symbol_body(name)；整文件才用 read_file
- 改完代码：changed_context() 复查波及范围
- 进陌生仓库：先 project_overview()
```

## 工具（14 个）

| 任务 | 工具 |
| --- | --- |
| 桌面端激活项目 | `activate_project(root)` |
| 大仓库不想等（`full=true` 则清掉重建） | `reindex(full?)` |
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

所有工具都接受可选 `root=` 参数做单次跨项目查询（按 LRU 缓存 8 个项目）。符号名可写 `top`、`Class.method`、`Class/method`，Rust/C++ 的 `Class::method` 与带泛型的 `Controller<'_>::print_file` 也接受（按去泛型后的名字回退匹配）。输出行号全部 1-based。另有 resource `fastgraph://overview` 与 prompt `fastgraph-workflow` 可选配。

## 支持语言

Python、TypeScript/TSX、JavaScript、Vue、Svelte、Go、Rust、Java、C/C++（`.wxml` 模板引用亦支持）。

依赖图按各语言 import 写法解析，含 tsconfig paths / vite alias / uni-app `@` 别名、Go `go.mod` 模块根、Rust crate 根、目录入口（`index.*` / `__init__.*`）。

## 调用图的边界（重要）

真实仓库上约 9%~40% 的调用边能唯一连到符号（10 个公开仓库实测：C++/TS 38%、Rust/Python 28~29%、JS 23~31%、Go 18~24%、Java 9%——继承与框架派发最多）；仓库越大、内部依赖越多，这个比例越高（sentry 17,703 文件的混合 Python/TSX 仓库：66 万条调用边中 25 万条连上 = 37.6%）。其余要么指向外部库，要么接收者类型无法静态确定——后者**不连边、不猜**，而是计数报出：

- `find_callers` 每条结果带 `via`：`resolved`（确证的调用边）或 `text`（同名文本折叠的猜测）
- `find_callees` 每条结果带 `evidence`：`same_file` / `imported`（有文件级证据）或 `name_only`（仅同名匹配，当猜测看）
- 出现 `unresolved_incoming` / `unresolved_outgoing` 字段时，**空列表 ≠ 没有调用者**，按"未知"处理，不能据此判定可删；若某个符号既无调用边也无未解析边，`find_callers` 会改报 `imported_by`（它可能是被读取的枚举/常量/类型，而非无人使用）
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
