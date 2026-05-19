# Research Findings — Content Generation Pipeline

**Date:** 2026-03-24
**Status:** Phase 0 Research Complete. Ready for experimentation.

---

## 1. One-Shot vs Iterative Generation

### Finding: 2-3 calls per subconcept beats one-shot

**Evidence:**
- Transformer attention dilutes across longer output prefixes — later items in structured output become generic/shorter ("generation fatigue")
- Anthropic + OpenAI both recommend decomposition for complex structured outputs
- Med-PaLM 2 (Singhal et al., 2023): staged generation (generate → critique → refine) outperforms single-pass on factual accuracy
- The degradation threshold: ~2000-3000 output tokens for structured content

**Recommended split:**
| Call | Content | Mode |
|------|---------|------|
| Call 1 | Theory + Solved Examples | Explanatory mode |
| Call 2 | SCQs (5 or buffer-adjusted) | Adversarial/assessment mode (distractors) |
| Call 3 | Subjective questions (3 or buffer-adjusted) | Open-ended assessment mode |

**Exception:** If subconcept is thin (< 20 source lines), one-shot is fine since total output will be under ~1500 tokens.

---

## 2. Breadth-First vs Depth-First

### Finding: Hybrid is optimal

**Breadth-first problems:**
- Content drift across subconcepts (each API call is stateless)
- Repetition increases without seeing prior generated content
- Cross-referencing between theory/questions/examples breaks

**Depth-first problems:**
- Later subconcepts may get less creative attention if all prior context is passed
- Cross-topic connections ("as we saw in section X") harder

**Recommended hybrid:**
1. **Breadth-first OUTLINE** (Phase 1): Generate full chapter topology — all concepts, subconcepts, line ranges, size flags. Cheap, short output.
2. **Depth-first CONTENT** (Phase 2): For each subconcept, generate theory → questions → examples. Pass only the outline + current concept context (not all prior content).
3. **Breadth-first REVIEW** (Phase 3): One final pass reviewing all content for gaps, repetitions, coherence.

This mirrors how curriculum designers actually work (ADDIE model, Understanding by Design).

---

## 3. Schema Validation

### Finding: Layered validation, not single-method

| Layer | What | How | Cost |
|-------|------|-----|------|
| **L1: Structural** | Fields, types, counts | Pydantic/JSON schema enforcement | Free (code) |
| **L2: Deterministic** | 4 options per MCQ, answer in options, no dupes, formulas in theory appear in questions | Python checks | Free (code) |
| **L3: Cross-model** | Factual accuracy, source grounding, difficulty calibration, distractor quality | Cheaper model validates | ~10% of gen cost |
| **L4: Back-exercise match** | isBackExercise flag correct | Compare against extracted answer key | Free (code) |

**Schema (topology) specifically:** Since topology is the backbone, cross-model validation is warranted. Generate with Gemini, validate with Claude (or vice versa). Cost is low since topology is short output.

---

## 4. Grounding Techniques

### Finding: Quote-then-generate + line citations + inference tagging

**Most effective combination:**
1. **Line-decorated source** (already in Stage 2): `Line_XXXXX: content`
2. **Quote-then-generate**: Force model to extract relevant quotes FIRST, then generate based on quotes only
3. **Line range citations**: Every generated paragraph must cite source lines → programmatically verifiable
4. **[INFERENCE] tag**: Model self-reports when going beyond source material
5. **Scope boundary**: Maintain grade-level concept list — flag if model introduces Class 12 concepts in Class 10 content

**For back exercises specifically:**
- Extract actual back exercise questions from chapter during OCR
- Model must match subconcept → back exercise question (grounded, not invented)
- isBackExercise=true only if question text matches actual NCERT exercise

---

## 5. NCERT Question Philosophy

### Finding: Activity-based, progressive complexity, real-world grounded

**From NCERT preface itself:**
- "The emphasis is not on definitions and technical terms, but on the concepts involved"
- "The entire approach of the book is activity-based"
- "Solved examples are provided to clarify a concept"
- "In-text questions after a main section check understanding"
- "Multiple difficulty levels in exercises"
- "More to Know" boxes — non-evaluative advanced material

**CBSE exam pattern (2024-25+):**
- 50% competency-based (case studies, real-world scenarios)
- 20% objective (MCQs)
- 30% constructed response

**Question type distribution for our content:**
| Type | Count per subconcept | Cognitive levels |
|------|---------------------|-----------------|
| SCQs | 5 (default), 2-3 (thin concepts) | Mix: 1 factual, 2 conceptual, 1 application, 1 HOTS |
| Subjective | 3 (default), 1-2 (thin) | 1 short answer (understanding), 1 long answer (application), 1 HOTS |
| Solved Examples | 3 (default), 1-2 (thin) | Progressive difficulty with worked steps |

---

## 6. OCR Tool Comparison

| Tool | Math OCR (CDM) | Image Extraction | Cost | NCERT Suitability |
|------|---------------|-----------------|------|-------------------|
| **MinerU** | 0.968 | Good (raster) | Free | High — benchmark needed |
| **MathPix** | 0.951 | Good | Paid ($) | High — production proven |
| **MonkeyOCR** | SOTA (OmniDocBench) | Yes | Free | High — newest option |
| **Marker** | Good | Yes | Free | Medium (English only) |

**Decision:** Benchmark MinerU vs MathPix on Chapter 9 before committing. If MinerU quality is within 5% of MathPix, use MinerU (free) for this pipeline.

**Vector image challenge:** NCERT PDFs contain vector-encoded diagrams. Extraction may produce gibberish. Solution: rasterize diagram regions at 300 DPI via layout detection.

---

## 7. Cost Estimation (Per Chapter)

**Using Gemini 2.5 Flash + Context Caching:**

| Step | Input tokens | Output tokens | Cost |
|------|-------------|---------------|------|
| Cache chapter (~40 pages) | ~30K | — | $0.009 |
| Topology generation | cached (90% off) | ~2K | $0.006 |
| Content gen (~15 subconcepts × 3 calls) | cached × 45 | ~3K × 45 | $0.35 |
| Validation pass | ~2K per subconcept × 15 | ~500 × 15 | $0.05 |
| **Total per chapter** | | | **~$0.42** |

**Scaling to all Class 10 Science (13 chapters):** ~$5.50
**Scaling to all 8-9-10 PCMB (~100 chapters):** ~$42

This is extremely cost-efficient. Even with Claude for quality-critical passes, total stays under $100.

---

## 8. VisualContent & Image Generation

### Three categories:
1. **Source-referenced images**: Diagram from chapter itself → extract during OCR, reference by figure number
2. **Cross-referenced images**: Question needs image from different section → link via figure reference
3. **Generated images**: Intuitive questions needing NEW diagrams (FBDs, circuit diagrams, ray diagrams)

**Generation approaches:**
- **Python libraries (free)**: matplotlib, plotly for graphs/charts; schemdraw for circuits; tikz-like for geometry
- **Gemini image gen**: For complex/realistic diagrams
- **Separate pipeline**: Run AFTER content generation, using VisualContent.Content descriptions as prompts

**Decision:** Defer image generation pipeline. First master text content. Mark all VisualContent.Needed=true cases and process them in a dedicated pass.
