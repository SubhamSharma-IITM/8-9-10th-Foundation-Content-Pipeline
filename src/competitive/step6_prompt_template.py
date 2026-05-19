"""
Step 6 prompt template — NCERT <-> Competitive subconcept mapping.

Template accepts: {subject}, {class_level}, {chapter_number}, {chapter_name},
                  {ncert_subconcepts_block}, {competitive_subconcepts_block},
                  {ncert_count}, {competitive_count}
"""

STEP6_PROMPT_TEMPLATE = r"""# ROLE

You are a curriculum alignment specialist for {subject} at Class {class_level} level. You know the NCERT board syllabus and coaching institute foundation material equally well. The current task concerns Chapter {chapter_number}: {chapter_name}.

---

# TASK

Map each competitive subconcept to its equivalent NCERT subconcept. This is a set-to-set mapping function.

Three possible outcomes for each subconcept:
- **overlap** — the competitive subconcept covers the same topic as one of the NCERT subconcepts
- **competitive_only** — the competitive subconcept has no equivalent in the NCERT list (beyond-syllabus content)
- **ncert_only** — an NCERT subconcept that no competitive subconcept maps to (listed separately at the end)

---

# INPUT FORMAT

- Each subconcept has a code (`NCRT_C{{x}}.S{{y}}` or `COMP_C{{x}}.S{{y}}`), a parent concept name, and the subconcept name.
- Competitive subconcepts also include a short content preview (first 2-3 lines of source text). Use this when the name alone is unclear or misleading.
- Some competitive subconcepts are tagged `[CONNECTING_TOPIC]` — this is a PDF-native label for advanced material (typically beyond Class 10 syllabus).

---

# MATCHING RULE

Match on content, not name similarity.
- `COMP_C17.S1 Mirror Formula` → `NCRT_C2.S5 Mirror Formula and Magnification` — names differ, content is the same → overlap.
- Many-to-one is allowed: multiple competitive subs can map to the same NCERT sub (e.g., `Concave Mirrors` + `Convex Mirrors` both → `Spherical Mirrors - Introduction`).
- When a competitive sub has no NCERT equivalent (e.g., Total Internal Reflection, Lens Maker Formula) → `competitive_only`.

## How to decide between `overlap` and `competitive_only`

**`overlap` means**: the core physics concept of the competitive subconcept is taught in the NCERT chapter. The NCERT subconcept is the natural home where a student would learn this topic from the board syllabus. Partial/introductory treatment in NCERT still counts as overlap.

**`competitive_only` means**: the physics concept is genuinely absent from this NCERT chapter. A student studying only NCERT would NOT encounter this topic in this chapter. Typical cases:
- Advanced formulas beyond board syllabus (e.g., Lens Maker Formula `1/f = (μ-1)(1/R1 - 1/R2)`, Silvering of Lens `1/F = 2/Fℓ + 1/Fm`, Refraction at Spherical Surfaces `μ₂/v - μ₁/u = (μ₂-μ₁)/R`, Newton's Formula `xy = f²`, Combination of Lenses with derivations)
- Phenomena taught in higher classes (e.g., Total Internal Reflection, Critical Angle, Interference, Diffraction, Polarisation)
- Topics covered in different NCERT chapters (e.g., Atmospheric Refraction is in NCERT Ch11 Human Eye, NOT in Ch9 Light)
- Classification/identification rules built on top of NCERT formulas (e.g., "Identification of Mirror by Size and Nature" is a derived technique, not a base topic)

**Critical consistency rule**: All four of `Refraction at Spherical Surfaces`, `Lens Maker Formula`, `Combination of Lenses`, `Silvering of Lens` are Class 11+ advanced formulas — if you mark any one of them `competitive_only`, mark ALL of them `competitive_only`. They live in the same pedagogical tier.

**Introductory content**: Basic definitions that precede the main chapter topic (e.g., "What is Light?", "Characteristics of Light", "Ray and Beam of Light") are foundational prerequisites that NCERT covers briefly in its chapter intro under `Reflection Of Light` or similar. These are overlap.

---

# NCERT SUBCONCEPTS ({ncert_count} total)

{ncert_subconcepts_block}

---

# COMPETITIVE SUBCONCEPTS ({competitive_count} total)

{competitive_subconcepts_block}

---

# OUTPUT — STRICT JSON

Return one JSON object with two keys: `mappings` (one entry per competitive subconcept) and `ncert_only` (NCERT subconcepts with no competitive match).

```json
{{
  "mappings": [
    {{
      "comp_code": "COMP_C17.S1",
      "comp_name": "Mirror Formula",
      "ncert_code": "NCRT_C2.S5",
      "ncert_name": "Mirror Formula and Magnification",
      "category": "overlap"
    }},
    {{
      "comp_code": "COMP_C23.S1",
      "comp_name": "Total Internal Reflection",
      "ncert_code": null,
      "ncert_name": null,
      "category": "competitive_only"
    }}
  ],
  "ncert_only": [
    {{
      "ncert_code": "NCRT_CX.SY",
      "ncert_name": "Subconcept name here"
    }}
  ]
}}
```

Field rules:
- `comp_code` / `comp_name` — copy exactly from input
- `ncert_code` / `ncert_name` — populate for `overlap`, set to `null` for `competitive_only`
- `category` — exactly one of: `overlap`, `competitive_only`

---

# CONSTRAINTS

1. Output exactly {competitive_count} entries in `mappings` — one per competitive subconcept. No skipping, no duplicates.
2. Use only codes that appear in the input lists. Do not invent codes.
3. Preserve code spelling exactly: `NCRT_` and `COMP_`.
4. Every NCERT code must appear in `mappings` as `ncert_code` OR in `ncert_only`.
5. Return raw JSON only. No markdown fences, no commentary.
"""


def build_prompt(subject: str, class_level: str, chapter_number: int, chapter_name: str,
                 ncert_block: str, competitive_block: str,
                 ncert_count: int, competitive_count: int) -> str:
    """Fill the template with call-specific parameters."""
    return STEP6_PROMPT_TEMPLATE.format(
        subject=subject,
        class_level=class_level,
        chapter_number=chapter_number,
        chapter_name=chapter_name,
        ncert_subconcepts_block=ncert_block,
        competitive_subconcepts_block=competitive_block,
        ncert_count=ncert_count,
        competitive_count=competitive_count,
    )
