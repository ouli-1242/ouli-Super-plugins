"""DeepEye MCP Server 组装。

通过 ``mcp`` 官方库的 ``stdio_server`` 启动 MCP Server，注册
``list_tools`` 与 ``call_tool`` 处理器，Server 名称为 ``deepeye``。

注意：本实现适配 ``mcp>=2.0.0`` 的 API：使用构造器注册
``on_list_tools`` / ``on_call_tool`` 处理器（而非旧版装饰器），handler
返回 ``ListToolsResult`` / ``CallToolResult``。
"""

from __future__ import annotations

import asyncio

from loguru import logger

from mcp.server import NotificationOptions, Server
from mcp.server.context import ServerRequestContext
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from deepeye_mcp import __version__
from deepeye_mcp.errors import VisionError
from deepeye_mcp.tools import (
    analyze_images,
    analyze_layout,
    ask_about_image,
    describe_image,
    extract_table,
    extract_text,
)

_TOOLS: list[Tool] = [
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


async def list_tools(
    ctx: ServerRequestContext, params: PaginatedRequestParams | None
) -> ListToolsResult:
    """返回 DeepEye 暴露的工具定义。"""
    return ListToolsResult(tools=_TOOLS)


async def call_tool(
    ctx: ServerRequestContext, params: CallToolRequestParams
) -> CallToolResult:
    """分发工具调用到对应实现。

    Raises:
        ValueError: 未知工具名时抛出。
    """
    name = params.name
    arguments: dict = params.arguments or {}
    logger.debug("call_tool name={} arguments={}", name, arguments)

    try:
        if name == "describe_image":
            describe_kwargs: dict = {"image_source": arguments["image_source"]}
            if arguments.get("prompt"):
                describe_kwargs["prompt"] = arguments["prompt"]
            if arguments.get("model"):
                describe_kwargs["model"] = arguments["model"]
            content: list[TextContent] = await describe_image(**describe_kwargs)
        elif name == "extract_text":
            content = await extract_text(
                image_source=arguments["image_source"],
                language=arguments.get("language", "auto"),
            )
        elif name == "ask_about_image":
            content = await ask_about_image(
                image_source=arguments["image_source"],
                question=arguments["question"],
            )
        elif name == "analyze_layout":
            # server 层枚举校验：detail 只接受 basic / detailed
            detail = arguments.get("detail", "basic")
            if detail not in ("basic", "detailed"):
                return CallToolResult(
                    content=[TextContent(type="text", text=f"detail 参数非法: {detail!r}，仅支持 basic / detailed")],
                    is_error=True,
                )
            content = await analyze_layout(**arguments)
        elif name == "extract_table":
            content = await extract_table(
                image_source=arguments["image_source"],
                model=arguments.get("model"),
            )
        elif name == "analyze_images":
            if not arguments.get("image_sources"):
                return CallToolResult(
                    content=[TextContent(type="text", text="错误：image_sources 数组不能为空")],
                    is_error=True,
                )
            content = await analyze_images(
                image_sources=arguments["image_sources"],
                prompt=arguments.get("prompt"),
                model=arguments.get("model"),
            )
        else:
            raise ValueError(f"未知工具: {name}")
    except VisionError as exc:
        # 工具失败统一置 isError=True，让 agent 能区分正常结果与失败
        return CallToolResult(
            content=[TextContent(type="text", text=str(exc))],
            is_error=True,
        )

    return CallToolResult(content=content)


DEEPEYE_INSTRUCTIONS = (
    "DeepEye：把图片变成可用信息。识图工具组，图片来源支持三种形式——本地绝对路径、"
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
    "deepeye",
    version=__version__,
    instructions=DEEPEYE_INSTRUCTIONS,
    on_list_tools=list_tools,
    on_call_tool=call_tool,
)


async def main() -> None:
    """启动 stdio MCP Server。"""
    logger.info("启动 DeepEye MCP Server v{}", __version__)
    init_options = server.create_initialization_options(
        notification_options=NotificationOptions()
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_options)


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
                try:
                    stream.reconfigure(encoding="utf-8")
                except Exception:
                    pass

    asyncio.run(main())


if __name__ == "__main__":
    run()
