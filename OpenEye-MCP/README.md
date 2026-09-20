<div align="center">

# OpenEye

**为纯文本大模型提供视觉能力的 MCP Server —— 让不会看图的模型也能读图、识字、解表格、复刻 UI。**
  <a href="https://pypi.org/project/openeye-mcp/"><img src="https://img.shields.io/pypi/v/openeye-mcp.svg" alt="PyPI version"></a>
  <img src="https://img.shields.io/pypi/pyversions/openeye-mcp.svg" alt="Python 3.11+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/transport-stdio-blueviolet.svg" alt="MCP stdio transport">

</div>

OpenEye 是一个 **stdio 类型的 MCP Server**：它把视觉模型（GPT / Claude / Gemini / 通义 / 智谱 / 本地 Ollama 等）包装成 6 个 MCP 工具，接到 Claude Code、Cursor、Cline 等 coding agent 上，原本只能处理文本的模型就获得了识图能力——分析 UI 截图、照抄报错文字、读表格、按图还原前端。

## 目录

- [特性](#特性)
- [环境要求](#环境要求)
- [安装](#安装)
- [快速开始](#快速开始)
- [工具一览](#工具一览)
- [配置](#配置)
- [视觉后端与协议取舍](#视觉后端与协议取舍)
- [客户端集成](#客户端集成)
- [安全设计](#安全设计)
- [故障排查](#故障排查)
- [开发](#开发)
- [致谢](#致谢)
- [License](#license)

## 特性

- **6 个识图工具**：图像描述、OCR 取字、视觉问答、UI 布局结构化分析、表格转 Markdown、多图批量分析 + 跨图汇总。
- **5 类视觉后端**：OpenAI 兼容协议（默认）/ Anthropic Messages / OpenAI Responses / Gemini generateContent / Gemini Interactions，一个 `VISION_PROVIDER` 切换。
- **任意 OpenAI 兼容厂商**：改 `OPENAI_BASE_URL` 就换厂商——通义、智谱、阶跃星辰、Kimi、DeepSeek、本地 Ollama / vLLM 都能直接接。
- **三种图片来源**：本地路径、`http(s)` 公网 URL、`data:image/...;base64,` data URI，同一入口自动识别。
- **结构化输出**：布局与表格走 JSON 模式，端点不支持 `response_format` 时自动降级并用容错解析兜底。
- **省 token 与提速**：图片等比压缩（JPEG 化）、结果 LRU+TTL 缓存、已解析图片缓存，重复问同一张图不再重复上传。
- **进度上报**：支持 MCP `progressToken` 的客户端可以看到「正在请求视觉后端（第 N 次）」这类实时进度。
- **默认安全的取图链路**：SSRF 防护 + DNS 解析结果固定、逐跳重定向校验、图片大小上限、凭据脱敏、可选本地目录白名单、单次调用总时间预算。
- **零 SDK 依赖**：只用 `httpx` 手写协议，不装各厂商 SDK；纯文本模型也能吃到多模态能力。

## 环境要求

- Python **3.11+**（CI 覆盖 3.11 / 3.12 / 3.13 / 3.14，Windows / macOS / Linux 通用）
- 一个支持**图片输入**的视觉模型 API Key（纯文本模型无法看图）
- 任一支持 MCP 的客户端（Claude Code、Cursor、Cline、Windsurf、Codex CLI、Zed、Continue、Roo Code、opencode 等）

## 安装

```bash
pip install openeye-mcp
```

装好后 `openeye` 命令即进入 PATH：

```bash
openeye        # 打印启动日志后等待 stdio 连接，Ctrl+C 退出
```

**在虚拟环境中安装**（推荐；客户端配置里用该环境的绝对路径）：

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install openeye-mcp
```

**从源码安装**（开发与贡献）：

```bash
git clone https://github.com/ouli-1242/openeye-mcp.git
cd openeye-mcp
pip install -e ".[dev]"          # editable：改源码即时生效
```

卸载：

```bash
pip uninstall openeye-mcp
```

## 快速开始

### 1. 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env`，填你要用的后端（下面这组是默认的 `openai` 后端）：

```dotenv
VISION_PROVIDER=openai
OPENAI_API_KEY=sk-your-real-key-here
OPENAI_MODEL=qwen-vl-max
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

### 2. 接入客户端

以 Claude Code 为例（一行命令）：

```bash
claude mcp add openeye --env VISION_PROVIDER=openai \
  --env OPENAI_API_KEY=sk-your-key \
  --env OPENAI_MODEL=qwen-vl-max \
  --env OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1 \
  -- openeye
```

或在项目根目录放一个 `.mcp.json`：

```json
{
  "mcpServers": {
    "openeye": {
      "command": "openeye",
      "env": {
        "VISION_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-your-key",
        "OPENAI_MODEL": "qwen-vl-max",
        "OPENAI_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1"
      }
    }
  }
}
```

### 3. 验证

重启客户端，`/mcp` 面板中 `openeye` 应显示 connected；然后直接说「用 OpenEye 描述这张截图：/path/to/shot.png」。

其他客户端（Cursor / Cline / Windsurf / Codex / Zed / Continue / Roo Code / opencode）的配置文件位置与字段差异，见 [编码工具接入指南](docs/编码工具接入指南.md)。

## 工具一览

所有工具的图片来源参数都支持三种形式：本地绝对路径、`http(s)` URL、`data:image/...;base64,...` data URI。六个工具均声明为只读（`readOnlyHint` / `idempotentHint`），可安全重试。

| 工具 | 何时用 | 必填参数 | 可选参数 | 返回 |
|------|--------|----------|----------|------|
| `describe_image` | 理解图片整体内容（画面、布局、风格） | `image_source` | `prompt`（描述角度）、`model` | `图片分析结果：\n{描述}` |
| `extract_text` | 只要照抄图里的文字（报错、票据、笔记） | `image_source` | `language`（`auto` 默认，或 `zh` / `en` 等） | 保持原排版的纯文字 |
| `ask_about_image` | 针对图片定向回答（数值、步骤、判断） | `image_source`、`question` | — | 针对问题的回答 |
| `analyze_layout` | 前端复刻：还原界面元素树与坐标 | `image_source` | `detail`（`basic` 默认 / `detailed` 含样式）、`model` | JSON：`layout_type` + `summary` + `elements`（`type` / `text` / `position` 百分比坐标 / `children`，detailed 加 `styles`） |
| `extract_table` | 表格截图 / 照片要结构化数据 | `image_source` | `model` | Markdown 表格；检测到合并单元格时追加 rowspan / colspan JSON |
| `analyze_images` | 一次涉及多张图（对比、统一评审） | `image_sources`（string[]） | `prompt`、`model` | `[序号] 来源: 结果` 列表 + `【跨图汇总】` |

**选型纪律**（Server 的 `instructions` 会把这套规则直接告诉 agent）：能 OCR 就别让模型看图说话；能定向提问就别大段描述；单张图别用批量工具；图片来源优先本地路径（少一次上传）。

调用示例：

```json
{"tool": "analyze_layout", "arguments": {"image_source": "/tmp/home.png", "detail": "detailed"}}
{"tool": "extract_table", "arguments": {"image_source": "https://example.com/report.png"}}
{"tool": "ask_about_image", "arguments": {"image_source": "/tmp/err.png", "question": "报错信息里的端口号是多少？"}}
```

## 配置

所有配置来自环境变量或 `.env`（环境变量优先）。MCP 客户端配置里的 `env` 字段等价于环境变量，因此**推荐直接在客户端配置里填 Key**，不依赖 `.env`。

### 先选后端：速查表

| 想用什么 | `VISION_PROVIDER` | 需要填的变量 | 默认模型 |
|---------|-------------------|--------------|---------|
| 任意 OpenAI 兼容厂商（默认，推荐） | `openai` | `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL` | `gpt-5.6-luna` |
| Claude 视觉（高质量档） | `anthropic` | `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` / `ANTHROPIC_BASE_URL` | `claude-sonnet-5` |
| OpenAI 官方 Responses（gpt-5 系列） | `responses` | `RESPONSES_API_KEY` / `RESPONSES_MODEL` / `RESPONSES_BASE_URL` | `gpt-5.6` |
| Google Gemini 原生 | `gemini` | `GEMINI_API_KEY` / `GEMINI_MODEL` / `GEMINI_BASE_URL` | `gemini-1.5-pro` |
| Google Gemini 新协议 | `gemini-interactions` | `GEMINI_API_KEY` / `GEMINI_MODEL` | 见 Gemini 官方文档 |

换后端 = 整体替换那一组变量，未填的走默认值：

```dotenv
# Anthropic Claude（UI 布局 / 表格 / 高分辨率截图质量档）
VISION_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-5
# ANTHROPIC_BASE_URL 默认 https://api.anthropic.com/v1，走代理时改这里

# OpenAI Responses（gpt-5 系列官方协议）
VISION_PROVIDER=responses
RESPONSES_API_KEY=sk-...
RESPONSES_MODEL=gpt-5.6

# Gemini（generateContent 与 Interactions 复用同一组 GEMINI_* 配置）
VISION_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
```

### 核心机制：任意 OpenAI 兼容厂商都能用

默认 `openai` 后端走 **Chat Completions 协议**（`/chat/completions` + `image_url` 传图）。只要厂商提供 OpenAI 兼容接口就能接入，不限于 GPT——换厂商只改 3 个值：

| 变量 | 作用 |
|------|------|
| `OPENAI_API_KEY` | 该厂商平台申请的 API Key |
| `OPENAI_MODEL` | 该厂商支持图片输入的模型名 |
| `OPENAI_BASE_URL` | 该厂商的 OpenAI 兼容端点；留空 = OpenAI 官方 `https://api.openai.com/v1` |

### 各厂商 base_url 参考

| 厂商 | `OPENAI_BASE_URL` | 视觉模型示例 |
|------|-------------------|--------------|
| OpenAI 官方 | 留空（默认 `https://api.openai.com/v1`） | `gpt-4o`、`gpt-5.6-luna` |
| 阿里通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-vl-max`、`qwen-vl-plus` |
| 阶跃星辰 | `https://api.stepfun.com/step_plan/v1` | `step-3.7-flash` 等支持视觉的型号 |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4v-plus`、`glm-4v-flash` |
| Moonshot Kimi | `https://api.moonshot.cn/v1` | 支持视觉的 moonshot 型号 |
| 深度求索 DeepSeek | `https://api.deepseek.com/v1` | 需确认该型号支持视觉输入 |
| 本地 Ollama | `http://127.0.0.1:11434/v1` | `llava`、`qwen2.5vl` |
| 本地 vLLM | `http://127.0.0.1:8000/v1` | 自行部署的多模态模型 |

> **本地模型说明**：视觉后端的 `base_url` 是**用户自己配置的信任端点**，不走 SSRF 校验，所以 `127.0.0.1` 可以直接用，无需开 `ALLOW_PRIVATE_URLS`（那个只管「图片 URL 下载」，不管 API 端点）。

### 环境变量完整参考

**后端选择**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VISION_PROVIDER` | `openai` | 视觉后端：`openai` / `anthropic` / `responses` / `gemini` / `gemini-interactions` |
| `OCR_BACKEND` | 空 | `extract_text` 单独用哪个后端；留空跟随 `VISION_PROVIDER` |

**各后端凭证**（`{P}` = `OPENAI` / `ANTHROPIC` / `RESPONSES` / `GEMINI`）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `{P}_API_KEY` | 空 | 该后端的 API Key |
| `{P}_MODEL` | 见速查表 | 该后端的视觉模型名 |
| `{P}_BASE_URL` | 官方端点 | 接口地址，可改为代理 / 兼容服务（Gemini 两个后端共用 `GEMINI_*`） |

**性能与图片处理**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `IMAGE_MAX_DIM` | `2048` | 预处理最大边长（px），超过等比缩放并转 JPEG；`0` 关闭预处理 |
| `CACHE_ENABLED` | `true` | 是否缓存视觉结果（LRU + TTL） |
| `CACHE_MAX_SIZE` | `128` | 结果缓存最大条目数 |
| `CACHE_TTL` | `3600` | 结果缓存存活秒数 |
| `IMAGE_CACHE_TTL` | `300` | 已解析图片（下载 / 读盘结果）缓存秒数；`0` 每次都重新取图 |
| `IMAGE_CACHE_MAX_SIZE` | `8` | 已解析图片缓存条目数 |
| `MAX_TOKENS` | `4096` | 视觉模型输出上限（推理模型需更大，否则正文被截断为空） |
| `REASONING_EFFORT` | 空 | `low` / `medium` / `high`；留空不发送该参数（部分后端不支持） |

**网络与可靠性**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `REQUEST_TIMEOUT` | `120` | 单次 HTTP 请求超时（秒） |
| `REQUEST_DEADLINE` | `300` | 单次工具调用的**总**时间预算（含全部重试与降级）；`0` 不设限 |
| `MAX_RETRIES` | `3` | 重试次数（网络 / 超时与 429/5xx 重试；400/401/403/404 不重试） |
| `RETRY_BACKOFF` | `0.5` | 退避基数（秒），指数退避 + ±25% 抖动；429 尊重 `Retry-After` |

**安全**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MAX_IMAGE_BYTES` | `20971520` | 图片字节上限，三种来源统一校验，超过拒绝 |
| `ALLOW_PRIVATE_URLS` | `false` | 是否允许图片 URL 指向内网 / 保留地址（仅本地调试时开） |
| `ALLOWED_IMAGE_ROOTS` | 空 | 逗号分隔的本地目录白名单；非空时白名单外路径一律拒绝 |
| `LOG_LEVEL` | `INFO` | stderr 日志级别（`TRACE`…`WARNING`）；`DEBUG` 会打出完整入参摘要 |

## 视觉后端与协议取舍

> 排名基于「个人自用 + 大陆网络 + OpenAI 兼容端点为主」的场景（通义 / 智谱 / 阶跃 / 本地 Ollama）。
> 协议是「信封」、模型是「内容」，真正的差异在生态广度、大陆可达性与结构化输出保障。

| 排名 | Provider | 协议 | 一句话定位 |
|---|---|---|---|
| 1 | **`openai`** | OpenAI Chat Completions | 默认首选：生态最广、大陆可用、特性完备 |
| 2 | `anthropic` | Anthropic Messages | 视觉质量天花板，但需代理 + 偏贵 |
| 3 | `responses` | OpenAI Responses | 官方新协议，生态窄（仅 OpenAI / Azure） |
| 4 | `gemini` | Google generateContent | Google 官方，大陆不可达，已被标 legacy |
| 5 | `gemini-interactions` | Google Interactions | 最新协议，新能力首发地，生态最窄 |

**1. `openai` — Chat Completions（推荐默认）**

- 优点：厂商覆盖最广（OpenAI + 通义 / 智谱 / 阶跃 / DeepSeek / Kimi / Ollama / vLLM 全部提供兼容端点）；`response_format` 与 `reasoning_effort` 都支持；适配器最成熟（含空内容重试）。
- 缺点：第三方厂商兼容层的实现完整度不一，个别厂商不支持 `response_format`（自动降级为普通请求 + JSON 容错解析兜底）。
- 适用：绝大多数场景。你想用的模型有 OpenAI 兼容端点，就选它。

**2. `anthropic` — Claude Messages API（高质量档）**

- 优点：Claude 视觉在 UI 布局还原、表格 / 图表抽取、高分辨率截图细节上明显强于国内生态；原生 `json_schema` 结构化输出比 `json_object` 的提示词约束更可靠；1M 上下文可一次塞大量图。
- 缺点：`api.anthropic.com` 大陆无法直连（需代理 + 国际支付）；美元计价偏贵；图片按视觉 token 计费（单图约 1.3k–4.8k）。
- 适用：追求视觉质量上限、且能稳定访问 Anthropic 时按需切换。

**3. `responses` — OpenAI Responses API**

- 优点：OpenAI 官方下一代协议；内置工具（web search / image generation）仅此协议有；gpt-5 系列 Pro / Codex 模型只走它。
- 缺点：第三方兼容厂商几乎都只实现 Chat Completions，本后端实际只对 OpenAI / Azure 官方端点有意义；纯图→文能力与 Chat Completions 对齐。
- 适用：用 OpenAI 官方 gpt-5 系列，或需要其内置工具时。

**4. `gemini` — Google generateContent**

- 优点：Google 官方，单次图→文完全够用，generateContent 仍受支持、无关闭日期。
- 缺点：大陆不可达；Google 已将其标记 legacy，新能力（多轮状态、agentic）只在 Interactions 首发；默认模型名偏旧，建议显式指定。
- 适用：已有 Google API Key 且网络可达。

**5. `gemini-interactions` — Google Interactions API**

- 优点：Google 新模型 / 新能力首发地；服务端多轮状态、可观测执行步骤。
- 缺点：生态最窄；对单次图片理解无增量收益（OpenEye 不用多轮）；`store=true` 默认留存数据（适配器已显式 `store=false`）。
- 适用：尝鲜 Gemini 新模型、且明确需要其新能力时。

**一句话总结**：日常用 `openai`；要最强视觉质量且能访问 Anthropic 用 `anthropic`；用 OpenAI 官方 gpt-5 系列用 `responses`；Gemini 两个协议是「有时想用 Google 模型」的备选。

各适配器内部已消化协议差异（认证头、图片 block 形式、响应解析、结构化输出参数），工具层完全共用，切换后端不需要改动任何调用方代码。

## 客户端集成

OpenEye 是标准 stdio MCP Server：配置里只需要 `command`（+ 可选 `args`）与 `env`，**不要**填 `url` / `serverUrl` / `headers` 等 HTTP 字段（多数客户端中 stdio 与 HTTP 互斥）。

### 方式一：Claude Code 命令行（推荐）

```bash
claude mcp add openeye --env VISION_PROVIDER=openai \
  --env OPENAI_API_KEY=sk-your-key \
  --env OPENAI_MODEL=qwen-vl-max \
  --env OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1 \
  -- openeye
```

> 结尾的 `-- openeye` 不是可选的：`claude mcp add` 必须带启动命令，`--` 之后才是要执行的命令（漏掉会报 `missing required argument 'commandOrUrl'`）。
> 前提：`openeye` 已在 PATH（`pip install openeye-mcp` 后自动注册）。

用 OpenAI 官方可以不写 `OPENAI_BASE_URL`；换厂商就替换 `OPENAI_*` 三个值；换 Gemini 就改成 `VISION_PROVIDER=gemini` + `GEMINI_API_KEY` + `GEMINI_MODEL`。

### 方式二：配置文件 `.mcp.json`

```json
{
  "mcpServers": {
    "openeye": {
      "command": "openeye",
      "env": {
        "VISION_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

`env` 里可填上文「环境变量完整参考」中的任意变量，未填的走默认值。

若 `openeye` 不在 PATH，把 `command` 换成完整路径：

- Windows：`"<你的 Python 安装目录>/Scripts/openeye.exe"`
- macOS / Linux：`"<你的 Python 安装目录>/bin/openeye"`

### 方式三：其他客户端

Cursor、Cline、Windsurf、Codex CLI、Zed、Continue、Roo Code、opencode 的配置文件位置、字段命名差异与逐一示例，见 **[编码工具接入指南](docs/编码工具接入指南.md)**。

## 安全设计

| 威胁 | 处理 |
|------|------|
| SSRF（图片 URL 指向内网 / 云元数据） | 解析域名后逐个校验 `is_global`（含 CGNAT `100.64.0.0/10` 等保留段），并把请求**固定到已校验的 IP**（防 DNS rebinding / TOCTOU）；重定向**逐跳**重新校验，不依赖自动跳转 |
| 代理 / 凭据外泄 | 取图客户端 `trust_env=False`，不读 `HTTP_PROXY` / `netrc`；`ALLOW_PRIVATE_URLS` 默认关闭 |
| 内存耗尽 | 流式下载并边读边限幅，超过 `MAX_IMAGE_BYTES` 立即中断，不会读完整个响应体再判 |
| 任意本地文件读取 | 本地路径必须能被 Pillow 解码为真实图片（拒绝 HTML / 文本被当成图片送进模型）；可用 `ALLOWED_IMAGE_ROOTS` 收紧到目录白名单 |
| API Key 泄漏到日志 / 错误信息 | 异常文本统一脱敏（`Bearer`、引号包裹的 Key 等被掩码）；日志只记入参摘要，绝不落 data URI 正文 |
| 请求堆积拖死客户端 | `REQUEST_DEADLINE` 为单次工具调用设总预算，超预算直接以 `isError` 返回而不是无限重试 |

## 故障排查

| 现象 | 原因 / 处理 |
|------|-------------|
| `missing required argument 'commandOrUrl'` | `claude mcp add` 漏了 `-- openeye` 启动命令 |
| 客户端提示找不到命令 | 虚拟环境未激活或不在 PATH，改用完整路径（见「方式二」） |
| 401 / 403 | Key 未注入或不属于该端点：MCP 配置的 `env` 优先于 `.env`，确认两边没有互相覆盖 |
| 「模型未返回内容」/ 结果为空 | 推理模型把 token 花在思考上：调大 `MAX_TOKENS`，或清空 `REASONING_EFFORT` |
| 图片 URL 被拒（SSRF 校验） | 该 URL 解析到内网 / 保留地址；确属本地调试再设 `ALLOW_PRIVATE_URLS=true` |
| 本地路径被拒 | 文件不是可解码的图片，或落在 `ALLOWED_IMAGE_ROOTS` 白名单之外 |
| 超过总时间预算 | 后端太慢或网络不通：调大 `REQUEST_DEADLINE`，或换离你更近的 `base_url` |
| 想看重试细节 | `LOG_LEVEL=DEBUG`（会打印每次重试与入参摘要，注意日志外泄风险） |

## 开发

```bash
git clone https://github.com/ouli-1242/openeye-mcp.git
cd openeye-mcp
pip install -e ".[dev]"

pytest tests/ -v          # 全部使用 mock，不发真实 API 请求
ruff check src tests      # 代码风格
mypy src/openeye_mcp      # 类型检查
python -m build           # 打包自检
```

### 新增一个视觉后端

1. 在 `src/openeye_mcp/vision/` 下新增 `xxx_adapter.py`，继承 `VisionAdapter`：声明 `settings_prefix` 与 `default_base_url`（模型 / Key / 端点自动从配置解析），实现 `describe`（带图请求）与 `describe_text`（纯文本汇总）。
2. 在 `config.py` 的 `VisionProvider` 字面量里加上后端名，并在 `vision/registry.py` 的 `ADAPTERS` 登记一行——工厂分发、可选值校验、错误提示与文档都跟着这张表走。

### 项目结构

```
openeye-mcp/
├── pyproject.toml                  # 元数据、依赖、openeye 入口、ruff/mypy/pytest 配置
├── .env.example                    # 配置示例
├── docs/
│   └── 编码工具接入指南.md          # 各 MCP 客户端的逐一接入方式
├── src/
│   └── openeye_mcp/
│       ├── __init__.py             # __version__（版本单一来源）
│       ├── server.py               # MCP Server 组装：工具表、入参校验、超时与进度
│       ├── tools.py                # 六个工具的实现
│       ├── image_utils.py          # 图片来源解析（本地 / URL / data URI + SSRF 防护）
│       ├── config.py               # pydantic-settings 配置
│       ├── cache.py                # 视觉结果缓存 + 已解析图片缓存
│       ├── errors.py               # 错误分类与凭据脱敏
│       ├── table.py                # 表格 JSON → Markdown
│       ├── budget.py               # 单次调用的总时间预算
│       ├── progress.py             # MCP 进度上报
│       └── vision/
│           ├── registry.py         # provider → 适配器 的唯一映射
│           ├── base.py             # VisionAdapter 基类 + VisionOptions
│           ├── _http.py            # 复用的 AsyncClient
│           ├── _retry.py           # 统一重试 / 退避 / Retry-After
│           ├── openai_adapter.py
│           ├── responses_adapter.py
│           ├── anthropic_adapter.py
│           ├── gemini_adapter.py
│           └── gemini_interactions_adapter.py
└── tests/                          # 单元 + 安全回归（含 SSRF / 脱敏 / 越权用例）
```

开发自检在本地跑：`ruff check src tests`、`mypy src`、`pytest`（测试套件含 SSRF / 凭据脱敏 / 越权回归用例）。

## 致谢

本项目是 [Favio8/deepeye](https://github.com/Favio8/deepeye) 的**二创**（衍生作品）。上游以 MIT 协议发布，本仓库在其基础上做了改造：包名由 `deepeye` 改为 `openeye_mcp`、新增视觉后端适配器（Anthropic / OpenAI Responses / Gemini Interactions）、补充错误分类与重试、缓存与测试等。

按 MIT 协议要求，上游的原始版权与许可文本已完整保留：

- 上游项目：<https://github.com/Favio8/deepeye>
- 上游原始版权：Copyright (c) 2026 Favio8
- 本仓库改造部分：Modifications Copyright (c) 2026 ouli-1242

## License

[MIT](LICENSE) © Favio8（上游）· ouli-1242（本仓库改造）
