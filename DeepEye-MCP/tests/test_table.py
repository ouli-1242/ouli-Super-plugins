"""表格 JSON → Markdown 转换单元测试。"""
from deepeye_mcp.table import has_merged_cells, json_to_markdown


def test_simple_table():
    parsed = {
        "columns": 2,
        "rows": [
            {"cells": [{"text": "名称", "rowspan": 1, "colspan": 1}, {"text": "价格"}]},
            {"cells": [{"text": "苹果", "rowspan": 1, "colspan": 1}, {"text": "5元"}]},
        ],
    }
    md = json_to_markdown(parsed)
    assert "| 名称 | 价格 |" in md
    assert "| 苹果 | 5元 |" in md
    assert "---" in md


def test_rows_ragged_padded_to_max_width():
    """合并单元格导致某行 cell 数少于最大列宽时，应补齐空列。"""
    parsed = {
        "columns": 2,
        "rows": [
            {"cells": [{"text": "A", "rowspan": 2, "colspan": 1}, {"text": "B"}]},
            {"cells": [{"text": "C"}]},
        ],
    }
    md = json_to_markdown(parsed)
    assert "| C |  |" in md


def test_merged_cells_flagged():
    parsed = {"rows": [{"cells": [{"text": "A", "rowspan": 2, "colspan": 1}]}]}
    assert has_merged_cells(parsed) is True


def test_no_merged_cells():
    parsed = {"rows": [{"cells": [{"text": "x", "rowspan": 1, "colspan": 1}]}]}
    assert has_merged_cells(parsed) is False


def test_pipe_escaped():
    parsed = {"rows": [{"cells": [{"text": "a|b"}]}]}
    md = json_to_markdown(parsed)
    assert "a\\|b" in md


def test_empty_rows():
    assert json_to_markdown({"rows": []}) == "（空表格）"