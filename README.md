# 8-9-10th Foundation Content Pipeline

Production pipeline that consumes NCERT + Foundation chapter PDFs and emits structured,
validated, faculty-ready content for the Acadza platform.

**Status:** Phase 1 (Ch12 NCERT) shipped — 11/11 stages, ₹114.27, 73 items, 15 images.
Phase 2 (Foundation Ch4 competitive) next. Factory mode after.

See `INTERN_ONBOARDING.md` if you've just joined and have been assigned a branch.

## Architecture

```
[ NCERT PDF + Foundation PDF ]
        ↓
  MathPix OCR (Stage 1)
        ↓
  Topology extraction (Stage 2)        ─┐
        ↓                                │
  Back-exercise + in-text extract (3)  │  NCERT track
        ↓                                │
  LLM mapper (4)  →  Capacity (5)      │
        ↓                                │
  Classifier (6) → Content gen (7)     │
        ↓                                │
  Post-process (8) → Solutions (9)     │
        ↓                                │
  Image gen (10) → Assemble (11)       ─┘
        ↓
  Dual-format output: topology.json + content.json
        ↓
  [Phase 3] Proofread → Surgical → Platform payload
        ↓
[ Live on Acadza ]
```

A parallel **Competitive track** (C1–C11) runs on the Foundation PDF with the same discipline.
Both tracks emit independent schemas per `decision_dual_independent_schemas`.

## Quick start

```bash
# 1. Install deps
pip install -r requirements.txt

# 2. Copy .env.example -> .env, fill in keys
cp .env.example .env

# 3. Place source PDFs (NOT in repo — request from team)
mkdir -p faculty_review
# ... copy NCERT_Ch12_*.pdf and Foundation_Ch4_*.pdf into faculty_review/

# 4. Register chapter in src/common/chapter_config.py KNOWN_CHAPTERS
# (see existing ch12_magnetic_ncert entry as template)

# 5. Run a stage
python -m src.ocr.mathpix_ocr --chapter ch12_magnetic_ncert
# ...
python -m src.content_gen.stage11_assemble --chapter ch12_magnetic_ncert
```

Every paid stage prompts for confirmation via `src/common/cost_gate.py`. Validators gate
every stage transition (`src/common/stage_validators.py`).

## Core engineering disciplines (sealed)

1. **Never overwrite a stage output** without snapshot via `src/common/backup.py`.
2. **Never trigger a paid stage** without `confirm_spend()` confirmation.
3. **Never run stage N+1** if stage N's validator fails.
4. **Resume-safe per-sub saves** — every LLM-generated artifact written atomically.
5. **LLM provider cascade** — AI Studio → Vertex AI → Anthropic via `src/common/llm_client.py`.
6. **Source-data tolerance** — OCR artifacts handled defensively (e.g. `\S` in EXERCISES regex).

## Project layout

```
src/
  common/          chapter_config, backup, cost_gate, stage_validators, llm_client
  ocr/             MathPix OCR runner
  topology/        Concept/subconcept extraction, back-exercise extractor, mapper
  content_gen/     Per-sub content generation, classification, post-process, solutions, assembler, proofread, surgical
  image_gen/       Matplotlib + SVG codegen, AST sandbox, render gate
  competitive/     Competitive-track stages C1-C11
  validation/      Per-stage validators
  utils/           Misc helpers

tests/             57 unit tests on infra
scripts/           One-off utilities
schemas/           Pydantic models for content/topology
experiments/       Per-chapter outputs (gitignored bulk; cost log retained)
```

## Where to read next

- `PIPELINE_FLOW.md` — visual pipeline diagram
- `ROADMAP.md` — phased build plan
- `INTERN_ONBOARDING.md` — branch-by-branch task briefs
