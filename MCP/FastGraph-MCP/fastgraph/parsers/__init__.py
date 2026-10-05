"""Language adapters registry and file-type detection."""

from __future__ import annotations

from fastgraph.parsers.registry import (
    available_languages,
    get_adapter,
    language_for_path,
    register_adapter,
    SUPPORTED_EXTENSIONS,
)

# Import adapters so they self-register.
from fastgraph.parsers import python as _python
from fastgraph.parsers import typescript as _typescript
from fastgraph.parsers import go as _go
from fastgraph.parsers import rust as _rust
from fastgraph.parsers import java as _java
from fastgraph.parsers import cpp as _cpp
from fastgraph.parsers import frontend as _frontend
from fastgraph.parsers import wxml as _wxml

__all__ = [
    "available_languages",
    "get_adapter",
    "language_for_path",
    "SUPPORTED_EXTENSIONS",
]