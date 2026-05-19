# Intern Onboarding — 8-9-10th Foundation Content Pipeline

Welcome. You've been assigned **one or more of four branches** below. Each is scoped to
~2–5 days of work. Read this whole file once before opening your first PR.

## Setup (every branch)

```bash
# Clone
git clone https://github.com/SubhamSharma-IITM/8-9-10th-Foundation-Content-Pipeline.git
cd 8-9-10th-Foundation-Content-Pipeline

# Python 3.11+
python -m venv .venv
.\.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # mac/linux

pip install -r requirements.txt

# Secrets (request from Subham — never commit)
cp .env.example .env

# Run the test suite to confirm setup
pytest tests/ -q
# Expect: 57 tests passing
```

Source PDFs (`data/`, `ncert_raw/`, `faculty_review/`) and the 14GB `models/` folder are
**not in git**. Request them from Subham via a non-git transfer.

## Rules you MUST follow

1. **One branch per task. Push to your own branch only.** Never push to `main`.
2. **Open a PR** when done, link this onboarding file's task ID, and request review.
3. **Never hardcode API keys.** Always `os.environ.get('FOO_KEY')` after `dotenv.load_dotenv()`.
4. **Don't commit large files** (>5 MB). Check `git status` before every commit.
5. **Don't run paid stages** (MathPix, Gemini) without explicit GO. The cost gate at
   `src/common/cost_gate.py` will block you — that's intentional.
6. **Read the existing memory of conventions** before starting:
   - `decision_dual_independent_schemas` shape — NCERT and Competitive trees are parallel and independent
   - `feedback_no_fabricated_metadata` — never invent field names / enum values / pricing / pattern codes from thin air
   - `pipeline_stages_testing_discipline` — every stage has a validator
   - These are in memory the lead will share — ask if you don't have them.

---

## Branch 1 — `feat/observability` (Langfuse wiring, Gap 2)

**Goal:** Every LLM call across the pipeline emits a trace to Langfuse (self-hosted).
Dashboards become possible. Replaces the append-only `_cost_log.jsonl`.

**Why:** At 100 chapters we can't debug cost/latency spikes by grepping a JSONL file.
Industry-standard observability.

**Deliverables**
1. Docker-compose for self-hosted Langfuse (Postgres + Langfuse server, local only)
2. Wire `src/common/llm_client.py` to wrap every Gemini/Anthropic call with a Langfuse `@observe`
3. Each trace must include: chapter_key, stage, model, thinking_level, input tokens, output tokens, latency_ms, cost_inr, error_class (if any), prompt template name
4. Backward-compat: keep `_cost_log.jsonl` writing AS WELL (don't break existing pipeline)
5. README section: "Running Langfuse locally"
6. Tests: extend `tests/test_cost_gate.py` to assert traces emitted in mock-Langfuse mode

**Acceptance**
- Run `python -m src.ocr.mathpix_ocr --chapter ch12_magnetic_ncert --dry-run` and screenshot Langfuse showing the trace
- Run real Gemini call and screenshot trace with all fields populated
- All existing tests still pass

**Estimated effort:** 3–5 days

---

## Branch 2 — `feat/upload-converter` (Task #59)

**Goal:** Convert our dual-format `content.json` + `topology.json` into the
Question Uploading App's stage-2/4/7 platform payload format.

**Why:** This is the "last mile" before content reaches the Acadza platform. Without it
our output is rich JSON nobody can ingest.

**Reference schema:** Ask Subham for `reference_qua_schema_for_upload_converter` memory.
It documents the exact target shape (questionType enum, options array, answer fields,
matchQuestion rows, etc.).

**Deliverables**
1. New module: `src/upload/build_platform_payload.py`
2. CLI: `python -m src.upload.build_platform_payload --chapter ch12_magnetic_ncert`
3. Output: `experiments/05_content_generation/<chapter>/platform_payload.json`
4. Handles all 5 question types: scq, mcq, integerQuestion, passageQuestion, matchQuestion
5. Maps our SCQ → platform `scq`; our Subjective-Numerical → `integerQuestion`; our Subjective-Descriptive → flagged for review (per Task #56, no clean slot exists yet — produce a warning log, don't fail)
6. Validates output shape with Pydantic — schema model in `schemas/platform_payload.py`
7. Tests: round-trip a known-good Ch12 content.json and assert payload validates

**Open question:** `isFoundation` field on competitive items — backend coordination
pending (Task #55). For now, hardcode `isFoundation=true` for items from competitive
track, `false` for NCERT. Document this as a TODO comment with task ref.

**Acceptance**
- Convert Ch12 NCERT content.json end-to-end, no validation errors
- Convert Foundation Ch4 content.json (when it lands from Phase 2) end-to-end
- 1 dry-run smoke test + 1 real conversion shown in PR description

**Estimated effort:** 3 days

---

## Branch 3 — `fix/ui-bugs` (7 bugs in review HTML)

**Goal:** Fix 7 documented UI bugs in the Ch1/Ch12 interactive review HTML.

**Why:** Faculty review is blocked on these bugs. Hard blockers: bugs 2 (\\n rendering)
and 6 (LaTeX in solutions) — they affect every question.

**Reference:** Ask Subham for `ui_bugs_pending` memory — it has all 7 bugs with
symptoms, likely causes, and suggested fixes.

**Files:**
- `review/index.html` (or wherever the review HTML lives — check `review/` dir)
- May involve fixing the option parser, MathJax retypeset hooks, and image placement logic

**Deliverables**
1. All 7 bugs fixed, in priority order from the memory file
2. Manual test screenshots showing each bug fixed (before/after)
3. Test on real Ch12 content + Ch1 content (both should render correctly)

**Acceptance**
- Open the review HTML in Chrome, verify each fixed bug
- Resize browser to mobile width — header layout correct (bug 7)
- Click a solution panel — LaTeX renders inside (bug 6)

**Estimated effort:** 2 days

---

## Branch 4 — `fix/post-process` (cosmetic regex fixes)

**Goal:** Two small fixes in the post-processor that are documented and well-scoped.

**Reference:** `finding_assembler_cosmetic_issues` memory (ask Subham).

**Fix 1 — Strip example solution meta-prefix**
- LLM-generated example solutions often start with "This is a descriptive example.\\n"
- Add regex strip in `src/content_gen/post_process.py::post_process_content`:
  ```python
  content_str = re.sub(
      r'"solution"\s*:\s*"This is a (descriptive|numerical|diagram) example\.\s*\\n?',
      r'"solution": "',
      content_str
  )
  ```

**Fix 2 — LaTeX validator false positive**
- Current `validate_latex()` in `post_process.py` flags compliant content as non-compliant
  when no `\\(` markers present
- Wrong logic for non-numerical chapters (which legitimately have no math)
- Change rule to: `latex_compliant = not has_dollar` (no $ signs = compliant, presence of `\\(` is bonus)

**Fix 3 — VisualContent over-linking in stage11_assemble**
- Every question's `VisualContent.Content` dict gets ALL sub's image codes with empty
  descriptions. Should filter to just the question's own images.
- Pass the question's `idx` and `scope` from `_build_*_record` callers into
  `_question_visual_content`. Match against `ref_key = f"{kind}:{sid}:{idx}:{scope}"`.
- One file, ~15 lines.

**Deliverables**
1. All 3 fixes in `src/content_gen/post_process.py` + `src/content_gen/stage11_assemble.py`
2. Unit tests in `tests/` showing before/after on known fixtures
3. Re-run stage 8 + stage 11 on Ch12 NCERT, screenshot the diff

**Acceptance**
- Tests pass
- Ch12 content.json after re-run has no meta-prefix on example solutions
- LaTeX validator no longer false-positives on Ch12 (mostly non-numerical)
- VisualContent on Ch12 questions only references that question's own images

**Estimated effort:** 0.5–1 day

---

## How to ask for help

1. **Stuck on environment / setup?** Reply in the thread with full error output.
2. **Stuck on a code question?** Quote the file + line, paste relevant code, describe what you tried.
3. **Found something wrong with this brief?** Push back — the brief can be wrong. Better to clarify than implement the wrong thing.
4. **Hit a paid stage in your local testing?** Don't run it. We have shared dry-run fixtures
   (`tests/fixtures/`) that let you exercise the path without real API calls.

## PR checklist (every PR you open)

- [ ] Branch name matches the task above
- [ ] Linked to the task ID in PR description
- [ ] No `.env` or credentials committed (`git diff main -- .env` empty)
- [ ] No files >5 MB added
- [ ] `pytest tests/ -q` passes locally
- [ ] At least 1 screenshot or test output proving it works
- [ ] Self-review the diff before requesting review

Welcome aboard.
