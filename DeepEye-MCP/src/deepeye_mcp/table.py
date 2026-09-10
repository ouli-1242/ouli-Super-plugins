"""表格提取：视觉模型 JSON → Markdown 转换。

视觉模型负责读表并输出结构化 JSON，本模块负责确定性的格式转换。
"""

_TABLE_JSON_PROMPT = """
分析这张图片中的表格，输出 JSON。只返回 JSON，不加任何说明文字。
JSON 格式：
{"columns": 列数, "title": "表格标题或空串", "rows": [{"cells": [{"text": "单元格内容", "rowspan": 1, "colspan": 1}]}]}
要求：
1. 完整保留所有单元格数据，绝不允许丢失或合并任何内容。
2. 合并单元格用 rowspan / colspan 标注数量（默认 1）。
3. 表头行作为第一行 rows 数据。
4. 图表（柱状图/折线图/饼图）转化为对应的数据表。
"""


def json_to_markdown(parsed: dict) -> str:
    """把表格 JSON 转换为 Markdown 表格。

    Args:
        parsed: 含 ``rows`` 的字典，每行含 ``cells`` 列表。

    Returns:
        Markdown 表格字符串；空表格返回 ``（空表格）``。
    """
    rows = parsed.get("rows") or []
    if not rows:
        return "（空表格）"
    max_cols = max((len(r.get("cells", [])) for r in rows), default=0)
    if max_cols == 0:
        return "（空表格）"

    def _row(cells: list) -> str:
        padded = [c.get("text", "").replace("|", "\\|") for c in cells]
        padded += [""] * (max_cols - len(padded))
        return "| " + " | ".join(padded) + " |"

    header = _row(rows[0].get("cells", []))
    sep = "|" + "---|" * max_cols
    body = [_row(r.get("cells", [])) for r in rows[1:]]
    return "\n".join([header, sep] + body)


def has_merged_cells(parsed: dict) -> bool:
    """是否存在合并单元格（rowspan/colspan > 1）。"""
    for row in parsed.get("rows") or []:
        for cell in row.get("cells", []):
            if cell.get("rowspan", 1) > 1 or cell.get("colspan", 1) > 1:
                return True
    return False