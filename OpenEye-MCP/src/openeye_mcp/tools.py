"""OpenEye MCP 工具实现。

六个工具均返回 ``list[TextContent]``：
- :func:`describe_image`：图像描述
- :func:`extract_text`：OCR 文字提取
- :func:`ask_about_image`：视觉问答
- :func:`analyze_layout`：UI 布局结构化分析（返回 JSON）
- :func:`extract_table`：表格提取为 Markdown（复杂表格附带 JSON）
- :func:`analyze_images`：批量分析多张图片 + 跨图对比

调用链分两段，各自有独立缓存：

``image_source`` → :func:`_prepare`（解析 + 预处理 + 摘要，按来源缓存）
                 → :func:`_invoke`（查/写视觉结果缓存 → 调适配器）

分成两段的原因：布局与表格要带 ``use_cache=False`` 反复请求模型（输出不
稳定），若解析预处理留在请求函数里，同一张图会被下载并解码若干次。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path

import httpx
from mcp.types import TextContent

from openeye_mcp.budget import has_budget_for
from openeye_mcp.cache import (
    PreparedImage,
    prepared_image_cache,
    source_fingerprint,
    vision_cache,
)
from openeye_mcp.config import settings
from openeye_mcp.errors import VisionError, classify_error
from openeye_mcp.image_utils import parse_image_source, preprocess_image
from openeye_mcp.progress import report
from openeye_mcp.table import TABLE_JSON_PROMPT, has_merged_cells, json_to_markdown
from openeye_mcp.vision import create_vision_adapter, normalize_provider

_DEFAULT_DESCRIBE_PROMPT = (
    "分析这张图片，按以下维度分点描述：\n"
    "1. 布局结构：各元素的位置关系和层级\n"
    "2. 主要元素：具体列出每个元素及其文字内容\n"
    "3. 颜色与样式：背景色、文字色、关键配色\n"
    "4. 潜在问题：如有遮挡、重叠、对齐异常、内容缺失等"
)
_OCR_PROMPT = "提取图片中所有文字，保持排版，不加描述。"

# 布局分析 basic 模式提示词：只要求类型 + 文本 + 位置
_LAYOUT_BASIC_PROMPT = """分析这张 UI 截图的布局结构，返回 JSON。只返回 JSON，不加任何说明文字。
JSON 格式：
{"layout_type": "布局类型", "summary": "一句话描述", "elements": [{"type": "元素类型", "text": "文本内容", "position": {"x": 0, "y": 0, "width": 0, "height": 0}, "children": []}]}
位置坐标用百分比 0-100。元素类型：nav/button/text/image/input/link/icon/card/container/list。"""

# detailed 模式：在 basic 基础上额外要求样式信息
_LAYOUT_DETAILED_EXTRA = """
额外为元素返回 styles 字段：{"background_color": "#hex", "text_color": "#hex", "font_size": "14px", "border_radius": "8px", "padding": "12px"}。"""

# 模型输出不稳定，偶发不返回 JSON 时的请求轮数
_JSON_RETRIES = 3
# 布局 / 表格的 JSON 较大，单独放宽输出上限，防止结果被截断
_JSON_MAX_TOKENS = 8192
# 后端明确拒绝某个请求参数时的状态码；只有这两种才值得去掉参数重试一次
_UNSUPPORTED_PARAM_STATUS = frozenset({400, 422})

# analyze_images 并发上限：限制同时进行的图片下载 + 视觉请求数，防止内存/连接峰值
_ANALYZE_IMAGES_CONCURRENCY = 4


def _as_vision_error(prefix: str, exc: Exception, provider: str = "") -> VisionError:
    """把底层异常翻译成面向用户的 :class:`VisionError`（并带上错误分类）。"""
    category, message = classify_error(exc, provider or normalize_provider())
    return VisionError(f"{prefix}：{message}", category=category)


async def _prepare(image_source: str) -> PreparedImage:
    """解析并预处理图片，返回带摘要的 :class:`PreparedImage`。

    同一来源（本地文件按 mtime+size、URL 按地址、data URI 按内容）在
    ``IMAGE_CACHE_TTL`` 内只解析一次；Pillow 处理放线程里执行，避免阻塞
    stdio 的事件循环。
    """
    fingerprint = source_fingerprint(image_source)
    cached = prepared_image_cache.get(fingerprint)
    if cached is not None:
        return cached

    b64_data, mime_type = await parse_image_source(image_source)
    # 图片预处理（缩放 + 转 JPEG），失败时原样返回不阻断
    b64_data, mime_type = await asyncio.to_thread(preprocess_image, b64_data, mime_type)
    prepared = PreparedImage(
        b64=b64_data,
        mime=mime_type,
        # 用处理后的字节算摘要，作为视觉结果缓存 key 的一部分
        digest=hashlib.sha256(b64_data.encode()).hexdigest(),
    )
    prepared_image_cache.set(fingerprint, prepared)
    return prepared


def _cache_variant(adapter: object, options: dict) -> str:
    """拼出视觉缓存的参数指纹（JSON 串，字段顺序稳定）。

    指纹必须含「实际后端 + 端点 + 真实模型 + 全部影响输出的生成参数」：
    只按 (图片, 提示词, 请求里的 model) 缓存时，切换 ``VISION_PROVIDER`` /
    ``OCR_BACKEND``、或改动 ``OPENAI_MODEL`` / ``OPENAI_BASE_URL`` /
    生成参数后，会在 TTL 内命中旧后端旧模型的旧结果。
    """
    payload = {
        "provider": options["provider"],
        "model": str(getattr(adapter, "model", "")),
        "base_url": str(getattr(adapter, "base_url", "")),
        "max_tokens": options["max_tokens"],
        "reasoning_effort": options["reasoning_effort"],
        "response_format": options["response_format"] or {},
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


async def _invoke(
    prepared: PreparedImage,
    prompt: str,
    *,
    model: str | None = None,
    use_cache: bool = True,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    response_format: dict | None = None,
    provider: str | None = None,
) -> str:
    """对已准备好的图片发起一次视觉请求（含结果缓存读写）。

    Args:
        prepared: :func:`_prepare` 的输出。
        prompt: 提示词。
        model: 可选模型名称覆盖。
        use_cache: 是否读写结果缓存；False 时每次真调后端（用于输出不稳定、
            需重试的场景）。
        max_tokens: 输出 token 上限覆盖；None 时用配置默认值。
        reasoning_effort: 推理深度覆盖；None 时用配置默认。
        response_format: 输出格式约束（如 ``{"type": "json_object"}``）。
        provider: 视觉后端覆盖（如 OCR 单独指定）；None 用默认。

    Returns:
        视觉模型返回的文本。
    """
    effective_provider = normalize_provider(provider)
    # 适配器只是构造对象（不发请求），提前建好才能拿到真实模型与端点做指纹
    adapter = create_vision_adapter(model, provider=effective_provider)
    variant = _cache_variant(
        adapter,
        {
            "provider": effective_provider,
            "max_tokens": max_tokens,
            "reasoning_effort": reasoning_effort,
            "response_format": response_format,
        },
    )
    caching = settings.cache_enabled and use_cache

    if caching:
        cached = vision_cache.get(prepared.digest, prompt, adapter.model, variant)
        if cached is not None:
            return cached

    # 真正要发请求了才上报：命中缓存的调用没有等待方需要被安慰
    await report(f"调用视觉后端 {effective_provider} / {adapter.model}")
    text = await adapter.describe(
        prepared.b64,
        prepared.mime,
        prompt,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        response_format=response_format,
    )

    # 写入缓存供下次复用；空结果不缓存，避免污染
    if caching and text:
        vision_cache.set(prepared.digest, prompt, adapter.model, text, variant)
    return text


async def _run_vision(
    image_source: str,
    prompt: str,
    model: str | None = None,
    use_cache: bool = True,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    response_format: dict | None = None,
    provider: str | None = None,
) -> str:
    """``_prepare`` + ``_invoke`` 的便捷组合（单图工具走这里）。"""
    prepared = await _prepare(image_source)
    return await _invoke(
        prepared,
        prompt,
        model=model,
        use_cache=use_cache,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        response_format=response_format,
        provider=provider,
    )


async def describe_image(
    image_source: str,
    prompt: str = _DEFAULT_DESCRIBE_PROMPT,
    model: str | None = None,
) -> list[TextContent]:
    """描述图片内容。

    Args:
        image_source: 图像来源（本地路径 / 公网 URL / Base64 data URI）。
        prompt: 描述提示词，默认使用详细分点描述提示词（布局/元素/配色/问题）。
        model: 可选模型名称覆盖。

    Returns:
        包含图片描述文本的 ``list[TextContent]``。
    """
    try:
        description = await _run_vision(image_source, prompt, model)
        return [TextContent(type="text", text=f"图片分析结果：\n{description}")]
    except VisionError:
        raise
    except Exception as exc:
        raise _as_vision_error("图片分析失败", exc) from exc


async def extract_text(
    image_source: str,
    language: str = "auto",
) -> list[TextContent]:
    """提取图片中的文字（OCR）。

    使用固定 OCR 提示词，强制仅返回文字、保持排版、不加描述。

    Args:
        image_source: 图像来源（本地路径 / 公网 URL / Base64 data URI）。
        language: 识别语言，``"auto"`` 自动识别；其他值会附加语言提示。

    Returns:
        包含提取文字的 ``list[TextContent]``。
    """
    prompt = _OCR_PROMPT
    if language != "auto":
        prompt += f" 优先识别语言：{language}"
    provider = settings.active_ocr_backend
    try:
        text = await _run_vision(image_source, prompt, provider=provider)
        return [TextContent(type="text", text=text)]
    except VisionError:
        raise
    except Exception as exc:
        raise _as_vision_error("OCR 失败", exc, provider) from exc


async def ask_about_image(
    image_source: str,
    question: str,
) -> list[TextContent]:
    """根据图片内容回答问题。

    Args:
        image_source: 图像来源（本地路径 / 公网 URL / Base64 data URI）。
        question: 要回答的问题。

    Returns:
        包含答案的 ``list[TextContent]``。
    """
    prompt = f"根据图片回答：{question}"
    try:
        answer = await _run_vision(image_source, prompt)
        return [TextContent(type="text", text=answer)]
    except VisionError:
        raise
    except Exception as exc:
        raise _as_vision_error("视觉问答失败", exc) from exc


def _extract_json(text: str, require_key: str | None = None) -> str | None:
    """从模型输出中提取「顶层含 ``require_key``」的 JSON 对象。

    模型可能返回"说明文字 + JSON"或把 JSON 包在代码块里。扫描所有合法
    JSON 对象：``require_key`` 非空时只返回含该键的对象（兼容不完整 JSON
    里嵌套元素先被解析到的情况），否则返回第一个合法对象。
    """
    # 去掉 markdown 代码围栏
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            continue
        if require_key is None or (isinstance(obj, dict) and require_key in obj):
            return json.dumps(obj, ensure_ascii=False)
    return None


def _is_unsupported_param(exc: httpx.HTTPStatusError) -> bool:
    """该 4xx 是否像「后端不认识这个参数」，值得去掉参数再试一次。

    只对 400 / 422 降级：401 / 403 / 429 去掉 ``response_format`` 再打一次
    既救不回来，又把真实错误藏进第二条错误里，还白花一次配额。
    """
    return exc.response.status_code in _UNSUPPORTED_PARAM_STATUS


async def _request_json(
    prepared: PreparedImage,
    prompt: str,
    require_key: str,
    model: str | None,
) -> str | None:
    """请求「带图的 JSON 结构化输出」，返回顶层含 ``require_key`` 的 JSON 串。

    布局与表格共用此流程：优先声明 ``json_object``，后端明确不支持该参数时
    降级为普通请求，靠 :func:`_extract_json` 从输出里捞。整体受
    :data:`_JSON_RETRIES` 轮数与 ``REQUEST_DEADLINE`` 总预算双重约束。

    Returns:
        JSON 字符串；多轮都没拿到合法 JSON 时返回 ``None``。
    """
    for attempt in range(_JSON_RETRIES + 1):
        await report(f"{require_key} 结构化请求第 {attempt + 1} 轮")
        try:
            text = await _invoke(
                prepared,
                prompt,
                model=model,
                use_cache=False,
                max_tokens=_JSON_MAX_TOKENS,
                reasoning_effort="low",
                response_format={"type": "json_object"},
            )
        except httpx.HTTPStatusError as exc:
            if not _is_unsupported_param(exc):
                raise
            text = await _invoke(
                prepared,
                prompt,
                model=model,
                use_cache=False,
                max_tokens=_JSON_MAX_TOKENS,
            )
        json_str = _extract_json(text, require_key=require_key)
        if json_str is not None:
            return json_str
        # 剩余预算不足以再走完一轮请求 + 重试，提前收摊（拿不到结果总比烧穿超时好）
        if not has_budget_for(settings.request_timeout):
            break
    return None


async def analyze_layout(
    image_source: str,
    detail: str = "basic",
    model: str | None = None,
) -> list[TextContent]:
    """UI 布局结构化分析：返回 JSON 字符串，包含元素类型、位置坐标、（可选）样式。

    Args:
        image_source: 图像来源（本地路径 / 公网 URL / Base64 data URI）。
        detail: 分析粒度，``"basic"`` 仅返回类型+文本+位置；
            ``"detailed"`` 额外返回颜色、字号、圆角等样式信息。
        model: 可选模型名称覆盖。

    Returns:
        包含 JSON 字符串的 ``list[TextContent]``。

    Raises:
        VisionError: 模型多轮未返回有效 JSON，或请求失败。
    """
    prompt = _LAYOUT_BASIC_PROMPT
    if detail == "detailed":
        prompt += _LAYOUT_DETAILED_EXTRA

    try:
        prepared = await _prepare(image_source)
        json_str = await _request_json(prepared, prompt, "layout_type", model)
        if json_str is None:
            raise VisionError("布局分析失败：模型多次未返回有效 JSON")
        return [TextContent(type="text", text=json_str)]
    except VisionError:
        raise
    except Exception as exc:
        raise _as_vision_error("布局分析失败", exc) from exc


async def extract_table(
    image_source: str,
    model: str | None = None,
) -> list[TextContent]:
    """提取图片中的表格为 Markdown；复杂表格（合并单元格）附带 JSON 结构。

    Args:
        image_source: 图像来源（本地路径 / URL / data URI）。
        model: 可选模型名称覆盖。

    Returns:
        含 Markdown 表格的 ``list[TextContent]``。

    Raises:
        VisionError: 模型多轮未返回有效表格 JSON，或请求失败。
    """
    try:
        prepared = await _prepare(image_source)
        json_str = await _request_json(prepared, TABLE_JSON_PROMPT, "rows", model)
        if json_str is None:
            raise VisionError("表格提取失败：模型多次未返回有效表格 JSON")
        parsed = json.loads(json_str)
        md = json_to_markdown(parsed)
        if has_merged_cells(parsed):
            return [TextContent(
                type="text",
                text=f"{md}\n\n（检测到合并单元格，附 JSON 完整结构）\n```json\n{json_str}\n```",
            )]
        return [TextContent(type="text", text=md)]
    except VisionError:
        raise
    except Exception as exc:
        raise _as_vision_error("表格提取失败", exc) from exc


def _source_name(source: str, index: int) -> str:
    """从 image_source 提取展示名：本地路径取文件名，URL 取末段，data URI 用序号。"""
    if source.startswith(("http://", "https://")):
        return source.rstrip("/").split("/")[-1] or f"图片{index}"
    if source.startswith("data:"):
        return f"图片{index}"
    return Path(source).name


async def analyze_images(
    image_sources: list[str],
    prompt: str = _DEFAULT_DESCRIBE_PROMPT,
    model: str | None = None,
) -> list[TextContent]:
    """批量分析多张图片：逐图结果 + 跨图对比汇总。

    Args:
        image_sources: 多张图片来源（本地路径 / URL / data URI）。
        prompt: 应用于每张图的统一提示词。
        model: 可选模型名称覆盖。

    Returns:
        含逐图结果与汇总的 ``list[TextContent]``。
    """
    if not image_sources:
        raise VisionError("错误：image_sources 数组不能为空")

    provider = normalize_provider()
    # 并发上限：避免 N 张图同时发起 N 个下载+API 请求导致内存/连接峰值不可控
    semaphore = asyncio.Semaphore(_ANALYZE_IMAGES_CONCURRENCY)

    async def _one(source: str) -> str:
        async with semaphore:
            return await _run_vision(source, prompt, model)

    # return_exceptions=True：单图失败不该让整批作废，逐图标注错误即可
    results: list[str | BaseException] = await asyncio.gather(
        *(_one(src) for src in image_sources), return_exceptions=True
    )

    lines: list[str] = []
    for i, (src, result) in enumerate(zip(image_sources, results, strict=True), 1):
        name = _source_name(src, i)
        text = (
            classify_error(result, provider)[1]
            if isinstance(result, BaseException)
            else result
        )
        lines.append(f"[{i}] {name}: {text}")

    per_image_text = "\n\n".join(lines)

    # 汇总：逐图描述作为纯文本发给模型对比（不依赖多图支持）
    summary_prompt = (
        f"以下是同一 prompt 对多张图片的分析结果，请对比这些图片，"
        f"总结彼此的异同点和关键结论。\n\n{per_image_text}"
    )
    try:
        adapter = create_vision_adapter(model)
        summary = await adapter.describe_text(summary_prompt)
    except Exception as exc:
        summary = f"（汇总失败：{classify_error(exc, provider)[1]}）"

    return [TextContent(type="text", text=f"{per_image_text}\n\n【跨图汇总】\n{summary}")]
