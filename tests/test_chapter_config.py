"""Unit tests for src/common/chapter_config.py."""
from __future__ import annotations

import pytest

from src.common.chapter_config import (
    ChapterConfig,
    KNOWN_CHAPTERS,
    PROJECT_ROOT,
    load,
    list_keys,
)


class TestRegistry:
    def test_known_chapters_not_empty(self):
        assert len(KNOWN_CHAPTERS) >= 2

    def test_ch12_both_modes_registered(self):
        keys = list_keys()
        assert "ch12_magnetic_ncert" in keys
        assert "ch12_magnetic_competitive" in keys

    def test_load_unknown_raises(self):
        with pytest.raises(KeyError) as exc_info:
            load("does_not_exist")
        assert "ch12_magnetic_ncert" in str(exc_info.value)  # err lists known keys


class TestNCERTConfig:
    def setup_method(self):
        self.cfg = load("ch12_magnetic_ncert")

    def test_mode(self):
        assert self.cfg.mode == "ncert"

    def test_canonical_identity(self):
        assert self.cfg.chapter_id == "ch12"
        assert self.cfg.subject == "Physics"
        assert self.cfg.class_level == "Class 10"

    def test_source_pdf_under_ncert_dir(self):
        assert "ncert" in str(self.cfg.source_pdf).lower()
        assert self.cfg.source_pdf.name == "ch12_magnetic_effects_of_electric_current.pdf"

    def test_source_pdf_exists_on_disk(self):
        assert self.cfg.source_pdf.exists(), f"NCERT Ch12 PDF must be present: {self.cfg.source_pdf}"

    def test_mmd_path_under_source_slug(self):
        assert self.cfg.source_slug == "ch12_magnetic_effects_of_electric_current"
        assert self.cfg.mmd_path.parent.name == self.cfg.source_slug
        assert self.cfg.mmd_path.suffix == ".mmd"

    def test_content_dir_uses_chapter_slug(self):
        assert "chapter_ch12_" in str(self.cfg.content_dir)
        assert self.cfg.content_dir.name == "ncert"
        # Final filenames match sealed convention
        assert self.cfg.topology_path.name == "topology.json"
        assert self.cfg.content_path.name == "content.json"


class TestCompetitiveConfig:
    def setup_method(self):
        self.cfg = load("ch12_magnetic_competitive")

    def test_mode(self):
        assert self.cfg.mode == "competitive"

    def test_source_id_is_foundation(self):
        assert self.cfg.source_id == "foundation_ch4"

    def test_foundation_page_range(self):
        assert self.cfg.foundation_page_range == (218, 283)

    def test_source_pdf_under_foundation_dir(self):
        assert "foundation" in str(self.cfg.source_pdf).lower()

    def test_source_pdf_exists_on_disk(self):
        assert self.cfg.source_pdf.exists(), f"Foundation Ch4 PDF must be present: {self.cfg.source_pdf}"

    def test_topology_dir_is_under_competitive(self):
        assert "competitive" in str(self.cfg.topology_dir)


class TestModeSharingChapterSlug:
    """Both modes for the same chapter share content root, differ only by mode subdir."""

    def test_chapter_slugs_match(self):
        ncert = load("ch12_magnetic_ncert")
        comp = load("ch12_magnetic_competitive")
        assert ncert.chapter_slug == comp.chapter_slug

    def test_content_dirs_share_parent(self):
        ncert = load("ch12_magnetic_ncert")
        comp = load("ch12_magnetic_competitive")
        assert ncert.content_dir.parent == comp.content_dir.parent
        assert ncert.content_dir.name == "ncert"
        assert comp.content_dir.name == "competitive"

    def test_source_slugs_differ(self):
        ncert = load("ch12_magnetic_ncert")
        comp = load("ch12_magnetic_competitive")
        assert ncert.source_slug != comp.source_slug


class TestEnsureDirs:
    def test_ensure_dirs_creates_all(self, tmp_path, monkeypatch):
        # Build a config pointing at a temp dir so we don't pollute real experiments/
        import src.common.chapter_config as cc

        monkeypatch.setattr(cc, "PROJECT_ROOT", tmp_path)

        cfg = ChapterConfig(
            chapter_id="chTEST",
            slug="test_chapter",
            chapter_name="Test Chapter",
            class_level="Class 10",
            subject="Physics",
            mode="ncert",
            source_pdf=tmp_path / "test.pdf",
            source_id="chTEST",
        )
        cfg.ensure_dirs()
        assert cfg.ocr_dir.exists()
        assert cfg.topology_dir.exists()
        assert cfg.content_dir.exists()
        assert cfg.content_per_sub_dir.exists()
        assert cfg.solutions_dir.exists()


class TestBackupsDir:
    def test_backups_dir_sibling_to_output(self, tmp_path):
        out = tmp_path / "stage_out" / "topology.json"
        assert ChapterConfig.backups_dir(out) == out.parent / "_backups"
