"""file_deps resolves @/ imports via jsconfig paths."""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer
from fastgraph.tools import Toolbox

WORK = Path(__file__).resolve().parent / "work_aliasdeps"
JSCONFIG = {"compilerOptions": {"paths": {"@/*": ["src/*"]}}}
MAIN = "import { fmt } from '@/utils/format';\nexport function main() { return fmt(); }\n"
UTIL = "export function fmt() { return 1; }\n"


def _rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def test_alias_import_resolves():
    _rmtree(WORK)
    (WORK / "src/utils").mkdir(parents=True, exist_ok=True)
    (WORK / "jsconfig.json").write_text(json.dumps(JSCONFIG), encoding="utf-8")
    (WORK / "src" / "main.js").write_text(MAIN, encoding="utf-8")
    (WORK / "src/utils/format.js").write_text(UTIL, encoding="utf-8")
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    tb = Toolbox(WORK, db, Indexer(WORK, db))
    deps = tb.file_deps("src/main.js")
    assert deps["found"] is True
    # file_deps splits resolved imports into `imports` (external stay external)
    assert any(
        "src/utils/format.js" in t for imp in deps.get("imports", []) for t in imp["resolves_to"]
    )
    db.close()
    _rmtree(WORK)


def test_uni_app_alias_in_subproject():
    """uni-app `@` convention resolved from the sub-project dir (pages.json)."""
    _rmtree(WORK)
    (WORK / "mini/utils").mkdir(parents=True, exist_ok=True)
    (WORK / "mini/pages.json").write_text("{}", encoding="utf-8")
    (WORK / "mini/utils/plan.js").write_text(
        "import { formatTime } from '@/utils/format.js';\n"
        "export function p() { return formatTime(); }\n",
        encoding="utf-8",
    )
    (WORK / "mini/utils/format.js").write_text(
        "export function formatTime() { return 1; }\n", encoding="utf-8"
    )
    db = DB(WORK)
    Indexer(WORK, db).force_index()
    tb = Toolbox(WORK, db, Indexer(WORK, db))
    deps = tb.file_deps("mini/utils/plan.js")
    assert any(
        "mini/utils/format.js" in t
        for imp in deps.get("imports", [])
        for t in imp["resolves_to"]
    )
    db.close()
    _rmtree(WORK)