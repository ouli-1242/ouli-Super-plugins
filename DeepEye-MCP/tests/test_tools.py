"""``deepeye_mcp.tools`` MCP 工具函数单元测试。

通过 ``unittest.mock.patch`` 替换 ``deepeye_mcp.tools.create_vision_adapter``，
避免任何真实 API 调用；使用 data URI 作为图像源，避免本地文件/网络 IO。
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import TextContent

from deepeye_mcp.cache import vision_cache
from deepeye_mcp.config import settings
from deepeye_mcp.errors import VisionError
from deepeye_mcp.tools import (
    _DEFAULT_DESCRIBE_PROMPT,
    _OCR_PROMPT,
    analyze_images,
    analyze_layout,
    ask_about_image,
    describe_image,
    extract_table,
    extract_text,
)

_DATA_URI = "data:image/png;base64,iVBOR"


def _build_mock_adapter(return_value: str = "mocked description") -> MagicMock:
    """构造一个 mock 适配器，其 ``describe`` 是 AsyncMock 返回固定字符串。"""
    adapter = MagicMock()
    adapter.describe = AsyncMock(return_value=return_value)
    return adapter


# ---------------------------------------------------------------------------
# describe_image
# ---------------------------------------------------------------------------


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_describe_image_default_prompt(mock_factory):
    mock_adapter = _build_mock_adapter()
    mock_factory.return_value = mock_adapter

    result = await describe_image(image_source=_DATA_URI)

    mock_adapter.describe.assert_awaited_once()
    call = mock_adapter.describe.await_args
    # describe(b64_data, mime_type, prompt)
    assert call.args[0] == "iVBOR"
    assert call.args[1] == "image/png"
    assert call.args[2] == _DEFAULT_DESCRIBE_PROMPT

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], TextContent)
    assert "mocked description" in result[0].text


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_describe_image_custom_prompt(mock_factory):
    mock_adapter = _build_mock_adapter()
    mock_factory.return_value = mock_adapter

    await describe_image(
        image_source=_DATA_URI,
        prompt="描述图表数据趋势",
    )

    call = mock_adapter.describe.await_args
    assert call.args[2] == "描述图表数据趋势"


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_describe_image_custom_model(mock_factory):
    """model 参数应透传给工厂函数。"""
    mock_adapter = _build_mock_adapter()
    mock_factory.return_value = mock_adapter

    await describe_image(image_source=_DATA_URI, model="gpt-4o-mini")

    mock_factory.assert_called_once_with("gpt-4o-mini", provider=None)


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_describe_image_result_format(mock_factory):
    mock_adapter = _build_mock_adapter(return_value="hello world")
    mock_factory.return_value = mock_adapter

    result = await describe_image(image_source=_DATA_URI)

    assert result[0].text == "图片分析结果：\nhello world"


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_extract_text_default_no_language_hint(mock_factory):
    mock_adapter = _build_mock_adapter()
    mock_factory.return_value = mock_adapter

    result = await extract_text(image_source=_DATA_URI)

    call = mock_adapter.describe.await_args
    assert call.args[2] == _OCR_PROMPT  # 不附加语言提示

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], TextContent)
    assert result[0].text == "mocked description"


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_extract_text_with_language_zh(mock_factory):
    mock_adapter = _build_mock_adapter()
    mock_factory.return_value = mock_adapter

    await extract_text(image_source=_DATA_URI, language="zh")

    call = mock_adapter.describe.await_args
    assert call.args[2] == _OCR_PROMPT + " 优先识别语言：zh"


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_extract_text_with_language_en(mock_factory):
    mock_adapter = _build_mock_adapter()
    mock_factory.return_value = mock_adapter

    await extract_text(image_source=_DATA_URI, language="en")

    call = mock_adapter.describe.await_args
    assert call.args[2] == _OCR_PROMPT + " 优先识别语言：en"


# ---------------------------------------------------------------------------
# ask_about_image
# ---------------------------------------------------------------------------


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_ask_about_image_prompt_assembly(mock_factory):
    mock_adapter = _build_mock_adapter()
    mock_factory.return_value = mock_adapter

    result = await ask_about_image(
        image_source=_DATA_URI,
        question="图中有几只猫？",
    )

    call = mock_adapter.describe.await_args
    assert call.args[2] == "根据图片回答：图中有几只猫？"

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], TextContent)
    assert result[0].text == "mocked description"


# ---------------------------------------------------------------------------
# 缓存集成（cache_enabled=True 时第二次相同调用不触发适配器）
# ---------------------------------------------------------------------------


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_cache_enabled_second_call_hits_cache(mock_factory, monkeypatch):
    """开启缓存后，第二次相同调用应命中缓存，不再次调用适配器。"""
    monkeypatch.setattr(settings, "cache_enabled", True)
    vision_cache.clear()  # 确保起始状态干净

    mock_adapter = _build_mock_adapter(return_value="first-result")
    mock_factory.return_value = mock_adapter

    # 第一次调用：未命中缓存，调用适配器
    result1 = await describe_image(image_source=_DATA_URI)
    assert mock_adapter.describe.await_count == 1
    assert "first-result" in result1[0].text

    # 第二次相同调用：应命中缓存，适配器不再被调用
    result2 = await describe_image(image_source=_DATA_URI)
    assert mock_adapter.describe.await_count == 1  # 仍为 1，未新增调用
    assert "first-result" in result2[0].text

    # 清理：恢复缓存状态
    vision_cache.clear()


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_cache_disabled_calls_adapter_each_time(mock_factory, monkeypatch):
    """关闭缓存时，每次调用都应触发适配器。"""
    monkeypatch.setattr(settings, "cache_enabled", False)
    vision_cache.clear()

    mock_adapter = _build_mock_adapter(return_value="result")
    mock_factory.return_value = mock_adapter

    await describe_image(image_source=_DATA_URI)
    await describe_image(image_source=_DATA_URI)

    assert mock_adapter.describe.await_count == 2

    vision_cache.clear()


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_cache_different_prompt_does_not_hit(mock_factory, monkeypatch):
    """相同图片但不同 prompt 应产生不同 key，缓存不命中。"""
    monkeypatch.setattr(settings, "cache_enabled", True)
    vision_cache.clear()

    mock_adapter = _build_mock_adapter(return_value="cached-desc")
    mock_factory.return_value = mock_adapter

    await describe_image(image_source=_DATA_URI, prompt="描述A")
    await describe_image(image_source=_DATA_URI, prompt="描述B")

    # 两次不同 prompt，应调用适配器两次
    assert mock_adapter.describe.await_count == 2

    vision_cache.clear()


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_cache_returns_cached_text_directly(mock_factory, monkeypatch):
    """缓存命中时应直接返回缓存文本（未经适配器重新生成）。"""
    monkeypatch.setattr(settings, "cache_enabled", True)
    vision_cache.clear()

    # 第一次调用返回 "v1"
    mock_adapter = _build_mock_adapter(return_value="v1")
    mock_factory.return_value = mock_adapter
    await describe_image(image_source=_DATA_URI)

    # 切换 mock 返回 "v2"，但缓存命中时不应调用，结果仍是 "v1"
    mock_adapter2 = _build_mock_adapter(return_value="v2")
    mock_factory.return_value = mock_adapter2

    result = await describe_image(image_source=_DATA_URI)
    assert "v1" in result[0].text
    assert mock_adapter2.describe.await_count == 0

    vision_cache.clear()


# ---------------------------------------------------------------------------
# analyze_layout
# ---------------------------------------------------------------------------


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_analyze_layout_basic(mock_factory):
    """basic 模式：mock 返回纯 JSON，验证返回 list[TextContent] 且 text 是 JSON 字符串。"""
    mock_adapter = _build_mock_adapter(
        return_value='{"layout_type":"header-nav","summary":"test","elements":[]}'
    )
    mock_factory.return_value = mock_adapter

    result = await analyze_layout(image_source=_DATA_URI)

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], TextContent)
    # text 应为合法 JSON 字符串，可被解析
    parsed = json.loads(result[0].text)
    assert parsed["layout_type"] == "header-nav"
    assert parsed["summary"] == "test"
    assert parsed["elements"] == []


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_analyze_layout_detailed(mock_factory):
    """detailed 模式：mock 返回含 styles 的 JSON，验证 prompt 中包含样式相关指令。"""
    mock_adapter = _build_mock_adapter(
        return_value=(
            '{"layout_type":"nav","summary":"s","elements":['
            '{"type":"button","text":"btn",'
            '"position":{"x":0,"y":0,"width":10,"height":5},'
            '"styles":{"background_color":"#fff"}}]}'
        )
    )
    mock_factory.return_value = mock_adapter

    result = await analyze_layout(image_source=_DATA_URI, detail="detailed")

    # 验证 prompt 中包含样式相关指令
    call = mock_adapter.describe.await_args
    prompt = call.args[2]
    assert "styles" in prompt or "颜色" in prompt or "color" in prompt
    # 结果应为合法 JSON，且保留 styles 字段
    assert isinstance(result, list)
    assert len(result) == 1
    parsed = json.loads(result[0].text)
    assert parsed["elements"][0]["styles"]["background_color"] == "#fff"


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_analyze_layout_json_with_text(mock_factory):
    """模型返回 "说明文字 + JSON" 时应能提取出 JSON。"""
    mock_adapter = _build_mock_adapter(
        return_value='这是结果：\n{"layout_type":"nav"}'
    )
    mock_factory.return_value = mock_adapter

    result = await analyze_layout(image_source=_DATA_URI)

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], TextContent)
    # text 应为合法 JSON 字符串，可被解析
    parsed = json.loads(result[0].text)
    assert parsed["layout_type"] == "nav"


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_analyze_layout_no_json(mock_factory):
    """模型未返回 JSON 时应抛 VisionError（含 "未返回有效 JSON" 文案）。"""
    mock_adapter = _build_mock_adapter(return_value="我无法分析")
    mock_factory.return_value = mock_adapter

    with pytest.raises(VisionError, match="未返回有效 JSON"):
        await analyze_layout(image_source=_DATA_URI)


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_analyze_layout_exception(mock_factory):
    """适配器抛异常时应抛 VisionError（含 "布局分析失败" 文案）。"""
    mock_adapter = MagicMock()
    mock_adapter.describe = AsyncMock(side_effect=RuntimeError("adapter boom"))
    mock_factory.return_value = mock_adapter

    with pytest.raises(VisionError, match="布局分析失败"):
        await analyze_layout(image_source=_DATA_URI)


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_analyze_layout_prompt_basic(mock_factory):
    """basic 模式 prompt 不应包含样式相关字段（styles / color）。"""
    mock_adapter = _build_mock_adapter(
        return_value='{"layout_type": "x", "summary": "s", "elements": []}'
    )
    mock_factory.return_value = mock_adapter

    await analyze_layout(image_source=_DATA_URI, detail="basic")

    call = mock_adapter.describe.await_args
    prompt = call.args[2]
    assert "styles" not in prompt
    assert "color" not in prompt


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_analyze_layout_prompt_detailed(mock_factory):
    """detailed 模式 prompt 应包含样式相关字段（styles / color）。"""
    mock_adapter = _build_mock_adapter(
        return_value='{"layout_type": "x", "summary": "s", "elements": []}'
    )
    mock_factory.return_value = mock_adapter

    await analyze_layout(image_source=_DATA_URI, detail="detailed")

    call = mock_adapter.describe.await_args
    prompt = call.args[2]
    assert "styles" in prompt or "color" in prompt


# ---------------------------------------------------------------------------
# 错误分类接入
# ---------------------------------------------------------------------------


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_describe_image_config_error_classified(mock_factory):
    """配置缺失类错误应抛 VisionError 并含「配置错误」提示。"""
    mock_adapter = MagicMock()
    mock_adapter.describe = AsyncMock(
        side_effect=ValueError("ANTHROPIC_API_KEY 未配置：使用 anthropic 视觉后端必须设置 ANTHROPIC_API_KEY")
    )
    mock_factory.return_value = mock_adapter

    with pytest.raises(VisionError, match="配置错误"):
        await describe_image(image_source=_DATA_URI)


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_analyze_layout_backend_error_has_status(mock_factory):
    """后端 429 错误应抛含限流提示的 VisionError。"""
    import httpx

    request = httpx.Request("POST", "https://example.com/v1/chat/completions")
    response = httpx.Response(429, request=request)
    mock_adapter = MagicMock()
    mock_adapter.describe = AsyncMock(
        side_effect=httpx.HTTPStatusError("限流", request=request, response=response)
    )
    mock_factory.return_value = mock_adapter

    with pytest.raises(VisionError, match="429"):
        await analyze_layout(image_source=_DATA_URI)


# ---------------------------------------------------------------------------
# extract_table
# ---------------------------------------------------------------------------


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_extract_table_returns_markdown(mock_factory):
    mock_adapter = _build_mock_adapter(
        return_value='{"columns":2,"title":"t","rows":['
        '{"cells":[{"text":"n","rowspan":1,"colspan":1},{"text":"p"}]},'
        '{"cells":[{"text":"a","rowspan":1,"colspan":1},{"text":"1"}]}]}'
    )
    mock_factory.return_value = mock_adapter

    result = await extract_table(image_source=_DATA_URI)

    assert "| n | p |" in result[0].text
    assert "| a | 1 |" in result[0].text


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_extract_table_merged_appends_json(mock_factory):
    mock_adapter = _build_mock_adapter(
        return_value='{"columns":1,"title":"","rows":['
        '{"cells":[{"text":"A","rowspan":2,"colspan":1}]},'
        '{"cells":[{"text":"B","rowspan":1,"colspan":1}]}]}'
    )
    mock_factory.return_value = mock_adapter

    result = await extract_table(image_source=_DATA_URI)

    assert "```json" in result[0].text
    assert '"rowspan": 2' in result[0].text


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_extract_table_invalid_json_degraded(mock_factory):
    mock_adapter = _build_mock_adapter(return_value="无法识别")
    mock_factory.return_value = mock_adapter

    with pytest.raises(VisionError, match="表格提取失败"):
        await extract_table(image_source=_DATA_URI)


# ---------------------------------------------------------------------------
# analyze_images
# ---------------------------------------------------------------------------


@patch("deepeye_mcp.tools.parse_image_source")
@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_analyze_images_two_images(mock_factory, mock_parse):
    """两张图并发：逐图结果 + 一次纯文本汇总。"""
    mock_parse.return_value = ("iVBOR", "image/png")
    adapter = _build_mock_adapter(return_value="图像描述A")
    adapter.describe_text = AsyncMock(return_value="对比总结")
    mock_factory.return_value = adapter

    result = await analyze_images(image_sources=["a.png", "b.png"])

    text = result[0].text
    assert "[1] a.png: 图像描述A" in text
    assert "[2] b.png: 图像描述A" in text
    assert "【跨图汇总】" in text
    assert "对比总结" in text
    # 两条逐图 + 一条汇总，共 3 次模型调用
    assert adapter.describe.await_count == 2
    adapter.describe_text.assert_awaited_once()


@patch("deepeye_mcp.tools.parse_image_source")
@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_analyze_images_isolated_failure(mock_factory, mock_parse):
    """单张失败不阻塞整体，返回分类后的占位文本。"""
    mock_parse.return_value = ("iVBOR", "image/png")
    adapter = MagicMock()
    adapter.describe = AsyncMock(side_effect=[RuntimeError("boom"), "ok"])
    adapter.describe_text = AsyncMock(return_value="汇总")
    mock_factory.return_value = adapter

    result = await analyze_images(image_sources=["bad.png", "good.png"])

    text = result[0].text
    assert "boom" in text  # unknown 分类保留原始异常
    assert "[2] good.png: ok" in text
    assert "汇总" in text


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_analyze_images_empty_list(mock_factory):
    mock_factory.return_value = _build_mock_adapter()

    with pytest.raises(VisionError, match="不能为空"):
        await analyze_images(image_sources=[])
    mock_factory.assert_not_called()


# ---------------------------------------------------------------------------
# server 注册
# ---------------------------------------------------------------------------


def test_server_tools_registered():
    """server 应注册 extract_table 与 analyze_images。"""
    from deepeye_mcp.server import _TOOLS

    names = {t.name for t in _TOOLS}
    assert "extract_table" in names
    assert "analyze_images" in names
