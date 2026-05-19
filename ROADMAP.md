# ROADMAP — NCERT 8-9-10 Content Generation Pipeline

## What Is Established (Ready to Execute)

### Architecture
- **Model**: Gemini 2.5 Flash (primary, cheapest with context caching) + Claude (quality-critical)
- **No RAG/BM25** — context caching beats retrieval for single-chapter comprehensive processing
- **Existing infra**: Stage 2 (Gemini/Anthropic cached extraction) + Stage 9 (3-pass QA) patterns reusable from `D:\ACADZA_WORK\Question Uploading App\app\pipeline`

### Data Organization
```
data/ncert/class10/
├── chapter_mapping.json         # Complete chapter→subject map + answer keys
├── chemistry/pdfs/ch01-04.pdf
├── biology/pdfs/ch05-08.pdf
├── physics/pdfs/ch09-12.pdf
└── environment/pdfs/ch13.pdf
```

### Generation Strategy
- **Topology first** (breadth-first): Chapter → Concepts → Subconcepts + line ranges + size flags
- **Content depth-first**: Per subconcept → Theory+Examples (call 1) → SCQs (call 2) → Subjective (call 3)
- **Review pass** (breadth-first): Full chapter coherence check
- **Thin concept buffer**: < 20 source lines → reduced question counts (2-3 SCQs, 1-2 subj, 1-2 examples)

### Schema (from reference repo)
```
Chapter → Concept → Subconcept → {
  Summary: { Theory, VisualContent: { Needed, Content: { IMAGE_ID: description } } },
  SCQs: { Question N: { isBackExercise, Difficulty, Question, Options, Correct Option, Solution, VisualContent } },
  SubjectiveTypes: { Question N: { isBackExercise, Difficulty, Question, Solution, VisualContent } },
  Examples: { Example N: { isSolvedExample, Question, Solution, VisualContent } }
}
```

### Validation
- L1: Pydantic schema enforcement (structural)
- L2: Deterministic (4 options, answer valid, no dupes, formulas consistent)
- L3: Cross-model (cheaper model checks factual accuracy + source grounding)
- L4: Back-exercise match (against extracted NCERT answer key)

### Grounding
- Line-decorated source text
- Quote-then-generate pattern
- Line range citations per paragraph
- [INFERENCE] tagging for beyond-source content
- Grade-level scope boundary

### Cost
- ~$0.42/chapter (Gemini Flash + context caching)
- ~$42 for 100 chapters across classes 8-9-10

---

## What's Next (Experimentation Phase)

### Experiment 01: OCR Benchmark
- [ ] Run MinerU on Chapter 9 PDF
- [ ] Run MathPix on Chapter 9 PDF (or use existing Stage 1)
- [ ] Compare: math formula accuracy, image extraction, diagram handling
- [ ] Decide OCR tool for pipeline
- [ ] Handle vector image artifacts in NCERT PDFs

### Experiment 02: Topology Generation
- [ ] Design topology prompt with line ranges + size flags
- [ ] Test on Chapter 9 (hardest: reflection + refraction combined)
- [ ] Validate concept distribution (even across chapter, not front-heavy)
- [ ] Cross-model validate topology
- [ ] Finalize topology schema for Physics (formulas, diagrams, sign conventions)

### Experiment 03: Content Generation
- [ ] NCERT question philosophy deep-dive (SCQ types, difficulty calibration)
- [ ] Design one-shot exemplars for each question type
- [ ] Test theory generation (grounded, teacher-like tone)
- [ ] Test SCQ generation (plausible distractors, NCERT style)
- [ ] Test subjective + solved examples
- [ ] isBackExercise identification accuracy
- [ ] VisualContent flagging accuracy

### Experiment 04: Schema + Quality Validation
- [ ] Pydantic models for all content types
- [ ] Deterministic validation suite
- [ ] Cross-model validation prompts
- [ ] Back-exercise matching pipeline
- [ ] End-to-end quality assessment on Chapter 9

### Post-Experimentation
- [ ] Scale to all Class 10 Physics chapters (9-12)
- [ ] Scale to Class 10 Chemistry, Biology
- [ ] Adapt for Class 8, 9 textbooks
- [ ] Image generation pipeline (matplotlib/Gemini for diagrams)
- [ ] Platform API integration (user will provide)
- [ ] MongoDB schema + upload pipeline
