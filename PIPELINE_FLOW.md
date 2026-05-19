# Production Pipeline Flow — NCERT Content Generation

**Version:** 1.0 — Sealed 2026-03-25
**Validated on:** Chapter 9 (Light — Reflection and Refraction)

---

## Stage 0: Source Ingestion
```
Input:  NCERT chapter PDF
Output: MathPix MMD + extracted images (JPGs)
Tool:   MathPix API (Stage 1 pattern from reference pipeline)
```

## Stage 1: Topology Extraction [DETERMINISTIC — no model]
```
Input:  MMD file
Output: ch_schema.json (database-ready)
        ch_topology.json (internal — IDs, tiers)
        ch_line_ranges.json (internal — line ranges, density)
        ch_image_codes.json (internal — image code mapping)
Tool:   src/topology/extractor.py
```

## Stage 2: Exercise Extraction [DETERMINISTIC — no model]
```
Input:  MMD file + chapter answer key
Output: ch_exercises.json (back exercises + in-text questions + solved examples)
        Edge cases flagged separately
Tool:   src/topology/back_exercise_extractor.py
```

## Stage 3: Exercise Mapping + Difficulty Tagging [MODEL — Gemini 3.1 Pro]
```
Input:  ch_exercises.json + ch_schema.json + ch_line_ranges.json + cached MMD
Output: ch_unified_mapping.json (all items mapped to subconcepts with difficulty + full question text)
Tool:   src/topology/exercise_mapper.py (Approach B — cached MMD + line ranges)
Note:   Solved examples mapped by code (line range) — no LLM needed for them
```

## Stage 4: Capacity Computation [DETERMINISTIC — no model]
```
Input:  ch_line_ranges.json + ch_unified_mapping.json
Output: ch_generation_budget.json (per subconcept: questions to generate, examples to generate)
Tool:   src/topology/capacity_formula.py
Caps:   Rich=8, Medium=6, Thin=4 (questions) | Rich=3, Medium=2, Thin=1 (examples)
```

## Stage 5: Subconcept Classification [DETERMINISTIC for now, MODEL for production]
```
Input:  ch_line_ranges.json + research findings
Output: ch_classified_budget.json (per subconcept: category + type split)
Categories: NUMERICAL, CONCEPTUAL, DIAGRAM, FACTUAL
Tool:   Manual classification (Ch9) → Production: Gemini with web search (Task #14)
```

## Stage 6: Content Generation [MODEL — Gemini 3.1 Pro HIGH]
```
Input:  Cached MMD + subconcept line ranges + type splits + existing questions as one-shots + images
Output: Per-subconcept JSON (theory + SCQs + subjective + examples)
Tool:   src/content_gen/generate_full_chapter.py
Post:   src/content_gen/post_process.py runs after EACH call:
        - Replace image codes with natural language
        - Auto-fix LaTeX delimiters ($→\( )
        - Strip NCERT figure numbers
        - Validate SCQ options present
Retry:  src/content_gen/retry_failed.py — fresh cache each round, recursive until all pass
Cost:   ~Rs 104 per chapter | ~13 min
```

## Stage 7: Solution Generation [MODEL — Gemini 3.1 Pro HIGH]
```
Input:  Cached MMD + NCERT questions (from unified mapping) with answers but no solutions
Output: Per-subconcept solution files → merged into unified mapping
Tool:   src/content_gen/generate_solutions.py
Rules:  SCQ → why correct + why distractor wrong
        Numerical → Given→Formula→Substitute→Answer→Interpret
        Descriptive → direct answer + reasoning
Post:   Same post-processor (LaTeX fix, image codes)
Cost:   ~Rs 30 per chapter
```

## Stage 8: Assembly [DETERMINISTIC — no model]
```
Input:  All generated content + all solutions + unified mapping
Output: ch_final_content.json (database-ready, reference schema format)
Tool:   Assembly script (merges generated + existing + solutions)
Checks: Every subconcept has theory + questions + examples
        Every SCQ has (A)(B)(C)(D) options
        Every question has answer + solution
        LaTeX delimiters correct
        No image codes in displayed text
```

## Stage 9: Review Interface [NO MODEL]
```
Input:  ch_final_content.json + generated images + NCERT images
Output: index.html (self-contained, MathJax rendering)
Tool:   Review HTML builder
Deploy: GitHub Pages or local file://
```

## Stage 10: Image Generation [MATPLOTLIB or GEMINI]
```
Input:  Image generation flags from content (generation_description field)
Output: PNG images (1024×768px)
Tool:   src/image_gen/ray_diagram_generator.py (matplotlib)
        Gemini Imagen (for complex biological/realistic diagrams)
Classifier: LLM decides matplotlib vs Gemini based on description
```

## Stage 11: Validation [MODEL — cross-model]
```
Input:  Final content
Output: Validation flags per item (_validation field)
Layers: L1 Pydantic (structural) + L2 LLM (factual accuracy)
Tool:   Post-processor with validation layers
```

## Stage 12: Faculty Review + Iteration
```
Input:  Review interface link
Output: Feedback → prompt adjustments → regenerate specific items
```

---

## TOTAL COST PER CHAPTER
| Stage | Cost |
|-------|------|
| MathPix OCR | ~Rs 5 |
| Exercise mapping | ~Rs 2 |
| Content generation | ~Rs 104 |
| Solution generation | ~Rs 30 |
| Image generation | FREE (matplotlib) |
| **TOTAL** | **~Rs 141 per chapter** |

## TOTAL FOR 100 CHAPTERS
~Rs 14,100 ($166 USD)
