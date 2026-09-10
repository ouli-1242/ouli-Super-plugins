"""classify_error 错误分类单元测试。"""
import httpx
import pytest

from deepeye_mcp.errors import classify_error


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com/v1/chat/completions")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError("err", request=request, response=response)


def test_config_missing_base_url():
    exc = ValueError("ANTHROPIC_API_KEY 未配置：使用 anthropic 视觉后端必须设置 ANTHROPIC_API_KEY")
    category, message = classify_error(exc, "anthropic")
    assert category == "config"
    assert "配置错误" in message


def test_config_invalid_provider():
    category, _ = classify_error(ValueError("不支持的视觉后端: 'foo'"))
    assert category == "config"


def test_image_file_not_found():
    category, message = classify_error(FileNotFoundError("图像文件不存在: /x.png"))
    assert category == "image"
    assert "文件不存在" in message


def test_image_ssrf_blocked():
    exc = ValueError("拒绝访问非公网地址（SSRF 防护）: localhost (127.0.0.1)")
    category, message = classify_error(exc)
    assert category == "image"
    assert "SSRF" in message


def test_image_too_large():
    category, message = classify_error(ValueError("图片超过大小上限: 100 > 10 bytes"))
    assert category == "image"
    assert "大小上限" in message


def test_timeout():
    category, message = classify_error(httpx.TimeoutException("timed out"))
    assert category == "timeout"
    assert "REQUEST_TIMEOUT" in message


def test_network():
    category, message = classify_error(httpx.ConnectError("refused"))
    assert category == "network"
    assert "网络错误" in message


def test_backend_400():
    category, message = classify_error(_http_error(400))
    assert category == "backend"
    assert "400" in message


def test_backend_401():
    category, message = classify_error(_http_error(401))
    assert category == "backend"
    assert "401" in message


def test_backend_429():
    category, message = classify_error(_http_error(429))
    assert category == "backend"
    assert "429" in message


def test_backend_500():
    category, message = classify_error(_http_error(500))
    assert category == "backend"
    assert "500" in message


def test_unknown():
    category, message = classify_error(RuntimeError("boom"))
    assert category == "unknown"
    assert "boom" in message


def test_openai_adapter_runtime_error_timeout():
    category, message = classify_error(RuntimeError("视觉模型请求超时（120s），已重试 3 次。"))
    assert category == "timeout"
    assert "超时" in message