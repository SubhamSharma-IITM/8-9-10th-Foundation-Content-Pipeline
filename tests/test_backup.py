"""Unit tests for src/common/backup.py."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.common.backup import (
    list_backups,
    safe_write_json,
    safe_write_text,
    snapshot,
)


class TestSnapshot:
    def test_snapshot_missing_file_returns_none(self, tmp_path):
        out = tmp_path / "topology.json"
        assert snapshot(out) is None

    def test_snapshot_existing_file_creates_backup(self, tmp_path):
        out = tmp_path / "topology.json"
        out.write_text('{"v": 1}', encoding="utf-8")
        bak = snapshot(out)
        assert bak is not None
        assert bak.exists()
        assert bak.parent.name == "_backups"
        assert bak.parent.parent == tmp_path
        assert bak.read_text(encoding="utf-8") == '{"v": 1}'
        # original still present
        assert out.exists()

    def test_snapshot_preserves_extension(self, tmp_path):
        out = tmp_path / "data.mmd"
        out.write_text("\\section*{Chapter}", encoding="utf-8")
        bak = snapshot(out)
        assert bak.suffix == ".mmd"
        assert bak.stem.startswith("data_")


class TestSafeWrite:
    def test_safe_write_json_first_time_no_backup(self, tmp_path):
        out = tmp_path / "topology.json"
        bak = safe_write_json(out, {"v": 1})
        assert bak is None
        assert json.loads(out.read_text("utf-8")) == {"v": 1}

    def test_safe_write_json_overwrite_creates_backup(self, tmp_path):
        out = tmp_path / "topology.json"
        safe_write_json(out, {"v": 1})
        bak = safe_write_json(out, {"v": 2})
        assert bak is not None
        assert json.loads(bak.read_text("utf-8")) == {"v": 1}
        assert json.loads(out.read_text("utf-8")) == {"v": 2}

    def test_safe_write_text(self, tmp_path):
        out = tmp_path / "report.txt"
        bak1 = safe_write_text(out, "first")
        assert bak1 is None
        bak2 = safe_write_text(out, "second")
        assert bak2 is not None
        assert bak2.read_text("utf-8") == "first"


class TestCollisionHandling:
    def test_back_to_back_writes_in_same_second_both_survive(self, tmp_path):
        """The critical regression: two backups in <1s must not overwrite each other."""
        out = tmp_path / "topology.json"
        safe_write_json(out, {"v": 1})
        bak_a = safe_write_json(out, {"v": 2})  # backs up v=1
        bak_b = safe_write_json(out, {"v": 3})  # backs up v=2
        assert bak_a is not None
        assert bak_b is not None
        assert bak_a != bak_b
        assert json.loads(bak_a.read_text("utf-8")) == {"v": 1}
        assert json.loads(bak_b.read_text("utf-8")) == {"v": 2}


class TestListBackups:
    def test_list_returns_all_backups_sorted(self, tmp_path):
        out = tmp_path / "topology.json"
        safe_write_json(out, {"v": 1})
        safe_write_json(out, {"v": 2})
        safe_write_json(out, {"v": 3})
        bks = list_backups(out)
        assert len(bks) == 2  # v=1 and v=2 snapshots; v=3 is the live file

    def test_list_empty_when_no_backups(self, tmp_path):
        out = tmp_path / "topology.json"
        out.write_text("{}", encoding="utf-8")
        assert list_backups(out) == []
