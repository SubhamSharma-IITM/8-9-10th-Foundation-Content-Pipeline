"""
chapter_config.py - Single source of truth for per-chapter file paths.

Every pipeline script reads paths from a ChapterConfig instance, rather than
hardcoding 'ch09_*.json' / 'ch01_light_competitive.mmd' style strings.

Adding a new chapter = adding one entry to KNOWN_CHAPTERS.

Path layout matches the dual-independent schema decision (see
memory/decision_dual_independent_schemas.md):

  experiments/01_ocr_benchmarks/mathpix/<source_slug>/<source_slug>.mmd
  experiments/03_topology_generation/<source_slug>/                          (ncert mode)
  experiments/03_topology_generation/competitive/<source_slug>/              (competitive mode)
  experiments/04_subconcept_classification/<source_slug>/classified_budget.json
  experiments/05_content_generation/chapter_<chapter_id>_<slug>/<mode>/
      topology.json
      content.json
      per_subconcept/
      solutions/
      theory_per_subconcept/        (competitive only)

OCR + topology paths track per-source (NCERT PDF and Foundation PDF are
different sources). Content paths track per-canonical-chapter so both
modes' content for the same chapter sit under one chapter directory.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

PROJECT_ROOT = Path(__file__).resolve().parents[2]

Mode = Literal["ncert", "competitive"]


@dataclass(frozen=True)
class ChapterConfig:
    # canonical identity (mode-agnostic)
    chapter_id: str            # NCERT chapter number, e.g. "ch12" - drives content_dir for both modes
    slug: str                  # url-safe chapter name, e.g. "magnetic_effects_of_electric_current"
    chapter_name: str          # display name, e.g. "Magnetic Effects of Electric Current"
    class_level: str           # "Class 10"
    subject: str               # "Physics"
    mode: Mode                 # which mode this config drives

    # source-bound (varies per mode because NCERT and Foundation PDFs are different files)
    source_pdf: Path           # absolute path to the source PDF
    source_id: str             # e.g. "ch12" for NCERT, "foundation_ch4" for Foundation
    foundation_page_range: tuple[int, int] | None = None  # only for foundation/competitive sources

    # -------------------------------------------------------------------
    # derived slugs
    # -------------------------------------------------------------------
    @property
    def source_slug(self) -> str:
        """Source-identity slug, used for OCR/topology dirs that are bound to a specific PDF."""
        return f"{self.source_id}_{self.slug}"

    @property
    def chapter_slug(self) -> str:
        """Canonical (mode-agnostic) chapter directory name. Shared across modes for content_dir."""
        return f"chapter_{self.chapter_id}_{self.slug}"

    # -------------------------------------------------------------------
    # Stage 1 - OCR (source-bound)
    # -------------------------------------------------------------------
    @property
    def ocr_dir(self) -> Path:
        return PROJECT_ROOT / "experiments" / "01_ocr_benchmarks" / "mathpix" / self.source_slug

    @property
    def mmd_path(self) -> Path:
        return self.ocr_dir / f"{self.source_slug}.mmd"

    @property
    def ocr_status_path(self) -> Path:
        return self.ocr_dir / "mathpix_status.json"

    # -------------------------------------------------------------------
    # Stage 3 - topology + back-exercise + mapping (source-bound)
    # -------------------------------------------------------------------
    @property
    def topology_dir(self) -> Path:
        base = PROJECT_ROOT / "experiments" / "03_topology_generation"
        if self.mode == "competitive":
            return base / "competitive" / self.source_slug
        return base / self.source_slug

    @property
    def schema_path(self) -> Path:
        return self.topology_dir / "schema.json"

    @property
    def topology_json_source_path(self) -> Path:
        """Raw topology output from regex extractor (source-bound, intermediate)."""
        return self.topology_dir / "topology_raw.json"

    @property
    def line_ranges_path(self) -> Path:
        return self.topology_dir / "line_ranges.json"

    @property
    def exercises_path(self) -> Path:
        return self.topology_dir / "exercises.json"

    @property
    def mapped_path(self) -> Path:
        return self.topology_dir / "mapped.json"

    @property
    def unified_mapping_path(self) -> Path:
        return self.topology_dir / "unified_mapping.json"

    @property
    def image_codes_path(self) -> Path:
        return self.topology_dir / "image_codes.json"

    @property
    def budget_path(self) -> Path:
        return self.topology_dir / "generation_budget.json"

    # competitive-only intermediates
    @property
    def comp_questions_extracted_path(self) -> Path:
        return self.topology_dir / "questions_extracted.json"

    @property
    def comp_questions_cleaned_path(self) -> Path:
        return self.topology_dir / "questions_cleaned.json"

    @property
    def comp_questions_mapped_path(self) -> Path:
        return self.topology_dir / "questions_mapped.json"

    @property
    def comp_questions_pending_path(self) -> Path:
        return self.topology_dir / "questions_pending.json"

    @property
    def comp_extraction_cost_path(self) -> Path:
        return self.topology_dir / "extraction_cost.json"

    # -------------------------------------------------------------------
    # Stage 4 - subconcept classification (source-bound)
    # -------------------------------------------------------------------
    @property
    def classification_dir(self) -> Path:
        return PROJECT_ROOT / "experiments" / "04_subconcept_classification" / self.source_slug

    @property
    def classified_budget_path(self) -> Path:
        return self.classification_dir / "classified_budget.json"

    # -------------------------------------------------------------------
    # Stage 5 - content generation (mode-bound, but shared per chapter)
    # -------------------------------------------------------------------
    @property
    def content_dir(self) -> Path:
        return PROJECT_ROOT / "experiments" / "05_content_generation" / self.chapter_slug / self.mode

    @property
    def content_per_sub_dir(self) -> Path:
        return self.content_dir / "per_subconcept"

    @property
    def solutions_dir(self) -> Path:
        return self.content_dir / "solutions"

    @property
    def theory_per_subconcept_dir(self) -> Path:
        """Competitive-mode only - theory generated for each comp-mode subconcept."""
        return self.content_dir / "theory_per_subconcept"

    @property
    def topology_path(self) -> Path:
        """Final dual-format topology.json - matches acadza-history-demo shape."""
        return self.content_dir / "topology.json"

    @property
    def content_path(self) -> Path:
        """Final dual-format content.json - matches acadza-history-demo shape."""
        return self.content_dir / "content.json"

    # -------------------------------------------------------------------
    # Stage 6 - concept tree rollup (project-wide, not per-chapter)
    # -------------------------------------------------------------------
    @property
    def extended_concept_tree_path(self) -> Path:
        return PROJECT_ROOT / "experiments" / "06_concept_tree" / "acadza_concept_tree_extended.json"

    # -------------------------------------------------------------------
    # backups
    # -------------------------------------------------------------------
    @staticmethod
    def backups_dir(output_path: Path) -> Path:
        """Backup directory sibling to any stage output. The backup helper in
        src/common/backup.py uses this to snapshot a file before it gets overwritten."""
        return output_path.parent / "_backups"

    # -------------------------------------------------------------------
    # convenience
    # -------------------------------------------------------------------
    def ensure_dirs(self) -> None:
        """Pre-create all expected output directories. Safe to call repeatedly."""
        for d in [
            self.ocr_dir,
            self.topology_dir,
            self.classification_dir,
            self.content_dir,
            self.content_per_sub_dir,
            self.solutions_dir,
            self.theory_per_subconcept_dir,
            self.extended_concept_tree_path.parent,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def describe(self) -> str:
        return (
            f"ChapterConfig({self.subject}/{self.class_level}/{self.chapter_name} [{self.mode}])\n"
            f"  source_id    : {self.source_id}\n"
            f"  source_slug  : {self.source_slug}\n"
            f"  chapter_slug : {self.chapter_slug}\n"
            f"  source_pdf   : {self.source_pdf}\n"
            f"  mmd_path     : {self.mmd_path}\n"
            f"  content_dir  : {self.content_dir}\n"
            f"  topology_path: {self.topology_path}\n"
            f"  content_path : {self.content_path}\n"
        )


# ---------------------------------------------------------------------
# Registry of known chapters
# ---------------------------------------------------------------------
# Add a new entry here to make a chapter runnable through the pipeline.
# Convention: KEY is "<chapter_id>_<short_topic>_<mode>".

KNOWN_CHAPTERS: dict[str, ChapterConfig] = {
    # ---------------- Class 10 Physics ----------------
    "ch12_magnetic_ncert": ChapterConfig(
        chapter_id="ch12",
        slug="magnetic_effects_of_electric_current",
        chapter_name="Magnetic Effects of Electric Current",
        class_level="Class 10",
        subject="Physics",
        mode="ncert",
        source_pdf=PROJECT_ROOT
        / "data" / "ncert" / "class10" / "physics" / "pdfs"
        / "ch12_magnetic_effects_of_electric_current.pdf",
        source_id="ch12",
    ),
    "ch12_magnetic_competitive": ChapterConfig(
        chapter_id="ch12",
        slug="magnetic_effects_of_electric_current",
        chapter_name="Magnetic Effects of Electric Current",
        class_level="Class 10",
        subject="Physics",
        mode="competitive",
        source_pdf=PROJECT_ROOT
        / "data" / "foundation" / "class10" / "physics" / "pdfs"
        / "foundation_ch4_magnetic_effects_of_electric_current.pdf",
        source_id="foundation_ch4",
        foundation_page_range=(218, 283),
    ),
}


def load(key: str) -> ChapterConfig:
    """Look up a chapter config by registry key. Raises KeyError if unknown."""
    if key not in KNOWN_CHAPTERS:
        known = "\n  ".join(sorted(KNOWN_CHAPTERS.keys()))
        raise KeyError(f"Unknown chapter '{key}'. Known keys:\n  {known}")
    return KNOWN_CHAPTERS[key]


def list_keys() -> list[str]:
    return sorted(KNOWN_CHAPTERS.keys())


if __name__ == "__main__":
    # Sanity check - print path resolutions for all known chapters
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for key in list_keys():
        cfg = load(key)
        print(f"\n=== {key} ===")
        print(cfg.describe())
