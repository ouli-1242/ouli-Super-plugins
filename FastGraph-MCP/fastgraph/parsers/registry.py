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
    """Language key of the file at ``path``, by its extension.

    Plain string search instead of ``Path(path).suffix``: the indexer calls this
    for every entry it walks, and together with not wrapping each candidate in a
    ``Path`` it was worth ~16% of a no-op refresh on a 17,703-file repo
    (1.00s -> 0.84s). Same rule as ``Path.suffix``: a final component starting
    with a dot, or a dot that is not in the file name at all, has no extension.
    """
    name = path if isinstance(path, str) else str(path)
    dot = name.rfind(".")
    if dot <= 0:
        return None  # no dot, or a leading-dot name like ".gitignore"
    sep = max(name.rfind("/"), name.rfind("\\"))
    if dot == sep + 1:
        return None  # "pkg/.hidden": the dot belongs to the name, not the suffix
    return SUPPORTED_EXTENSIONS.get(name[dot + 1:].lower())
