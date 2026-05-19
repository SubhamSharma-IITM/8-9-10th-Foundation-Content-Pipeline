"""Unit tests for src/common/stage_validators.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.common.stage_validators import (
    ValidationResult,
    validate_dual_content,
    validate_dual_topology,
    validate_mmd,
    validate_questions_list,
    validate_topology_schema,
)


class TestValidateMMD:
    def test_missing_file_fails(self, tmp_path):
        r = validate_mmd(tmp_path / "nope.mmd")
        assert not r.ok
        assert any("missing" in e for e in r.errors)

    def test_too_few_lines_fails(self, tmp_path):
        p = tmp_path / "tiny.mmd"
        p.write_text("\\section*{One}\n" * 5, encoding="utf-8")
        r = validate_mmd(p, min_lines=100)
        assert not r.ok

    def test_too_few_sections_fails(self, tmp_path):
        p = tmp_path / "few.mmd"
        # plenty of lines, but only 1 section
        p.write_text("\\section*{Only one}\n" + "blank\n" * 200, encoding="utf-8")
        r = validate_mmd(p, min_lines=100, min_sections=3)
        assert not r.ok

    def test_valid_mmd_passes(self, tmp_path):
        p = tmp_path / "good.mmd"
        content = "\\section*{One}\n" + "body line\n" * 200 + "\\section*{Two}\n\\section*{Three}\n"
        p.write_text(content, encoding="utf-8")
        r = validate_mmd(p)
        assert r.ok, r.report()

    def test_warns_on_known_artifacts(self, tmp_path):
        p = tmp_path / "artifacts.mmd"
        content = "\\section*{A}\n\\section*{B}\n\\section*{C}\n" + "line\n" * 200 + "use \\and stuff\n\\text {bad}"
        p.write_text(content, encoding="utf-8")
        r = validate_mmd(p)
        assert r.ok  # warnings don't break validity
        assert any("\\and" in w for w in r.warnings)
        assert any("\\text {" in w for w in r.warnings)


class TestValidateTopologySchema:
    def test_valid_schema_passes(self, tmp_path):
        p = tmp_path / "schema.json"
        p.write_text(json.dumps({
            "concepts": [
                {"name": "C1", "subconcepts": [{"name": "S1"}, {"name": "S2"}]},
                {"name": "C2", "subconcepts": [{"name": "S3"}]},
            ]
        }), encoding="utf-8")
        r = validate_topology_schema(p)
        assert r.ok, r.report()

    def test_missing_subs_fails(self, tmp_path):
        p = tmp_path / "schema.json"
        p.write_text(json.dumps({"concepts": [{"name": "C1", "subconcepts": []}]}), encoding="utf-8")
        r = validate_topology_schema(p)
        assert not r.ok

    def test_invalid_json_fails(self, tmp_path):
        p = tmp_path / "broken.json"
        p.write_text("{not valid", encoding="utf-8")
        r = validate_topology_schema(p)
        assert not r.ok


class TestValidateDualTopology:
    def test_valid_passes(self, tmp_path, minimal_topology_data):
        p = tmp_path / "topology.json"
        p.write_text(json.dumps(minimal_topology_data), encoding="utf-8")
        r = validate_dual_topology(p)
        assert r.ok, r.report()

    def test_two_chapter_keys_fails(self, tmp_path):
        p = tmp_path / "topology.json"
        p.write_text(json.dumps({"Ch A": {"C": ["S"]}, "Ch B": {"C": ["S"]}}), encoding="utf-8")
        r = validate_dual_topology(p)
        assert not r.ok

    def test_empty_concept_fails(self, tmp_path):
        p = tmp_path / "topology.json"
        p.write_text(json.dumps({"Chapter": {"C1": []}}), encoding="utf-8")
        r = validate_dual_topology(p)
        assert not r.ok

    def test_expected_chapter_name_warning(self, tmp_path, minimal_topology_data):
        p = tmp_path / "topology.json"
        p.write_text(json.dumps(minimal_topology_data), encoding="utf-8")
        r = validate_dual_topology(p, expected_chapter_name="Wrong Name")
        assert r.ok  # warnings don't fail
        assert any("Wrong Name" in w for w in r.warnings)


class TestValidateDualContent:
    def test_valid_passes(self, tmp_path, minimal_content_data):
        p = tmp_path / "content.json"
        p.write_text(json.dumps(minimal_content_data), encoding="utf-8")
        r = validate_dual_content(p)
        assert r.ok, r.report()

    def test_concept_prefix_label_rejected(self, tmp_path, minimal_content_data):
        """The retired 'Concept: X' / 'Subconcept: Y' prefix label format must fail."""
        legacy = {
            "Magnetic Effects": {
                "Concept: Magnetic Field": {
                    "Magnetic Field": {
                        "Summary": {"Theory": "T"},
                    }
                }
            }
        }
        p = tmp_path / "content.json"
        p.write_text(json.dumps(legacy), encoding="utf-8")
        r = validate_dual_content(p)
        assert not r.ok
        assert any("prefix" in e for e in r.errors)

    def test_missing_summary_theory_fails(self, tmp_path):
        bad = {
            "Chapter": {
                "Concept": {
                    "Sub": {"Summary": {"Theory": ""}}
                }
            }
        }
        p = tmp_path / "content.json"
        p.write_text(json.dumps(bad), encoding="utf-8")
        r = validate_dual_content(p)
        assert not r.ok

    def test_multiple_root_keys_fails(self, tmp_path):
        bad = {"A": {}, "B": {}}
        p = tmp_path / "content.json"
        p.write_text(json.dumps(bad), encoding="utf-8")
        r = validate_dual_content(p)
        assert not r.ok


class TestValidateQuestionsList:
    def test_valid_passes(self):
        qs = [
            {"question": "Q1", "type": "scq"},
            {"question": "Q2", "type": "subjective"},
        ]
        assert validate_questions_list(qs).ok

    def test_missing_field_fails(self):
        qs = [{"question": "Q1"}]
        r = validate_questions_list(qs)
        assert not r.ok

    def test_empty_field_fails(self):
        qs = [{"question": "", "type": "scq"}]
        r = validate_questions_list(qs)
        assert not r.ok

    def test_non_list_fails(self):
        r = validate_questions_list({"not": "a list"})
        assert not r.ok
