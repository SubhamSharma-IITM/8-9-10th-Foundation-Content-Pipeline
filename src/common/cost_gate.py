"""
cost_gate.py - Interactive cost confirmation + dry-run mode for paid stages.

Wraps any paid stage (MathPix, Gemini, etc.). Before invocation:
  - Print stage name, item count, INR estimate, model + thinking_level
  - In dry-run mode: SKIP the API call, return canned/structural output
  - In confirm mode: prompt user for [y/N]. If --yes flag passed, auto-confirm.
  - On real invocation, log to experiments/_cost_log.jsonl

Discipline (from pipeline_stages_testing_discipline.md):
  - First-time run on a new chapter: dry-run first, then live run with explicit confirmation
  - Subsequent runs in same session: can pass yes=True if user authorized scope
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COST_LOG_PATH = PROJECT_ROOT / "experiments" / "_cost_log.jsonl"


@dataclass
class CostEstimate:
    stage: str               # e.g. "ncert_stage1_mathpix_ocr"
    chapter_key: str         # e.g. "ch12_magnetic_ncert"
    item_count: int          # number of items (pages, questions, subs) to process
    inr_estimate: float      # expected INR cost
    model: str = ""          # e.g. "gemini-3.1-pro-preview"
    thinking_level: str = "" # "LOW" / "MEDIUM" / "HIGH" / "" for non-LLM
    notes: str = ""


def _safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


def confirm_spend(est: CostEstimate, yes: bool = False, dry_run: bool = False) -> bool:
    """
    Print the cost estimate and (unless yes=True) prompt the user.

    Returns True if the caller should proceed with the paid invocation, False to skip.

    dry_run=True ALWAYS returns False - the caller should branch into mock-output mode.
    """
    _safe_print("")
    _safe_print("=" * 72)
    _safe_print(f"  PAID STAGE GATE: {est.stage}")
    _safe_print("=" * 72)
    _safe_print(f"  chapter        : {est.chapter_key}")
    _safe_print(f"  items          : {est.item_count}")
    _safe_print(f"  est cost (INR) : Rs {est.inr_estimate:.2f}")
    if est.model:
        _safe_print(f"  model          : {est.model}")
    if est.thinking_level:
        _safe_print(f"  thinking_level : {est.thinking_level}")
    if est.notes:
        _safe_print(f"  notes          : {est.notes}")
    if dry_run:
        _safe_print("  MODE           : DRY-RUN (no API call)")
        _safe_print("=" * 72)
        return False
    if yes:
        _safe_print("  MODE           : AUTO-CONFIRMED (--yes)")
        _safe_print("=" * 72)
        return True

    _safe_print("=" * 72)
    try:
        ans = input("  Proceed with paid invocation? [y/N]: ").strip().lower()
    except EOFError:
        ans = ""
    proceed = ans in ("y", "yes")
    _safe_print(f"  -> {'PROCEEDING' if proceed else 'ABORTED'}")
    return proceed


def log_spend(est: CostEstimate, actual_inr: float, status: str = "ok", error: str = "") -> None:
    """Append an entry to the cost log. Call this after the paid invocation completes."""
    COST_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "stage": est.stage,
        "chapter_key": est.chapter_key,
        "item_count": est.item_count,
        "inr_estimate": est.inr_estimate,
        "inr_actual": actual_inr,
        "model": est.model,
        "thinking_level": est.thinking_level,
        "status": status,
        "error": error,
    }
    with COST_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def total_spent(chapter_key: str | None = None) -> float:
    """Sum actual INR cost from the log. Optionally filter by chapter."""
    if not COST_LOG_PATH.exists():
        return 0.0
    total = 0.0
    with COST_LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if chapter_key and entry.get("chapter_key") != chapter_key:
                continue
            total += float(entry.get("inr_actual", 0.0))
    return total


if __name__ == "__main__":
    # sanity check + demo
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    est = CostEstimate(
        stage="demo_stage",
        chapter_key="ch12_magnetic_ncert",
        item_count=14,
        inr_estimate=80.0,
        model="gemini-3.1-pro-preview",
        thinking_level="HIGH",
        notes="content generation for 14 subconcepts",
    )

    # dry-run path
    proceed = confirm_spend(est, dry_run=True)
    assert proceed is False, "dry_run must always return False"

    # auto-confirm path
    proceed = confirm_spend(est, yes=True)
    assert proceed is True, "yes=True must auto-confirm"
    log_spend(est, actual_inr=75.5)

    spent = total_spent("ch12_magnetic_ncert")
    _safe_print(f"\nTotal logged for ch12_magnetic_ncert: Rs {spent:.2f}")
    _safe_print("\ncost_gate.py sanity check PASSED")
