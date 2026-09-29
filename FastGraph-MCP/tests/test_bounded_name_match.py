"""The word-boundary test used by the resolver must match the regex it replaced.

`_bounded_hit` swapped a per-edge `re.search(r"(?<![\\w$])owner(?![\\w$])")` for
`str.find` + two character checks (2,005 such calls cost 846us each on a sentry
subtree, 224us with the find). Two edge cases are easy to get wrong: a name at
the very start/end of the import text, and the extra boundary characters (`$` for
identifiers, `.` for Java fully-qualified names).
"""
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.index import _bounded_hit


def _regex(hay: str, needle: str, extra: str) -> bool:
    return re.search(rf"(?<![\w{extra}]){re.escape(needle)}(?![\w{extra}])", hay) is not None


def test_boundary_cases():
    # the empty neighbour: `"" in "_$"` is True in Python, so an edge of the
    # haystack has to be judged by length, not by membership
    assert _bounded_hit(" import user", "user", "$")
    assert _bounded_hit("user import", "user", "$")
    assert _bounded_hit("user", "user", "$")
    assert not _bounded_hit(" import user_service", "user", "$")
    assert not _bounded_hit(" import myuser", "user", "$")
    # `$` is part of an identifier in JS, `.` in a Java fully-qualified name
    assert not _bounded_hit("import jquery$x", "jquery", "$")
    # a dotted Java name is only ever searched as a whole
    assert not _bounded_hit("import a.userservice;", "userservice", ".")
    assert not _bounded_hit("import com.a.parserx;", "com.a.parser", ".")
    assert not _bounded_hit("import xcom.a.parser;", "com.a.parser", ".")
    assert _bounded_hit("import com.a.parser;", "com.a.parser", ".")
    assert not _bounded_hit("import zlib", "zip", "$")
    assert not _bounded_hit("import zlib", "", "$")


def test_matches_the_regex_it_replaced():
    rng = random.Random(7)
    words = ["user", "user_service", "svc", "$ctx", "com.a.parser", "a.b.c",
             "Parser", "x", "", "_priv", "u", "服务"]
    seps = [" ", ";", "\n", ",", "(", ":", "\t", ""]
    for _ in range(600):
        hay = "".join(rng.choice(words) + rng.choice(seps) for _ in range(8))
        for needle in words:
            if not needle:
                continue  # an empty name is refused outright; the regex would match
            for extra in ("$", "."):
                assert _bounded_hit(hay, needle, extra) == _regex(
                    hay, needle, extra
                ), (hay, needle, extra)
