"""
stage_validators.py - Output shape validators per pipeline stage.

Every stage's output must pass its validator before the next stage may consume it.
This is the gate enforcer for the testing discipline.

Validators return ValidationResult(ok: bool, errors: list[str], warnings: list[str]).
Callers should assert ok before proceeding. Warnings are logged but non-blocking.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ValidationResult:
    ok: bool
    stage: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def report(self) -> str:
        lines = [f"[{self.stage}] {'PASS' if self.ok else 'FAIL'}"]
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        for w in self.warnings:
            lines.append(f"  WARN:  {w}")
        return "\n".join(lines)


def _load_json(path: Path) -> tuple[Any, list[str]]:
    """Load JSON safely. Returns (data, errors)."""
    if not path.exists():
        return None, [f"file does not exist: {path}"]
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as e:
        return None, [f"invalid JSON in {path}: {e}"]
    except Exception as e:
        return None, [f"failed to read {path}: {e}"]


# ---------------------------------------------------------------------
# Stage 1 / C1 - MathPix MMD output
# ---------------------------------------------------------------------
def validate_mmd(mmd_path: Path, min_lines: int = 100, min_sections: int = 3) -> ValidationResult:
    res = ValidationResult(ok=True, stage="mmd")
    if not mmd_path.exists():
        res.errors.append(f"MMD file missing: {mmd_path}")
        res.ok = False
        return res

    text = mmd_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) < min_lines:
        res.errors.append(f"MMD has {len(lines)} lines, expected >= {min_lines}")
        res.ok = False

    section_count = len(re.findall(r"\\section\*?\{", text))
    if section_count < min_sections:
        res.errors.append(f"MMD has {section_count} \\section* headers, expected >= {min_sections}")
        res.ok = False

    # warning-only checks
    if "\\and" in text:
        res.warnings.append("MMD contains '\\and' artifacts (cleaner should fix)")
    if "\\text {" in text:
        res.warnings.append("MMD contains '\\text {' (space after brace) - cleaner should fix")

    return res


# ---------------------------------------------------------------------
# Stage 2 / C2 - topology / schema output
# ---------------------------------------------------------------------
def validate_topology_schema(schema_path: Path) -> ValidationResult:
    res = ValidationResult(ok=True, stage="topology_schema")
    data, errs = _load_json(schema_path)
    if errs:
        res.errors.extend(errs)
        res.ok = False
        return res

    if not isinstance(data, dict):
        res.errors.append("schema root must be a dict")
        res.ok = False
        return res

    concepts = data.get("concepts", [])
    if not isinstance(concepts, list) or len(concepts) < 1:
        res.errors.append(f"schema must have >=1 concepts, got {len(concepts) if isinstance(concepts, list) else type(concepts).__name__}")
        res.ok = False
        return res

    total_subs = 0
    for c in concepts:
        if "name" not in c:
            res.errors.append(f"concept missing 'name' field: {c}")
            res.ok = False
        subs = c.get("subconcepts", [])
        if not isinstance(subs, list) or len(subs) < 1:
            res.errors.append(f"concept '{c.get('name','?')}' has no subconcepts")
            res.ok = False
        else:
            for s in subs:
                if "name" not in s:
                    res.errors.append(f"subconcept missing 'name': {s}")
                    res.ok = False
                total_subs += 1

    res.warnings.append(f"counted {len(concepts)} concepts, {total_subs} subconcepts")
    return res


# ---------------------------------------------------------------------
# Final dual-independent topology.json (the front-end-shaped file)
# ---------------------------------------------------------------------
def validate_dual_topology(topology_path: Path, expected_chapter_name: str | None = None) -> ValidationResult:
    """
    Validate the shape: {<Chapter Name>: {<Concept Name>: [<sub names>]}}
    matches acadza-history-demo/class9_history_chapter_1_topology.json.
    """
    res = ValidationResult(ok=True, stage="dual_topology")
    data, errs = _load_json(topology_path)
    if errs:
        res.errors.extend(errs)
        res.ok = False
        return res

    if not isinstance(data, dict) or len(data) != 1:
        res.errors.append("topology root must be a dict with exactly one chapter key")
        res.ok = False
        return res

    chapter_key = next(iter(data))
    if expected_chapter_name and chapter_key != expected_chapter_name:
        res.warnings.append(f"chapter key '{chapter_key}' != expected '{expected_chapter_name}'")

    concepts = data[chapter_key]
    if not isinstance(concepts, dict) or len(concepts) < 1:
        res.errors.append("chapter must contain >=1 concept entries (dict of concept->subs list)")
        res.ok = False
        return res

    for cname, subs in concepts.items():
        if not isinstance(subs, list) or len(subs) < 1:
            res.errors.append(f"concept '{cname}' must be a non-empty list of sub names")
            res.ok = False
        else:
            for s in subs:
                if not isinstance(s, str) or not s.strip():
                    res.errors.append(f"sub name under '{cname}' must be non-empty string, got {s!r}")
                    res.ok = False
    res.warnings.append(f"chapter '{chapter_key}' has {len(concepts)} concepts, {sum(len(v) for v in concepts.values())} subs")
    return res


# ---------------------------------------------------------------------
# Final dual-independent content.json (the front-end-shaped file)
# ---------------------------------------------------------------------
def validate_dual_content(
    content_path: Path,
    expected_chapter_name: str | None = None,
    require_subjectivetypes: bool = True,
) -> ValidationResult:
    """
    Validate the shape:
      {<Chapter Name>: {<Concept Name>: {<Sub Name>: {Summary, SCQs, SubjectiveTypes, Examples}}}}
    matches acadza-history-demo/french_society_schema.json (with the user's
    sealed bare-names convention - no 'Concept: X' prefix labels).
    """
    res = ValidationResult(ok=True, stage="dual_content")
    data, errs = _load_json(content_path)
    if errs:
        res.errors.extend(errs)
        res.ok = False
        return res

    if not isinstance(data, dict) or len(data) != 1:
        res.errors.append("content root must be a dict with exactly one chapter key")
        res.ok = False
        return res

    chapter_key = next(iter(data))
    if expected_chapter_name and chapter_key != expected_chapter_name:
        res.warnings.append(f"chapter key '{chapter_key}' != expected '{expected_chapter_name}'")

    # Reject "Concept: X" prefix labels (the sealed convention is bare names)
    if chapter_key.startswith("Concept:") or chapter_key.startswith("Subconcept:"):
        res.errors.append(f"chapter key '{chapter_key}' uses prefix label - convention is bare names")
        res.ok = False

    concepts = data[chapter_key]
    if not isinstance(concepts, dict) or len(concepts) < 1:
        res.errors.append("chapter must contain >=1 concept entries")
        res.ok = False
        return res

    required_sub_keys = {"Summary"}
    sub_total = 0
    scqs_total = 0
    examples_total = 0

    for cname, subs in concepts.items():
        if cname.startswith("Concept:") or cname.startswith("Subconcept:"):
            res.errors.append(f"concept key '{cname}' uses prefix label - convention is bare names")
            res.ok = False
        if not isinstance(subs, dict) or len(subs) < 1:
            res.errors.append(f"concept '{cname}' must contain >=1 subconcept entries")
            res.ok = False
            continue
        for sname, payload in subs.items():
            if sname.startswith("Subconcept:"):
                res.errors.append(f"sub key '{sname}' under '{cname}' uses prefix label")
                res.ok = False
            if not isinstance(payload, dict):
                res.errors.append(f"sub '{sname}' payload must be dict")
                res.ok = False
                continue
            missing = required_sub_keys - set(payload.keys())
            if missing:
                res.errors.append(f"sub '{sname}' missing required keys: {sorted(missing)}")
                res.ok = False
            summary = payload.get("Summary", {})
            if not isinstance(summary, dict) or not summary.get("Theory"):
                res.errors.append(f"sub '{sname}' Summary.Theory is empty")
                res.ok = False
            scqs = payload.get("SCQs", {})
            if isinstance(scqs, dict):
                scqs_total += len(scqs)
            ex = payload.get("Examples", {})
            if isinstance(ex, dict):
                examples_total += len(ex)
            if require_subjectivetypes and "SubjectiveTypes" not in payload:
                res.warnings.append(f"sub '{sname}' missing SubjectiveTypes block")
            sub_total += 1

    res.warnings.append(f"chapter '{chapter_key}': {len(concepts)} concepts, {sub_total} subs, {scqs_total} SCQs, {examples_total} examples")
    return res


# ---------------------------------------------------------------------
# Question records - shape check
# ---------------------------------------------------------------------
def validate_questions_list(questions: list[dict], required: tuple[str, ...] = ("question", "type")) -> ValidationResult:
    res = ValidationResult(ok=True, stage="questions_list")
    if not isinstance(questions, list):
        res.errors.append(f"expected list, got {type(questions).__name__}")
        res.ok = False
        return res
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            res.errors.append(f"question[{i}] is not a dict")
            res.ok = False
            continue
        for k in required:
            if k not in q or not q[k]:
                res.errors.append(f"question[{i}] missing or empty field: {k}")
                res.ok = False
    res.warnings.append(f"validated {len(questions)} questions")
    return res


if __name__ == "__main__":
    # Smoke test: confirm validators behave correctly on (a) a matching reference
    # and (b) a deliberately-mismatched legacy reference (must FAIL by design).
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    PROJECT = Path(__file__).resolve().parents[2]

    print("\n--- TEST 1: dual_topology validator on demo topology file ---")
    print("    expected: PASS (file matches the sealed shape)")
    demo_topo = PROJECT / "acadza-history-demo" / "class9_history_chapter_1_topology.json"
    r = validate_dual_topology(demo_topo)
    print(r.report())
    assert r.ok, "demo topology file should pass the validator"

    print("\n--- TEST 2: dual_content validator on LEGACY-FORMAT reference file ---")
    print("    expected: FAIL (file uses retired 'Concept:' prefixes + no chapter wrapper)")
    print("    this FAIL proves the validator gates retired formats out")
    demo_content = PROJECT / "acadza-history-demo" / "french_society_schema.json"
    r = validate_dual_content(demo_content)
    print(r.report())
    assert not r.ok, "legacy-format file should fail the validator (this is the gate)"

    print("\nstage_validators.py sanity checks PASSED (both behaviors verified)")
