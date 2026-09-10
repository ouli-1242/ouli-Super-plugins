# DeepEye

为纯文本大模型提供视觉能力的 MCP Server（图像描述 / OCR / 视觉问答 / 布局分析）。

## 安装

> 本项目为本地自制项目，未发布到 PyPI，请从源码安装。

### 从源码安装

```bash
git clone https://github.com/ouli-1242/deepeye-mcp.git
cd deepeye-mcp

# 普通安装（代码复制到 site-packages，源码目录可随意移动）
pip install .

# 开发模式（editable，改代码即时生效，源码目录不可移动）
pip install -e .
```

> 说明：editable 安装（`-e .`）让源码改动即时生效，无需每次重装。支持全局 Python 或任意虚拟环境；本仓库开发环境使用全局 Python 3.11+。

装好后命令 `deepeye` 即可用。

要求：Python 3.11+，一个视觉模型 API Key。

## 卸载

```bash
pip uninstall deepeye-mcp
```

## 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env`：

```dotenv
VISION_PROVIDER=openai
OPENAI_API_KEY=sk-your-real-key-here
OPENAI_MODEL=gpt-5.6-luna
# 如果用兼容服务，可改 OPENAI_BASE_URL
# OPENAI_BASE_URL=https://your-compatible-service/v1
```

### 先选后端：速查表

DeepEye 支持五类视觉后端，用 `VISION_PROVIDER` 切换。**每个后端有自己的变量组**——选好后端填对应那组即可，未填的用默认值：

| 想用什么 | `VISION_PROVIDER` | 需要填的变量 | 典型模型 |
|---------|-------------------|--------------|---------|
| 任意 OpenAI 兼容厂商（默认，推荐） | `openai` | `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL` | `qwen-vl-max`、`glm-4v-plus`、`llava` |
| OpenAI 官方 gpt-5 系列 | `responses` | `RESPONSES_API_KEY` / `RESPONSES_MODEL` / `RESPONSES_BASE_URL` | `gpt-5.6` |
| Claude 视觉（高质量档） | `anthropic` | `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` / `ANTHROPIC_BASE_URL` | `claude-sonnet-5` |
| Google Gemini | `gemini` | `GEMINI_API_KEY` / `GEMINI_MODEL` | `gemini-2.0-flash` |
| Google Gemini（新协议尝鲜） | `gemini-interactions` | `GEMINI_API_KEY` / `GEMINI_MODEL` | Gemini 3.x 系列（见官方文档） |

各后端配置示例（换后端 = 整体替换变量组）：

```dotenv
# 后端一：任意 OpenAI 兼容厂商（默认，改 base_url 即换厂商）
VISION_PROVIDER=openai
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=qwen-vl-max
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

```dotenv
# 后端二：Claude 视觉（高质量档）
VISION_PROVIDER=anthropic
ANTHROPIC_API_KEY=你的key
ANTHROPIC_MODEL=claude-sonnet-5
# ANTHROPIC_BASE_URL 默认 https://api.anthropic.com/v1，可改成代理地址
```

```dotenv
# 后端三：OpenAI Responses（gpt-5 系列）
VISION_PROVIDER=responses
RESPONSES_API_KEY=sk-your-key
RESPONSES_MODEL=gpt-5.6
```

```dotenv
# 后端四：Google Gemini
VISION_PROVIDER=gemini
GEMINI_API_KEY=你的key
GEMINI_MODEL=gemini-2.0-flash
```

```dotenv
# 后端五：Google Gemini（Interactions API）
VISION_PROVIDER=gemini-interactions
GEMINI_API_KEY=你的key
GEMINI_MODEL=你的模型
```

### 核心机制：任意 OpenAI 兼容厂商都能用（openai 后端）

这是默认的 `openai` 后端，走 **OpenAI Chat Completions 协议**（`/chat/completions` 接口 + `image_url` 传图）。
只要厂商提供 OpenAI 兼容接口，任何模型都能接入——不限于 GPT，**换厂商只需改 3 个变量**（这 3 个变量只属于 openai 后端；其他后端各自的变量组见上方速查表）：

| 变量 | 作用 |
|------|------|
| `OPENAI_API_KEY` | 该厂商平台申请的 API Key |
| `OPENAI_MODEL` | 该厂商的视觉模型名（要支持图片输入） |
| `OPENAI_BASE_URL` | 该厂商的 OpenAI 兼容端点地址（留空则用 OpenAI 官方 `https://api.openai.com/v1`） |

**选择模型的关键**：模型必须支持**图片/视觉输入**（多模态模型）。纯文本模型（如 DeepSeek-V3、普通 GPT-4）无法看图片，会报错或忽略图片。

### 各厂商 base_url 参考（均已验证端点可达）

| 厂商 | `OPENAI_BASE_URL` | 视觉模型示例 |
|------|-------------------|--------------|
| OpenAI 官方 | `https://api.openai.com/v1`（留空默认） | `gpt-4o`、`gpt-5.6-luna` |
| 阿里通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-vl-max`、`qwen-vl-plus` |
| 阶跃星辰 | `https://api.stepfun.com/step_plan/v1` | `step-3.7-flash` 等支持视觉的模型 |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4v-plus`、`glm-4v-flash` |
| Moonshot Kimi | `https://api.moonshot.cn/v1` | 支持视觉的 moonshot 模型 |
| 深度求索 DeepSeek | `https://api.deepseek.com/v1` | 需确认支持视觉的最新模型 |
| 本地 Ollama | `http://127.0.0.1:11434/v1` | `llava`、`qwen2.5vl` 等本地多模态模型 |
| 本地 vLLM | `http://127.0.0.1:8000/v1` | 部署的多模态模型 |

> **本地模型（Ollama/vLLM）说明**：视觉后端的 base_url 是**用户配置的信任端点**，
> 不经过 SSRF 校验，所以本地 `127.0.0.1` 地址可直接用，无需开启 `ALLOW_PRIVATE_URLS`
> （该选项只影响「图片 URL 下载」的防护，不影响 API 端点）。

配置示例（用阿里通义，其他厂商同理只改 3 个值）：

```dotenv
VISION_PROVIDER=openai
OPENAI_API_KEY=sk-your-dashscope-key
OPENAI_MODEL=qwen-vl-max
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

### 切换后端类型

DeepEye 支持五类视觉后端，用 `VISION_PROVIDER` 切换：

| `VISION_PROVIDER` | 说明 |
|-------------------|------|
| `openai` | OpenAI + 任意 OpenAI 兼容厂商（默认，推荐）。本地模型也走这个（改 base_url） |
| `gemini` | Google Gemini 原生 API（`generateContent`） |
| `gemini-interactions` | Google Gemini 新版 `Interactions API`（新模型/新能力首发地） |
| `anthropic` | Anthropic Claude 原生 Messages API（高质量视觉档） |
| `responses` | OpenAI 官方 Responses API（gpt-5 系列） |

### 协议排名与优缺点

> 排名基于「个人自用 + 大陆网络 + OpenAI 兼容端点为主」的典型场景
> （通义 / 智谱 / 阶跃 / 本地 Ollama）。各协议能力本身差异不大——模型是「内容」、
> 协议是「信封」；真正的差异在生态广度、大陆可达性、结构化输出保障。

| 排名 | Provider | 协议 | 一句话定位 |
|---|---|---|---|
| 🥇 1 | **`openai`** | OpenAI Chat Completions | 默认首选：生态最广、大陆可用、功能完备 |
| 🥈 2 | `anthropic` | Anthropic Messages API | 视觉质量天花板，但需代理 + 偏贵 |
| 🥉 3 | `responses` | OpenAI Responses API | OpenAI 官方新协议，生态窄（仅官方/Azure） |
| 4 | `gemini` | Google generateContent | Google 官方，大陆不可达，GenerateContent 已 legacy |
| 5 | `gemini-interactions` | Google Interactions API | 最新协议，新能力首发地，生态最窄 |

---

**🥇 1. `openai` — OpenAI Chat Completions（推荐默认）**

- **优点**：厂商覆盖最广（OpenAI + 通义 / 智谱 / 阶跃 / DeepSeek / Kimi / 本地 Ollama / vLLM 全部提供兼容端点）；大陆可直接用国内厂商；`response_format` / `reasoning_effort` 两个关键特性全支持；适配器最成熟（含空内容重试）。
- **缺点**：非 OpenAI 官方模型走的是各厂商自己实现的兼容层，个别厂商对 `response_format` 支持不完整（会触发降级到普通请求，靠 `_extract_json` 兜底）。
- **适用**：绝大多数场景。你想用的模型有 OpenAI 兼容端点就选它。

**🥈 2. `anthropic` — Anthropic Messages API（高质量档）**

- **优点**：Claude 视觉在 UI 布局还原（analyze_layout）、表格/图表抽取（extract_table）、高分辨率截图细节上明显强于国内生态；原生结构化输出（json_schema）比 OpenAI 的 json_object 提示词约束更可靠；1M 上下文可一次塞大量图。
- **缺点**：`api.anthropic.com` 大陆**无法直连**（需代理 + 国际支付）；美元计价偏贵；图片按视觉 token 计费（单图约 1.3k–4.8k）。
- **适用**：追求视觉质量上限、能稳定访问 Anthropic 时。作为「高端档」按需切换。

**🥉 3. `responses` — OpenAI Responses API（官方新协议）**

- **优点**：OpenAI 官方下一代协议；内置工具（web search / image generation 等）仅此协议有；gpt-5.4+ Pro/Codex 模型只走它。
- **缺点**：生态窄——**第三方兼容厂商几乎都是 Chat Completions**，Responses 只面向 OpenAI/Azure 官方端点；纯视觉能力与 Chat Completions 对齐，没有独占收益。
- **适用**：用 OpenAI 官方 gpt-5.6 等模型、或想用 OpenAI 内置工具时。

**4. `gemini` — Google generateContent（演进中）**

- **优点**：Google 官方；单次图→文完全够用；generateContent 仍受支持、无关闭日期。
- **缺点**：大陆**无法直连**（需代理）；Google 已将其标记 legacy，新能力（多轮状态、agentic）只在 Interactions 首发；默认模型名需手动更新（`gemini-1.5-pro` 已过时）。
- **适用**：已有 Google API key 且网络可达时。

**5. `gemini-interactions` — Google Interactions API（最新）**

- **优点**：Google 新模型/新能力首发地；服务端多轮状态、可观测执行步骤。
- **缺点**：生态最新也最窄；对单次图片理解无增量收益（deepeye 不用多轮）；`store=true` 默认留存数据（适配器已显式 `store=false`）。
- **适用**：想尝鲜 Gemini 3.x 新模型、且明确需要其新能力时。

> **一句话总结**：日常用 `openai`；想要最强视觉质量且能访问 Anthropic 用 `anthropic`；
> 用 OpenAI 官方 gpt-5 系列用 `responses`；Gemini 两个协议是「有时想用 Google 模型」时的备选。
>
> **各后端的完整配置示例见上文「先选后端：速查表」。**

> **协议说明**：`openai` / `responses` 传 OpenAI 兼容格式（本地 Ollama/vLLM 也走
> `openai`，改 `OPENAI_BASE_URL` 即可）；
> `anthropic` 走 Claude 原生 `Messages API`（`x-api-key` 认证 + `image` block）；
> `gemini` 走 Google `generateContent`，`gemini-interactions` 走 Google 新版
> `Interactions API`。各适配器内部已处理协议差异，工具层无需改动。

## 启动

```bash
deepeye
```

Server 通过 stdio 与 MCP 客户端通信，单独运行不会输出交互界面，需配合 MCP 客户端使用（见 [MCP 客户端集成](#mcp-客户端集成)）。

## 工具一览

### `describe_image` — 通用图像理解

对图片进行详细描述，可自定义描述角度。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `image_source` | string | 是 | 本地路径 / http(s) URL / `data:image/...;base64,...` |
| `prompt` | string | 否 | 描述提示词，不传则使用默认详细描述 |
| `model` | string | 否 | 临时指定视觉模型，不传则用配置默认值 |

**返回**：`图片分析结果：\n{描述}`

### `extract_text` — OCR 文字提取

仅提取图片中的文字，保持原文排版，不加任何额外描述。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `image_source` | string | 是 | 同上 |
| `language` | string | 否 | 识别语言，`auto`（默认）自动识别；其他值如 `zh` / `en` 会附加语言提示 |

**返回**：图片中提取到的纯文字。

### `ask_about_image` — 视觉问答

针对图片内容提出具体问题，获取定向回答。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `image_source` | string | 是 | 同上 |
| `question` | string | 是 | 要询问的问题 |

**返回**：针对问题的回答。

### `analyze_layout` — UI 布局结构化分析

对图片进行 UI 布局结构化分析，返回 JSON 格式的布局类型与元素树（类型/位置/样式），适合前端复刻。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `image_source` | string | 是 | 同上 |
| `detail` | string | 否 | 分析粒度：`basic`（默认，仅类型 + 文本 + 位置）或 `detailed`（额外返回颜色、字号、圆角等样式） |
| `model` | string | 否 | 临时指定视觉模型，不传则用配置默认值 |

**返回**：JSON 字符串，包含 `layout_type`（布局类型）、`summary`（一句话描述）与 `elements`（元素树）；每个元素含 `type`、`text`、`position`（百分比坐标）、`children`，`detailed` 模式额外返回 `styles`。

### `extract_table` — 图片转表格

提取图片中的表格为 Markdown（截图数据表 / 纸质表格 / 图表 / 合并单元格均支持）。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `image_source` | string | 是 | 本地路径 / http(s) URL / data URI |
| `model` | string | 否 | 临时指定视觉模型 |

**返回**：Markdown 表格；检测到合并单元格时追加 JSON 结构（含 rowspan/colspan）。

### `analyze_images` — 批量图片分析

对多张图片应用同一提示词，返回逐图结果 + 跨图对比汇总。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `image_sources` | string[] | 是 | 多张图片来源（本地路径 / URL / data URI） |
| `prompt` | string | 否 | 每张图统一提示词，默认详细描述 |
| `model` | string | 否 | 临时指定视觉模型 |

**返回**：`[序号] 来源: 结果` 列表 + `【跨图汇总】` 对比总结。

## 配置参考

所有配置通过环境变量或 `.env` 文件加载（参考 `.env.example`）。按后端分组：

**后端选择（全局）**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VISION_PROVIDER` | `openai` | 视觉后端提供者：`openai` / `gemini` / `gemini-interactions` / `anthropic` / `responses` |
| `OCR_BACKEND` | `openai` | `extract_text` 实际使用的视觉后端（可单独指定） |

**openai 后端（默认，OpenAI 兼容协议）**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENAI_API_KEY` | — | OpenAI 或兼容服务的 API Key |
| `OPENAI_MODEL` | `gpt-5.6-luna` | 视觉模型名称 |
| `OPENAI_BASE_URL` | — | 接口地址，留空用官方 `https://api.openai.com/v1`；可改为 Azure / 代理 / 兼容服务 |

**gemini / gemini-interactions 后端（Google 协议）**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GEMINI_API_KEY` | — | Gemini 后端 API Key |
| `GEMINI_MODEL` | `gemini-1.5-pro` | Gemini 模型名称 |

**anthropic 后端（Claude Messages API）**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ANTHROPIC_API_KEY` | — | Anthropic Claude API Key（原生 Messages API） |
| `ANTHROPIC_MODEL` | `claude-sonnet-5` | Claude 视觉模型名 |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com/v1` | Anthropic 接口地址 |

**responses 后端（OpenAI Responses API）**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RESPONSES_API_KEY` | — | OpenAI Responses API Key |
| `RESPONSES_MODEL` | `gpt-5.6` | Responses 视觉模型名 |
| `RESPONSES_BASE_URL` | `https://api.openai.com/v1` | Responses 接口地址（OpenAI 官方协议） |

**通用（所有后端共用）**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `IMAGE_MAX_DIM` | `2048` | 图片预处理最大边长（像素），超过则等比缩放转 JPEG；`0` 禁用预处理 |
| `CACHE_ENABLED` | `true` | 是否开启视觉结果缓存（LRU + TTL） |
| `CACHE_MAX_SIZE` | `128` | 缓存最大条目数 |
| `CACHE_TTL` | `3600` | 缓存存活秒数 |
| `REQUEST_TIMEOUT` | `120` | 视觉后端 HTTP 请求超时（秒） |
| `MAX_RETRIES` | `3` | 失败重试次数（仅对网络/超时错误重试） |
| `MAX_TOKENS` | `4096` | 视觉模型返回的最大 token 数 |
| `REASONING_EFFORT` | 空 | 推理深度 `low`/`medium`/`high`；留空不发送该参数（部分后端不支持） |
| `MAX_IMAGE_BYTES` | `20971520` | 图片大小上限（字节），三种来源（URL / 本地路径 / data URI）统一校验，超过拒绝 |
| `ALLOW_PRIVATE_URLS` | `false` | 是否允许访问内网/保留地址（SSRF 防护，默认禁止；仅本地调试设为 `true`） |

> 厂商 base_url 示例见上文「各厂商 base_url 参考」，后端类型切换见「切换后端类型」。

> 厂商 base_url 示例见上文「各厂商 base_url 参考」，后端类型切换见「切换后端类型」。

## MCP 客户端集成

DeepEye 是标准 stdio MCP Server，在 MCP 配置中声明 `deepeye` 启动命令，并通过 `env` 字段传入视觉后端凭证。**env 字段里填的就是上面「配置 API Key」的环境变量**，二者效果完全一样（MCP 配置的 env 优先于 `.env` 文件）。

### 方式一：Claude Code 命令行（推荐）

OpenAI 官方 / 任意兼容厂商：

```bash
claude mcp add deepeye --env VISION_PROVIDER=openai \
  --env OPENAI_API_KEY=sk-your-key \
  --env OPENAI_MODEL=qwen-vl-max \
  --env OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

- 用 OpenAI 官方可以不写 `OPENAI_BASE_URL`（默认官方端点）
- 用其他厂商，把 `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL` 换成对应平台的值
- 用 Gemini 原生就换成 `VISION_PROVIDER=gemini` + `GEMINI_API_KEY` + `GEMINI_MODEL`

> 前提：`deepeye` 命令已在 PATH（`pip install -e .` 后自动注册）。

### 方式二：配置文件 `.mcp.json`

在项目根目录（或 Claude Code 起始目录）创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "deepeye": {
      "command": "deepeye",
      "env": {
        "VISION_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-your-key",
        "OPENAI_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "OPENAI_MODEL": "qwen-vl-max"
      }
    }
  }
}
```

**env 字段可选变量**（按需填写，未写的用默认值）：

| env 键 | 作用 | 不填时 |
|--------|------|--------|
| `VISION_PROVIDER` | 后端类型 `openai`/`gemini`/`gemini-interactions`/`anthropic`/`responses` | `openai` |
| `OPENAI_API_KEY` | OpenAI 兼容厂商的 Key | 空（部分厂商可无 key） |
| `OPENAI_MODEL` | 视觉模型名 | `gpt-5.6-luna` |
| `OPENAI_BASE_URL` | 厂商 OpenAI 兼容端点 | OpenAI 官方 |
| `GEMINI_API_KEY` / `GEMINI_MODEL` / `GEMINI_BASE_URL` | Gemini 后端 | 仅 gemini / gemini-interactions 生效 |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | Claude 后端 | 仅 anthropic 生效 |
| `RESPONSES_API_KEY` / `RESPONSES_MODEL` | OpenAI Responses 后端 | 仅 responses 生效 |
| `OCR_BACKEND` | OCR 单独用哪个后端 | 同 `VISION_PROVIDER` |
| `REASONING_EFFORT` | 推理深度 `low`/`medium`/`high` | 空（不发送） |

> 若 `deepeye` 不在 PATH，把 `command` 换成完整路径：
> `"command": "<你的 Python 安装目录>/Scripts/deepeye.exe"`（Windows 示例；macOS / Linux 为 `<...>/bin/deepeye`）。

保存后重启 Claude Code，`/mcp` 面板中应显示 `deepeye` 已连接。若显示 failed，运行 `deepeye` 查看报错。

其他客户端（Cursor / Cline / Windsurf 等）的配置方式见 [接入 Coding Agent 指南](docs/coding-agent-integration.md)。

> **opencode 用户**：安装 [opencode-easy-vision](https://github.com/devadathanmb/opencode-easy-vision) 插件后，粘贴图片会自动保存为临时文件并调用 DeepEye 分析。配置方法见 [接入指南的 opencode 章节](docs/coding-agent-integration.md#进阶粘贴图片自动调用-deepeyeopencode-easy-vision-插件)。

## 支持的视觉后端

| 后端 | 状态 | 说明 |
|------|------|------|
| **OpenAI 兼容** | 已实现 | 支持 OpenAI 官方、Azure OpenAI、阿里通义 Qwen-VL、智谱 GLM-4V、Moonshot 等 |
| **Gemini** | 已实现 | 支持 Google Gemini 系列模型（gemini-1.5-pro / gemini-2.0-flash 等） |
| **自定义 OpenAI 兼容** | 已实现 | 用于任何兼容 OpenAI Chat Completions 格式的自部署服务（vLLM / Ollama / 通义 Qwen-VL / 智谱等） |
| 本地 OCR (Tesseract / PaddleOCR) | 计划中 | 隐私场景下数据不出本机 |

## 开发

### 运行测试

```bash
pytest tests/ -v
```

测试覆盖图像源解析、视觉适配器工厂、六个工具的 prompt 组装逻辑，全部使用 mock，不发起真实 API 调用。

### 新增视觉后端

1. 在 `src/deepeye_mcp/vision/` 下新增 `xxx_adapter.py`，继承 `VisionAdapter`，实现 `describe` 方法
2. 在 `vision/__init__.py` 的工厂函数中注册新分支

## 项目结构

```
deepeye/
├── pyproject.toml              # 项目元数据、依赖、入口命令、pytest 配置
├── .env.example                # 配置示例
├── src/
│   └── deepeye_mcp/
│       ├── __init__.py         # __version__
│       ├── server.py           # MCP Server 组装（mcp 2.0 API）
│       ├── tools.py            # 六个 MCP 工具实现
│       ├── image_utils.py      # 图像源解析（本地/URL/data URI）
│       ├── config.py           # pydantic-settings 配置加载
│       ├── cache.py            # 视觉结果缓存
│       └── vision/
│           ├── __init__.py     # create_vision_adapter 工厂
│           ├── base.py         # VisionAdapter 抽象基类
│           ├── openai_adapter.py
│           ├── responses_adapter.py
│           ├── anthropic_adapter.py
│           ├── gemini_adapter.py
│           └── gemini_interactions_adapter.py
└── tests/
    ├── test_image_utils.py
    ├── test_vision_factory.py
    ├── test_adapters.py
    └── test_tools.py
```

## License

[MIT](LICENSE) © DeepEye Contributors