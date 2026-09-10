"""Indexer refuses to scan the user home directory (auto-detect fallback)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastgraph.db import DB
from fastgraph.index import Indexer


def test_home_root_skips_scan(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / "huge.py").write_text("x = 1\n", encoding="utf-8")
    # point the guard at a fake home so the real user home is untouched
    monkeypatch.setattr("fastgraph.index.user_home", lambda: fake_home)
    db = DB(fake_home)
    idx = Indexer(fake_home, db)
    stats = idx.refresh()
    assert stats.skipped is True
    assert db.count_files() == 0
    assert db.count_symbols() == 0
    db.close()