"""Language coverage: import resolution and entry points.

Regression guards for gaps found by indexing real GitHub projects (cobra/go,
ripgrep/rust, fmt/jq/c++, gson/java). Go, Rust and C/C++ collect their imports
at parse time, but the module-name extraction only understood Python/JS/Java
forms, so those three languages produced *no* internal dependency edges at all:
file_deps reported 0 internal imports, module_cycles and project_overview.layering
were empty, while the source files clearly import each other.
"""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.graph import _rust_modules
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox


def _project(tmp_path: Path, files: dict[str, str]):
    root = tmp_path / "proj"
    root.mkdir()
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    db = DB(root)
    ix = Indexer(root, db)
    tb = Toolbox(root, db, ix)
    ix.refresh()
    return root, db, tb


# ---------------- Go ----------------

GO = {
    "go.mod": "module example.com/m\n\ngo 1.22\n",
    "main.go": (
        "package main\n"
        "\n"
        "import (\n"
        '\t"fmt"\n'
        '\t"example.com/m/internal/util"\n'
        ")\n"
        "\n"
        "func main() {\n"
        "\tfmt.Println(util.Helper())\n"
        "}\n"
    ),
    "internal/util/util.go": "package util\n\nfunc Helper() int {\n\treturn 1\n}\n",
}


def test_go_block_import_resolves_to_the_internal_file(tmp_path):
    root, db, tb = _project(tmp_path, GO)
    deps = tb.file_deps("main.go")
    db.close()
    shutil.rmtree(root, ignore_errors=True)

    internal = [i["text"] for i in deps["imports"]]
    resolved = [f for i in deps["imports"] for f in i["resolves_to"]]
    assert "internal/util/util.go" in resolved, internal
    # stdlib stays external: `fmt` must not be resolved to anything
    assert any("fmt" in i["text"] for i in deps["external_imports"])


GO_CYCLE = {
    "go.mod": "module example.com/m\n",
    "internal/a/a.go": (
        "package a\n"
        "\n"
        'import "example.com/m/internal/x"\n'
        "\n"
        "func A() {\n\tx.X()\n}\n"
    ),
    "internal/x/x.go": (
        "package x\n"
        "\n"
        'import "example.com/m/internal/a"\n'
        "\n"
        "func X() {\n\ta.A()\n}\n"
    ),
}


def test_go_import_cycle_is_visible(tmp_path):
    """module_cycles was blind for Go: no edges meant no cycles."""
    root, db, tb = _project(tmp_path, GO_CYCLE)
    cycles = tb.module_cycles(max_cycles=5)
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    assert cycles["count"] >= 1, cycles


# ---------------- Rust ----------------

RUST = {
    "crates/cli/src/a.rs": (
        "use crate::b::Thing;\n"
        "\n"
        "pub fn use_it(t: Thing) -> i32 {\n"
        "\tt.value()\n"
        "}\n"
    ),
    "crates/cli/src/b.rs": (
        "pub struct Thing;\n"
        "\n"
        "impl Thing {\n"
        "    pub fn value(&self) -> i32 {\n"
        "        1\n"
        "    }\n"
        "}\n"
    ),
}


def test_rust_use_resolves_to_the_internal_file(tmp_path):
    root, db, tb = _project(tmp_path, RUST)
    deps = tb.file_deps("crates/cli/src/a.rs")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    resolved = [f for i in deps["imports"] for f in i["resolves_to"]]
    assert "crates/cli/src/b.rs" in resolved, deps["imports"]


def test_rust_module_extraction():
    """Braced groups import from the path before the brace; `crate`/`self`/
    `super` are crate-relative, and the trailing segment is the imported item."""
    assert _rust_modules("use crate::process::{CommandError, CommandReader};") == ["process"]
    assert _rust_modules("use crate::foo::bar::Baz;") == ["foo.bar"]
    assert _rust_modules("use super::sibling;") == ["sibling"]
    assert _rust_modules("use std::{io, fmt};") == ["std"]
    assert _rust_modules("use globset::{Glob, GlobSetBuilder};") == ["globset"]


# ---------------- C / C++ ----------------

CPP = {
    "include/fmt/format.h": (
        "#pragma once\n"
        '#include "core.h"\n'
        "#include <vector>\n"
        "\n"
        "namespace fmt {\n"
        "int widths();\n"
        "}\n"
    ),
    "include/fmt/core.h": "#pragma once\n\nnamespace fmt {\nint core();\n}\n",
    "src/main.c": '#include "core.h"\n\nint main(int argc, char* argv[]) {\n    return 0;\n}\n',
}


def test_cpp_include_resolves_and_system_headers_stay_external(tmp_path):
    root, db, tb = _project(tmp_path, CPP)
    deps = tb.file_deps("include/fmt/format.h")
    db.close()
    shutil.rmtree(root, ignore_errors=True)

    resolved = [f for i in deps["imports"] for f in i["resolves_to"]]
    assert "include/fmt/core.h" in resolved, deps["imports"]
    # <vector> is a system header: it must not resolve to anything
    external = [i["text"] for i in deps["external_imports"]]
    assert any("vector" in t for t in external), external


def test_c_entry_point_is_recognized(tmp_path):
    """jq's only entry point is src/main.c and it was not reported."""
    root, db, tb = _project(tmp_path, CPP)
    overview = tb.project_overview()
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    assert "src/main.c" in overview["entry_points"], overview["entry_points"]


@pytest.mark.parametrize("name", ["Main.java"])
def test_main_java_entry_point_is_recognized(tmp_path, name):
    root, db, tb = _project(
        tmp_path,
        {f"src/{name}": "public class Main {\n    public static void main(String[] a) {}\n}\n"},
    )
    overview = tb.project_overview()
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    assert f"src/{name}" in overview["entry_points"], overview["entry_points"]


# ---------------- ESM default imports ----------------

JS = {
    "package.json": '{"name": "x", "type": "module"}\n',
    "src/index.js": (
        "import axios from '../lib/axios.js';\n"
        "\n"
        "export function main() {\n"
        "\treturn axios;\n"
        "}\n"
    ),
    "lib/axios.js": "export default { get() {} };\n",
    # same basename, different case/dir: used to be a second candidate for the
    # binding-name lookup that this form previously produced
    "lib/core/Axios.js": "export default class Axios {}\n",
}


def test_js_default_import_resolves_the_path_not_the_binding_name(tmp_path):
    """``import axios from '../lib/axios.js'`` must resolve the *path*.

    Bare ``import\\s+`` in the extractor matched the binding instead, so this
    form -- 395 of axios's ~700 import rows -- resolved the local variable name
    and then suffix-matched by it.
    """
    root, db, tb = _project(tmp_path, JS)
    deps = tb.file_deps("src/index.js")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    resolved = [f for i in deps["imports"] for f in i["resolves_to"]]
    assert resolved == ["lib/axios.js"], deps["imports"]


# ---------------- extension sensitivity ----------------

CPP_EXT = {
    "src/jv.c": '#include "jv.h"\n\nint jv_main(void) {\n\treturn 0;\n}\n',
    "src/jv.h": "#pragma once\n\nint jv_len(void);\n",
}


def test_include_extension_is_honoured(tmp_path):
    """``#include "jv.h"`` must not resolve to the sibling jv.c.

    Dropping the extension made `.h` and `.c` interchangeable, which was 92 of
    jq's 363 import rows and most of fmt's 63 ambiguous ones.
    """
    root, db, tb = _project(tmp_path, CPP_EXT)
    deps = tb.file_deps("src/jv.c")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    resolved = [f for i in deps["imports"] for f in i["resolves_to"]]
    assert resolved == ["src/jv.h"], deps["imports"]


JS_EXT = {
    "package.json": '{"name": "x", "type": "module"}\n',
    "tests/esm/case.test.js": "import { help } from './helpers/twin.js';\n\nexport const run = help;\n",
    "tests/esm/helpers/twin.js": "export const help = 1;\n",
    "tests/cjs/helpers/twin.cjs": "module.exports = { help: 1 };\n",
}


def test_js_specifier_does_not_cross_module_kinds(tmp_path):
    """``./x.js`` must not resolve to a sibling ``x.cjs``.

    A `.js` specifier may land on a TS file (Node's TS resolution), but `.cjs`,
    `.mjs` and `.vue` are different files that the specifier would have named
    explicitly. This was the last source of ambiguous import rows on axios.
    """
    root, db, tb = _project(tmp_path, JS_EXT)
    deps = tb.file_deps("tests/esm/case.test.js")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    resolved = [f for i in deps["imports"] for f in i["resolves_to"]]
    assert resolved == ["tests/esm/helpers/twin.js"], deps["imports"]


# ---------------- bare specifiers / language family ----------------

JS_BARE = {
    "package.json": '{"name": "x"}\n',
    "vitest.config.js": "export default {};\n",
    "src/a.test.js": "import { defineConfig } from 'vitest/config';\n\nexport const c = defineConfig;\n",
    "py/os.h": "#pragma once\n",
    "py/thing.py": "import os\n\nprint(os.getcwd())\n",
}


def test_js_bare_specifier_is_a_package_not_a_project_file(tmp_path):
    """Under Node resolution `vitest/config` is an npm package.

    Matching it to a project file named vitest.config.js was 60 of axios's
    ambiguous rows.
    """
    root, db, tb = _project(tmp_path, JS_BARE)
    deps = tb.file_deps("src/a.test.js")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    assert deps["imports"] == [], deps["imports"]
    assert any("vitest" in i["text"] for i in deps["external_imports"])


def test_python_import_cannot_resolve_to_another_language(tmp_path):
    """``import os`` in a .py file must not match the C++ os.h next door."""
    root, db, tb = _project(tmp_path, JS_BARE)
    deps = tb.file_deps("py/thing.py")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    assert deps["imports"] == [], deps["imports"]
    assert any("os" in i["text"] for i in deps["external_imports"])


# ---------------- module roots (go.mod / Rust crates) ----------------

GO_MODULE = {
    "go.mod": "module example.com/m\n\ngo 1.22\n",
    "cmd/app/main.go": (
        "package main\n"
        "\n"
        'import "example.com/m/internal/util"\n'
        "\n"
        "func main() {\n"
        "\tutil.Run()\n"
        "}\n"
    ),
    "internal/util/util.go": "package util\n\nfunc Run() {}\n",
    # same package directory name, but a different package path
    "tools/util/util.go": "package util\n\nfunc Other() {}\n",
}


def test_go_module_prefix_pins_the_package_directory(tmp_path):
    """The import path resolves through go.mod, not by its last segment.

    Without the module prefix, "example.com/m/internal/util" matched every
    directory called util/ in the repo.
    """
    root, db, tb = _project(tmp_path, GO_MODULE)
    deps = tb.file_deps("cmd/app/main.go")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    resolved = [f for i in deps["imports"] for f in i["resolves_to"]]
    assert resolved == ["internal/util/util.go"], deps["imports"]


GO_SELF = {
    "go.mod": "module example.com/m\n",
    "pkg/a.go": "package pkg\n\nfunc A() {}\n",
    "pkg/a_test.go": (
        "package pkg_test\n"
        "\n"
        'import "example.com/m/pkg"\n'
        "\n"
        "func TestA(t *testing.T) {\n"
        "\tpkg.A()\n"
        "}\n"
    ),
}


def test_package_import_never_targets_the_importer(tmp_path):
    """An external test package importing its own directory must not self-link.

    ``doc/man_examples_test.go`` in cobra showed up as a 1-file import cycle
    before this: the package resolved to itself.
    """
    root, db, tb = _project(tmp_path, GO_SELF)
    deps = tb.file_deps("pkg/a_test.go")
    cycles = tb.module_cycles(max_cycles=5)["count"]
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    resolved = [f for i in deps["imports"] for f in i["resolves_to"]]
    assert resolved == ["pkg/a.go"], deps["imports"]
    assert cycles == 0, cycles


RUST_CRATE = {
    "crates/a/src/util.rs": "pub fn a_only() {}\n",
    "crates/b/Cargo.toml": '[package]\nname = "b"\n',
    "crates/b/src/util.rs": "pub struct Thing;\n",
    "crates/b/src/module/mod.rs": "pub struct Nested;\n",
    "crates/b/src/sub/deep.rs": "use super::helper::H;\n\npub fn d() {\n\tlet _ = H;\n}\n",
    "crates/b/src/sub/helper.rs": "pub struct H;\n",
    "crates/b/src/main.rs": (
        "use crate::util::Thing;\n"
        "use crate::module::Nested;\n"
        "\n"
        "fn main() {\n"
        "\tlet _ = Thing;\n"
        "\tlet _ = Nested;\n"
        "}\n"
    ),
}


def test_rust_crate_root_pins_the_module(tmp_path):
    """`crate::` is relative to the crate root, so crate b cannot see crate a.

    Resolving by name would pick crates/a/src/util.rs as well; `crate::module`
    also has to reach the ``mod.rs`` form.
    """
    root, db, tb = _project(tmp_path, RUST_CRATE)
    deps = tb.file_deps("crates/b/src/main.rs")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    resolved = sorted({f for i in deps["imports"] for f in i["resolves_to"]})
    assert resolved == ["crates/b/src/module/mod.rs", "crates/b/src/util.rs"], resolved


def test_rust_super_path_resolves_in_the_module(tmp_path):
    """``super::helper`` from sub/deep.rs is sub/helper.rs."""
    root, db, tb = _project(tmp_path, RUST_CRATE)
    deps = tb.file_deps("crates/b/src/sub/deep.rs")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    resolved = [f for i in deps["imports"] for f in i["resolves_to"]]
    assert resolved == ["crates/b/src/sub/helper.rs"], deps["imports"]


# ---------------- relative paths resolve as paths ----------------

JS_SIBLING = {
    "package.json": '{"name": "x"}\n',
    "lib/platform/node/index.js": (
        "import URLSearchParams from './classes/URLSearchParams.js';\n"
        "\n"
        "export default URLSearchParams;\n"
    ),
    "lib/platform/node/classes/URLSearchParams.js": (
        "export default class NodeURLSearchParams {}\n"
    ),
    "lib/platform/browser/classes/URLSearchParams.js": (
        "export default class BrowserURLSearchParams {}\n"
    ),
}


def test_relative_path_resolves_against_the_importing_directory(tmp_path):
    """``'./classes/x.js'`` means the caller's own ``classes/``.

    Both platform variants share the basename, so the basename fallback picks
    the wrong one -- the last ambiguous rows on axios (browser vs node builds).
    """
    root, db, tb = _project(tmp_path, JS_SIBLING)
    deps = tb.file_deps("lib/platform/node/index.js")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    resolved = [f for i in deps["imports"] for f in i["resolves_to"]]
    assert resolved == ["lib/platform/node/classes/URLSearchParams.js"], deps["imports"]


# ---------------- proximity ----------------

RUST_LOCAL = {
    "crates/a/src/util.rs": "pub fn a_helper() -> i32 {\n\t1\n}\n",
    "tests/util.rs": "pub struct Dir;\n\npub fn from_tests() {}\n",
    "tests/feature.rs": (
        "use crate::util::{Dir, from_tests};\n"
        "\n"
        "#[test]\n"
        "fn t() {\n"
        "\tlet _ = Dir;\n"
        "\tfrom_tests();\n"
        "}\n"
    ),
}


def test_same_directory_wins_over_a_repo_wide_basename_match(tmp_path):
    """A crate-relative use resolves next to its own file first.

    ``tests/feature.rs``'s ``use crate::util`` means ``tests/util.rs``, not the
    same-named file under another crate root (14 of ripgrep's 17 ambiguous rows).
    """
    root, db, tb = _project(tmp_path, RUST_LOCAL)
    deps = tb.file_deps("tests/feature.rs")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    resolved = [f for i in deps["imports"] for f in i["resolves_to"]]
    assert resolved == ["tests/util.rs"], deps["imports"]


# ---------------- directory entry files ----------------

JS_ENTRY = {
    "package.json": '{"name": "x", "type": "module"}\n',
    "src/main.ts": "import './server';\nimport './widgets/panel';\n",
    "src/server/index.ts": "export const s = 1;\n",
    "src/widgets/panel/index.tsx": "export const P = 1;\n",
}


def test_js_directory_import_resolves_to_its_index_file(tmp_path):
    """``import './server'`` is ``server/index.ts`` under Node/TS resolution.

    Resolving only file stems left every directory import unresolved -- 35
    relative imports on vite, all of its ``import './importing-updated'`` rows.
    """
    root, db, tb = _project(tmp_path, JS_ENTRY)
    deps = tb.file_deps("src/main.ts")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    resolved = sorted(f for i in deps["imports"] for f in i["resolves_to"])
    assert resolved == ["src/server/index.ts", "src/widgets/panel/index.tsx"], deps["imports"]


JS_ENTRY_EXT = {
    "package.json": '{"name": "x", "type": "module"}\n',
    "src/main.js": "import './server.js';\n",
    "src/server/index.js": "export const s = 1;\n",
}


def test_explicit_extension_does_not_fall_back_into_a_directory(tmp_path):
    """``./server.js`` names a file; Node does not retry it as ``server/``."""
    root, db, tb = _project(tmp_path, JS_ENTRY_EXT)
    deps = tb.file_deps("src/main.js")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    assert deps["imports"] == [], deps["imports"]


PY_ENTRY = {
    "pkg/__init__.py": "VERSION = '1'\n",
    "pkg/helper.py": "def h():\n\treturn 1\n",
    "pkg/sub/__init__.py": "S = 1\n",
    "pkg/consumer.py": "from . import helper\nfrom . import sub\nfrom . import VERSION\n",
}


def test_python_from_dot_import_reaches_submodules_and_the_package_entry(tmp_path):
    """``from . import x`` is a submodule of the package, or a name in its entry.

    The module part is empty, which the suffix lookup can never match: all 11
    such rows on requests (``from . import _types as _t``) resolved to nothing.
    """
    root, db, tb = _project(tmp_path, PY_ENTRY)
    deps = tb.file_deps("pkg/consumer.py")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    got = {i["text"].splitlines()[0]: sorted(i["resolves_to"]) for i in deps["imports"]}
    assert got["from . import helper"] == ["pkg/helper.py"], got
    assert got["from . import sub"] == ["pkg/sub/__init__.py"], got
    assert got["from . import VERSION"] == ["pkg/__init__.py"], got


PY_ABS_ENTRY = {
    "pkg/sub/__init__.py": "S = 1\n",
    "app.py": "import pkg.sub\n\nprint(pkg.sub.S)\n",
}


def test_python_absolute_package_path_resolves_to_its_init(tmp_path):
    """``import pkg.sub`` is ``pkg/sub/__init__.py``, not a file named ``sub``."""
    root, db, tb = _project(tmp_path, PY_ABS_ENTRY)
    deps = tb.file_deps("app.py")
    db.close()
    shutil.rmtree(root, ignore_errors=True)
    resolved = [f for i in deps["imports"] for f in i["resolves_to"]]
    assert resolved == ["pkg/sub/__init__.py"], deps["imports"]
