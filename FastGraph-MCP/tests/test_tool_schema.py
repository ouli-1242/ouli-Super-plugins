"""Advertised tool schemas stay model-friendly: every parameter carries a
description, and ambiguous tool pairs cross-reference each other in their
tool descriptions (routing), so the model can pick the right tool without
guessing. Regression guards for the tool-surface description work.
"""
import gc
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.server import build_server

WORK = Path(__file__).resolve().parent / "work_schema"


def _rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _tools():
    _rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)
    server = build_server(WORK)
    return server._tool_manager.list_tools()


def test_every_parameter_has_a_description():
    try:
        missing = [
            (t.name, name)
            for t in _tools()
            for name, prop in (t.parameters or {}).get("properties", {}).items()
            if not prop.get("description")
        ]
        assert missing == [], f"parameters without description: {missing}"
    finally:
        gc.collect()
        _rmtree(WORK)


def test_ambiguous_tools_cross_reference_each_other():
    try:
        docs = {t.name: t.description or "" for t in _tools()}
        assert "find_callees" in docs["symbol_info"], "symbol_info must route callee queries to find_callees"
        assert "find_callers" in docs["trace_path"], "trace_path must route direct-caller queries to find_callers"
        assert "impact_analysis" in docs["find_callers"], "find_callers must route change-impact to impact_analysis"
        assert "rename_impact" in docs["find_callers"], "find_callers must route rename risk to rename_impact"
        assert "impact_analysis" in docs["rename_impact"], "rename_impact must route behavior-change impact to impact_analysis"
        assert "find_callers" in docs["impact_analysis"], "impact_analysis must route plain caller lists to find_callers"
    finally:
        gc.collect()
        _rmtree(WORK)