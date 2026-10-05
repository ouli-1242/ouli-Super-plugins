"""`language_for_path` is a string scan that must keep ``Path.suffix`` semantics.

The indexer calls it for every entry it walks, so building a Path per candidate
cost ~16% of a no-op refresh on a 17,703-file repo. The replacement is two
`rfind` calls, and the cases where `Path.suffix` says "no extension" are exactly
the ones a plain ``rsplit(".")`` gets wrong.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.parsers.registry import SUPPORTED_EXTENSIONS, language_for_path


def test_leading_dot_and_dotted_directories():
    assert language_for_path("mod.ts") == "typescript"
    assert language_for_path("MOD.TS") == "typescript"          # case-insensitive
    assert language_for_path("pkg/sub/mod.py") == "python"
    assert language_for_path(".gitignore") is None              # leading dot = no suffix
    assert language_for_path("pkg/.hidden.ts") == "typescript"  # dot is not the name start
    assert language_for_path("pkg/.hidden") is None
    assert language_for_path("my.dir/file") is None             # dot outside the name
    assert language_for_path("noext") is None
    assert language_for_path("") is None
    assert language_for_path(Path("a/b/c.go")) == "go"


def test_matches_path_suffix_for_every_registered_extension():
    for ext, lang in sorted(SUPPORTED_EXTENSIONS.items()):
        for shape in (f"src/mod.{ext}", f"a.{ext}/b.{ext}", f"{ext}.{ext}"):
            assert language_for_path(shape) == lang, shape
        # a final component that begins with the extension name is not a match
        assert language_for_path(f"src/.{ext}") is None, ext
