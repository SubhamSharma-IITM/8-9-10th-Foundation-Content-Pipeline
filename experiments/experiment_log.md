# Experiment Log — NCERT 8-9-10 Content Pipeline

## Timeline

### 2026-03-24 — Project Initialization

**[00] Chapter Mapping** — COMPLETE
- Extracted NCERT Class 10 Science textbook (13 chapters, 2025-26 reprint)
- Mapped chapters to subjects: Chemistry (1-4), Biology (5-8), Physics (9-12), Environment (13)
- Extracted full back exercise answer key from jesc1an.pdf
- Selected Chapter 9 (Light: Reflection and Refraction) as stress test chapter
- Organized PDFs into subject-wise directory structure

**Research Completed:**

1. **Model Selection** — Proprietary models (Gemini 2.5 Flash + Claude) for quality. Open source (Qwen 2.5 72B, DeepSeek V3) insufficient for teacher-like quality (~80-85%).

2. **Retrieval Strategy** — NO RAG/BM25. Use Gemini context caching (cache full chapter, multiple queries at 90% discount). Existing Stage 2 pipeline already implements this.

3. **Generation Approach** — Hybrid: breadth-first topology, depth-first content per subconcept. 2-3 API calls per subconcept (theory+examples → MCQs → subjective) rather than one-shot. Evidence: output quality degrades past ~2000 tokens of structured content.

4. **Validation** — Layered: Pydantic schema enforcement + cross-model validation + deterministic checks. Schema validation may need second model pass (backbone of all content).

5. **Grounding** — Quote-then-generate pattern + line range citations + [INFERENCE] tagging. Prevents hallucination, ensures NCERT-faithful content.

6. **OCR Tools** — MinerU (0.968 CDM) slightly beats MathPix (0.951) on math. Free/open-source. MonkeyOCR (SOTA on OmniDocBench). Both need benchmarking on NCERT PDFs. Vector images in NCERT PDFs require rasterization approach.

7. **Question Philosophy (NCERT/CBSE):**
   - 50% competency-based (real-world application)
   - 20% MCQs (factual + conceptual)
   - 30% constructed response (short/long answer)
   - Bloom's taxonomy: Remember 15-20%, Understand 25-30%, Apply 25-30%, Analyze/HOTS 15-20%, Create 5-10%

**[Architecture Research] Transformer Attention & Thinking Budget** — COMPLETE
- "Lost in the Middle" (Liu et al., 2023): U-shaped attention — beginning (~60%) and end (~58%) well-attended, middle drops to ~40%. Applies to ALL models.
- Retrieval ≠ Comprehension. Models ace needle-in-haystack but struggle with comprehensive synthesis from long inputs. Our use case is comprehension.
- Thinking budget: Does NOT change input prefill processing. But thinking tokens create additional retrieval passes over cached input KV. Higher budget → better coverage of middle-context.
- From PROOF-READING-V5.0 empirical data: LOW budget = 0 thinking tokens (useless). MEDIUM (8192) = ~4,550 avg thinking tokens, 66% recall vs LOW's 50%.
- Model: `gemini-3-flash-preview` with MEDIUM thinking for content gen, HIGH for topology gen.
- Mitigation: Two-pass chunked extraction + section markers + instruction-before-context + explicit section checklist + deterministic coverage validation.

See: `experiments/research_transformer_architecture.md` for full details.

**[01] OCR Benchmark** — IN PROGRESS (2026-03-24)
- PyMuPDF baseline COMPLETE:
  - Text extraction: works but formulas BROKEN (positioned chars → `1 1 1 v u f + =`)
  - Image extraction: ALL 54 images are watermark backgrounds (black). Zero diagrams.
  - Reason: ALL diagrams are vector paths (2,536 path objects across 27 pages), NOT raster images.
  - Section headers duplicated 5x (PDF layering artifact)
  - Rasterization works: `get_pixmap(dpi=300)` renders clean pages with all diagrams
- MinerU: Model download in progress (~2-3 GB from HuggingFace). Will run once complete.
- MathPix: Need to run via Stage 1 API. Proven production tool.
- Key finding: NCERT is digital PDF (text selectable). Core differentiator is formula reconstruction.

**Decisions Pending:**
- [x] OCR benchmark: DECIDED — use MathPix (proven). MinerU deferred (model download issues, no API). PyMuPDF unusable for Physics (formulas break, diagrams are vector paths).
- [x] NCERT Question Philosophy: Ch9 analysis complete — 14 in-text Qs, 17 back exercises, 4 solved examples, 13 activities analyzed. Patterns documented.
- [x] Difficulty Definitions: Easy/Medium/Hard precisely defined with Bloom's mapping, CBSE distribution (30:50:20), examples per level. 3:3:2 split formula computed.
- [x] Question Count Algorithm: Assessable-concept-based estimation. Pre-computed hard caps for prompts. "Unique Cognitive Task" test for quality.
- [x] NCERT Philosophy: Constructivist approach, scaffolding sequence, "stay in the zone" principle documented.
- [x] MathPix Ch9 Output: 62K chars, 724 lines, all 6 formulas as LaTeX, 24 images extracted, 49 sections, 13 activities, 4 examples, 5 tables, full exercises.
- [x] CBSE 2025-26 SQP Analysis: Analyzed actual Class 10 paper (Science-SQP.pdf). Confirmed question types across classes 8-10. SEALED taxonomy.
- [x] Question Type Taxonomy SEALED: 2 main types (SCQ + Subjective). SCQ sub-formats: standard, assertion_reason, statement_selection. Subjective sub-formats: descriptive, numerical, diagram. Integer type INVALID. Class 8 simpler (no A-R, no case-based). Class 9-10 full range.
- [x] Mapping Approach: CONFIRMED Approach B (cached MMD + line ranges). Cost: $0.026/chapter, Rs 2.25. 31/31 questions mapped.
- [x] Solved Examples: 4 found in Ch9, extracted with Q+S, mapped to subconcepts by line range (no LLM needed).
- [ ] Topology generation: prompt design + model choice (ON HOLD — needs schema discussion)
- [ ] Content triplet generation: exact prompt templates
- [ ] isBackExercise flag: how model identifies back exercise questions
- [ ] VisualContent pipeline: image generation for intuitive questions
- [ ] Schema finalization for Physics (formulas, diagrams differ from History)
