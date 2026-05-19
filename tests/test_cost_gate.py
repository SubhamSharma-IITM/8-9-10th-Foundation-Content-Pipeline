"""Unit tests for src/common/cost_gate.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.common import cost_gate
from src.common.cost_gate import CostEstimate, confirm_spend, log_spend, total_spent


@pytest.fixture
def sample_estimate() -> CostEstimate:
    return CostEstimate(
        stage="test_stage",
        chapter_key="ch12_magnetic_ncert",
        item_count=14,
        inr_estimate=80.0,
        model="gemini-3.1-pro-preview",
        thinking_level="HIGH",
        notes="unit test estimate",
    )


@pytest.fixture
def isolated_cost_log(tmp_path, monkeypatch):
    """Redirect COST_LOG_PATH to a tmp file so tests don't pollute the real log."""
    fake_log = tmp_path / "_cost_log.jsonl"
    monkeypatch.setattr(cost_gate, "COST_LOG_PATH", fake_log)
    return fake_log


class TestConfirmSpend:
    def test_dry_run_always_returns_false(self, sample_estimate, capsys):
        assert confirm_spend(sample_estimate, dry_run=True) is False
        out = capsys.readouterr().out
        assert "DRY-RUN" in out
        assert "test_stage" in out
        assert "Rs 80.00" in out

    def test_yes_flag_auto_confirms(self, sample_estimate):
        assert confirm_spend(sample_estimate, yes=True) is True

    def test_dry_run_takes_precedence_over_yes(self, sample_estimate):
        # If a script accidentally passes both, dry_run must win (safer default)
        assert confirm_spend(sample_estimate, yes=True, dry_run=True) is False


class TestLogSpend:
    def test_log_writes_jsonl_entry(self, sample_estimate, isolated_cost_log):
        log_spend(sample_estimate, actual_inr=75.5)
        assert isolated_cost_log.exists()
        lines = isolated_cost_log.read_text("utf-8").strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["stage"] == "test_stage"
        assert entry["chapter_key"] == "ch12_magnetic_ncert"
        assert entry["item_count"] == 14
        assert entry["inr_actual"] == 75.5
        assert entry["status"] == "ok"

    def test_log_appends_multiple_entries(self, sample_estimate, isolated_cost_log):
        log_spend(sample_estimate, actual_inr=10.0)
        log_spend(sample_estimate, actual_inr=20.0)
        lines = isolated_cost_log.read_text("utf-8").strip().splitlines()
        assert len(lines) == 2


class TestTotalSpent:
    def test_total_with_no_log(self, isolated_cost_log):
        assert total_spent() == 0.0

    def test_total_sums_actual_inr(self, sample_estimate, isolated_cost_log):
        log_spend(sample_estimate, actual_inr=10.0)
        log_spend(sample_estimate, actual_inr=20.0)
        log_spend(sample_estimate, actual_inr=15.5)
        assert total_spent() == pytest.approx(45.5)

    def test_total_filtered_by_chapter(self, sample_estimate, isolated_cost_log):
        log_spend(sample_estimate, actual_inr=10.0)
        other = CostEstimate(
            stage="other_stage", chapter_key="other_chapter",
            item_count=1, inr_estimate=5.0,
        )
        log_spend(other, actual_inr=5.0)
        assert total_spent("ch12_magnetic_ncert") == pytest.approx(10.0)
        assert total_spent("other_chapter") == pytest.approx(5.0)
        assert total_spent() == pytest.approx(15.0)
