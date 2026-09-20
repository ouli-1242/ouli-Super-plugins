"""OpenEye MCP Server 组装。

通过 ``mcp`` 官方库的 ``stdio_server`` 启动 MCP Server，注册
``list_tools`` 与 ``call_tool`` 处理器，Server 名称为 ``openeye``。

注意：本实现适配 ``mcp>=2.0.0`` 的 API：使用构造器注册
``on_list_tools`` / ``on_call_tool`` 处理器（而非旧版装饰器），handler
返回 ``ListToolsResult`` / ``CallToolResult``。
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import sys
from collections.abc import Awaitable, Callable

from loguru import logger
from mcp.server import NotificationOptions, Server
from mcp.server.context import ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
    ToolAnnotations,
)

from openeye_mcp import __version__
from openeye_mcp.budget import budget
from openeye_mcp.config import settings
from openeye_mcp.errors import VisionError
from openeye_mcp.progress import progress_scope
from openeye_mcp.tools import (
    analyze_images,
    analyze_layout,
    ask_about_image,
    describe_image,
    extract_table,
    extract_text,
)
from openeye_mcp.vision._http import aclose_client

_BASE_TOOLS: list[Tool] = [
    Tool(
        name="describe_image",
        description="描述图片内容，支持本地路径 / 公网 URL / Base64 data URI 三种来源。"
        " 何时用：需要理解图片整体内容（画面、布局、风格）时优先用；"
        " 何时不用：只要文字用 extract_text，只要回答问题用 ask_about_image。",
        inputSchema={
            "type": "object",
            "properties": {
                "image_source": {
                    "type": "string",
                    "description": "图像来源：本地路径、http(s) URL 或 data:image/...;base64,... 形式的 data URI。",
                },
                "prompt": {
                    "type": "string",
                    "description": "描述提示词，可选；不传则使用默认详细描述提示词。",
                },
                "model": {
                    "type": "string",
                    "description": "可选模型名称覆盖，不传则使用配置默认模型。",
                },
            },
            "required": ["image_source"],
        },
    ),
    Tool(
        name="extract_text",
        description="提取图片中的文字（OCR），保持原文排版，不加额外描述。"
        "何时用：图片/截图里有需要照抄的文字（报错信息、票据、白板笔记）。"
        "何时不用：要理解内容含义用 describe_image 或 ask_about_image；"
        "表格/图表截图要结构化数据用 extract_table（本工具不保留行列结构）。",
        inputSchema={
            "type": "object",
            "properties": {
                "image_source": {
                    "type": "string",
                    "description": "图像来源：本地路径、http(s) URL 或 data:image/...;base64,... 形式的 data URI。",
                },
                "language": {
                    "type": "string",
                    "description": "识别语言，默认 auto 自动识别；其他值会附加语言提示。",
                },
            },
            "required": ["image_source"],
        },
    ),
    Tool(
        name="ask_about_image",
        description="根据图片内容回答问题（视觉问答）：关于图片的任何具体问题。"
        "何时用：看图名、图里的数字、操作步骤、故障判断等需要定向回答时。"
        "何时不用：要整体描述用 describe_image，要原文文字用 extract_text。",
        inputSchema={
            "type": "object",
            "properties": {
                "image_source": {
                    "type": "string",
                    "description": "图像来源：本地路径、http(s) URL 或 data:image/...;base64,... 形式的 data URI。",
                },
                "question": {
                    "type": "string",
                    "description": "要回答的问题。",
                },
            },
            "required": ["image_source", "question"],
        },
    ),
    Tool(
        name="analyze_layout",
        description="UI 布局结构化分析：返回 JSON，包含元素类型、位置坐标、样式（detailed 模式）。"
        "适合前端复刻场景：需要按图还原网页/APP 界面结构时用；general 看图用 describe_image。",
        inputSchema={
            "type": "object",
            "properties": {
                "image_source": {"type": "string", "description": "图片来源：本地绝对路径、公网URL或Base64数据"},
                "detail": {"type": "string", "description": "分析粒度：basic（类型+位置）或 detailed（含颜色/字号等样式）", "default": "basic", "enum": ["basic", "detailed"]},
                "model": {"type": "string", "description": "指定视觉模型，不填使用默认配置"}
            },
            "required": ["image_source"]
        }
    ),
    Tool(
        name="extract_table",
        description="提取图片中的表格为 Markdown（截图/纸质/图表/合并单元格均支持）；复杂表格附带 JSON 结构。"
        "何时用：用户贴了表格截图/表格照片需要结构化数据时；数据整理后可直接喂给代码或分析。",
        inputSchema={
            "type": "object",
            "properties": {
                "image_source": {"type": "string", "description": "图像来源：本地路径、http(s) URL 或 data URI。"},
                "model": {"type": "string", "description": "可选模型名称覆盖。"},
            },
            "required": ["image_source"],
        },
    ),
    Tool(
        name="analyze_images",
        description="批量分析多张图片：逐图返回结果 + 跨图对比汇总。"
        "何时用：一次任务涉及多张图（多张截图对比、一组 UI 稿统一评审、短系列图读懂）。"
        "单张图用 describe_image 更省。",
        inputSchema={
            "type": "object",
            "properties": {
                "image_sources": {"type": "array", "items": {"type": "string"}, "description": "多张图片来源（本地路径 / URL / data URI）。"},
                "prompt": {"type": "string", "description": "应用于每张图的统一提示词，可选。默认使用详细描述提示词。"},
                "model": {"type": "string", "description": "可选模型名称覆盖。"},
            },
            "required": ["image_sources"],
        },
    ),
]

# 六个工具都是「只读分析」：不写任何状态、可安全重试，但会出网访问第三方后端。
# title 与 annotations 集中在这一处声明，避免六个字面量各写一遍还漏。
_READ_ONLY_TOOL = ToolAnnotations(
    readOnlyHint=True, idempotentHint=True, openWorldHint=True
)
_TOOL_TITLES = {
    "describe_image": "描述图片内容",
    "extract_text": "提取图片文字（OCR）",
    "ask_about_image": "看图回答问题",
    "analyze_layout": "UI 布局结构化分析",
    "extract_table": "表格转 Markdown",
    "analyze_images": "批量分析多张图片",
}

_TOOLS: list[Tool] = [
    tool.model_copy(
        update={"title": _TOOL_TITLES[tool.name], "annotations": _READ_ONLY_TOOL}
    )
    for tool in _BASE_TOOLS
]


async def list_tools(
    ctx: ServerRequestContext, params: PaginatedRequestParams | None
) -> ListToolsResult:
    """返回 OpenEye 暴露的工具定义。"""
    return ListToolsResult(tools=_TOOLS)


# 工具名 → 实现。入参校验清单（required / 允许的键 / enum）全部来自下面
# _TOOLS 的 inputSchema，因此新增工具或调整参数只需维护 _TOOLS 一处。
_HANDLERS: dict[str, Callable[..., Awaitable[list[TextContent]]]] = {
    "describe_image": describe_image,
    "extract_text": extract_text,
    "ask_about_image": ask_about_image,
    "analyze_layout": analyze_layout,
    "extract_table": extract_table,
    "analyze_images": analyze_images,
}

_TOOL_SCHEMAS: dict[str, dict] = {tool.name: tool.input_schema for tool in _TOOLS}

# 图片参数可能是数 MB 的 data URI，日志里只记来源类型与长度
_IMAGE_ARGS = frozenset({"image_source", "image_sources"})


def _source_kind(source: str) -> str:
    if source.startswith("data:"):
        return "data-uri"
    if source.startswith(("http://", "https://")):
        return "url"
    return "path"


def _argument_summary(arguments: dict) -> str:
    """把入参压成一行可安全写入日志的摘要（不落用户图片与完整提示词）。"""
    parts: list[str] = []
    for key in sorted(arguments):
        value = arguments[key]
        if key in _IMAGE_ARGS:
            items = value if isinstance(value, list) else [value]
            kinds = ",".join(_source_kind(str(item)) for item in items[:3])
            parts.append(f"{key}[{len(items)}]<{kinds}>")
        else:
            parts.append(f"{key}={str(value)[:80]}")
    return " ".join(parts)


def _invalid(message: str) -> CallToolResult:
    """入参不合法走 isError，让 agent 拿到可自我纠正的提示而非协议错误。"""
    return CallToolResult(
        content=[TextContent(type="text", text=message)], is_error=True
    )


def _validate_arguments(name: str, arguments: dict) -> CallToolResult | None:
    """按该工具的 inputSchema 校验入参，合法返回 ``None``，否则返回 isError 结果。"""
    schema = _TOOL_SCHEMAS.get(name)
    if schema is None:
        return _invalid(
            f"未知工具: {name}。可用工具：{', '.join(_TOOL_SCHEMAS)}。"
        )
    properties: dict = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in arguments:
            return _invalid(
                f"工具 {name} 缺少必填参数 {key}。"
                f"{properties.get(key, {}).get('description', '')}"
            )
    if unknown := [key for key in arguments if key not in properties]:
        return _invalid(
            f"工具 {name} 收到不支持的参数 {unknown}，仅支持：{list(properties)}。"
        )
    for key, prop in properties.items():
        enum = prop.get("enum")
        if enum and arguments.get(key) is not None and arguments[key] not in enum:
            return _invalid(
                f"{key} 参数非法: {arguments[key]!r}，仅支持 {' / '.join(enum)}"
            )
    return None


async def call_tool(
    ctx: ServerRequestContext, params: CallToolRequestParams
) -> CallToolResult:
    """校验并分发工具调用到对应实现。

    工具自身失败与入参不合法都经 ``is_error=True`` 返回，不向协议层抛异常。
    """
    name = params.name
    # 显式 null 的可选参数等同于「不传」：否则 None 会盖掉工具函数的默认值
    arguments: dict = {
        key: value
        for key, value in (params.arguments or {}).items()
        if value is not None
    }

    validation_error = _validate_arguments(name, arguments)
    if validation_error is not None:
        return validation_error
    logger.debug("call_tool {} {}", name, _argument_summary(arguments))

    deadline = settings.request_deadline
    reporter = _build_reporter(ctx, _progress_token(params))
    try:
        # 总时间预算：外层重试 × 降级请求 × 内层重试会把最坏耗时相乘到几十分钟，
        # 超过客户端自己的超时后结果就没人要了 —— 到点主动中止并报清楚
        async with asyncio.timeout(deadline if deadline > 0 else None):
            with budget(deadline):
                async with progress_scope(reporter):
                    # 只转发客户端实际给出的键，缺省项由工具函数自己的默认值补全
                    content: list[TextContent] = await _HANDLERS[name](**arguments)
    except TimeoutError:
        return _invalid(
            f"工具 {name} 超过总时间预算 {deadline:.0f}s 已中止。"
            "可增大 REQUEST_DEADLINE / REQUEST_TIMEOUT，或把批量任务拆小。"
        )
    except VisionError as exc:
        # 工具失败统一置 isError=True，让 agent 能区分正常结果与失败
        logger.warning("工具 {} 失败 category={}", name, exc.category)
        return CallToolResult(
            content=[TextContent(type="text", text=str(exc))],
            is_error=True,
        )

    return CallToolResult(content=list(content))


def _progress_token(params: CallToolRequestParams) -> str | int | None:
    """取客户端为本次调用带的 progressToken（没带就返回 None）。"""
    meta = getattr(params, "meta", None)
    if meta is None:
        return None
    if isinstance(meta, dict):
        return meta.get("progressToken", meta.get("progress_token"))
    # mcp 会把 ``_meta`` 解析成模型，字段名同时存在两种写法
    return getattr(meta, "progress_token", None) or getattr(meta, "progressToken", None)


def _build_reporter(ctx: ServerRequestContext | None, token: str | int | None):
    """构造本次调用的进度上报函数；无 token 或无会话时返回 ``None``（no-op）。"""
    if ctx is None or token is None or getattr(ctx, "session", None) is None:
        return None
    counters = iter(itertools.count(1))

    async def _report(message: str) -> None:
        try:
            await ctx.session.send_progress_notification(
                progress_token=token,
                progress=float(next(counters)),
                message=message,
            )
        except Exception as exc:  # 客户端断开等：进度只是附加信息，不该影响结果
            logger.debug("progress 通知发送失败：{}", exc)

    return _report


OPENEYE_INSTRUCTIONS = (
    "OpenEye：把图片变成可用信息。识图工具组，图片来源支持三种形式——本地绝对路径、"
    "http(s) 公网 URL、data:image/...;base64,... data URI。\n"
    "按任务选工具：\n"
    "- 理解图片讲了什么（整体内容/画面/风格/布局）→ describe_image\n"
    "- 只要照抄/提取文字（OCR：报错、票据、笔记）→ extract_text\n"
    "- 针对图定向回答问题（数值、步骤、判断）→ ask_about_image；通用描述不适合\n"
    "- 前端复刻/还原 UI 结构 → analyze_layout（详细 JSON 元素+坐标+样式）\n"
    "- 图里有表格要结构化数据 → extract_table（Markdown + 复杂表格 JSON）\n"
    "- 一次多张图（对比评审、一组截图）→ analyze_images；单张优先单图工具\n"
    "纪律：能用 OCR 别让模型看图说话；能用 question 别大段描述；"
    "多图任务优先批量工具避免重复调用；图片来源优先用本地路径（少上传、快）。"
)


server = Server(
    "openeye",
    version=__version__,
    instructions=OPENEYE_INSTRUCTIONS,
    on_list_tools=list_tools,
    on_call_tool=call_tool,
)


def _configure_logging() -> None:
    """按 ``LOG_LEVEL`` 把日志接到 stderr。

    loguru 的默认 sink 级别是 DEBUG：会把每次工具调用的入参摘要、每次重试
    全部倒进 stderr。stdio 服务的 stderr 由客户端收集，量级过大既刷屏也拖慢
    管道，因此按配置收窄级别。
    """
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)


async def main() -> None:
    """启动 stdio MCP Server。"""
    _configure_logging()
    logger.info("启动 OpenEye MCP Server v{}", __version__)
    init_options = server.create_initialization_options(
        notification_options=NotificationOptions()
    )
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, init_options)
    finally:
        await aclose_client()


def run() -> None:
    """同步入口 wrapper（供 console_scripts 使用）。

    ``main`` 是 ``async def``，setuptools 生成的 exe 执行
    ``sys.exit(main())`` 只创建 coroutine 不会 await，进程秒退。
    本 wrapper 通过 ``asyncio.run`` 正常驱动事件循环。
    同时在 Windows 下强制 stdout/stderr 使用 UTF-8，避免中文乱码。
    """
    import sys

    if sys.platform == "win32":
        for stream_name in ("stdout", "stderr"):
            stream = getattr(sys, stream_name, None)
            if stream is not None and hasattr(stream, "reconfigure"):
                with contextlib.suppress(Exception):
                    stream.reconfigure(encoding="utf-8")

    asyncio.run(main())


if __name__ == "__main__":
    run()
