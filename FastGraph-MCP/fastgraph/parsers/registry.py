"""Module registry: assigns languages to file extensions."""

from __future__ import annotations

from pathlib import Path

SUPPORTED_EXTENSIONS: dict[str, str] = {}  # ext -> language key

_adapters: dict[str, "Adapter"] = {}


def register_adapter(adapter) -> None:
    _adapters[adapter.lang] = adapter
    for ext in adapter.exts:
        SUPPORTED_EXTENSIONS[ext.lstrip(".")] = adapter.lang


def get_adapter(language: str):
    return _adapters.get(language)


def available_languages() -> list[str]:
    return sorted(_adapters)


def language_for_path(path: str | Path) -> str | None:
    ext = Path(path).suffix.lstrip(".").lower()
    return SUPPORTED_EXTENSIONS.get(ext)