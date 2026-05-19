"""
Competitive Question Extractor Prompt — adapted from stage2_llm_mapper.

Surgical changes from stage2:
- Drop PYQ context, subject inference (we're scoped to Physics Ch1)
- Drop production difficulty classification (we use exercise_tier-based)
- Compress to NCERT taxonomy: SCQ + MCQ + Subjective only
- Add scq_format / answer_format sub-format fields
- Add exercise_tier (1-4), foundation_type (NTSE/KVPY/JSTSE/null)
- Pass exercise boundaries from regex pre-scan as guide rails
"""

SYSTEM_INSTRUCTION = """You are a document labeler for Class 10 Physics competitive coaching material.
The document is a single chapter (Light - Reflection and Refraction) with 4 exercise tiers
followed by a Solutions section. Your job: extract each question with its line range,
type, sub-format, answer (if explicit), and solution range (if mapped).

DO NOT invent or alter content. Only label what exists. Return strict JSON only."""


EXTRACTION_PROMPT_TEMPLATE = r"""ROLE: Question labeler. Do not generate or rewrite any content.

START READING FROM: Line_{start_line:05d}
EXTRACT THE NEXT: {batch_size} questions
STOP AT: Line_{stop_at:05d} — do NOT extract any question whose start line >= STOP_AT. If you reach STOP_AT before finding {batch_size} questions, return whatever you found and signal EOF.

# EXERCISE BOUNDARIES (from pre-scan)
- Exercise 1 (Master Boards) starts at: Line_{ex1_start:05d}
- Exercise 2 (Master NCERT - Textbook + Exemplar) starts at: Line_{ex2_start:05d}
- Exercise 3 (Foundation Builder) starts at: Line_{ex3_start:05d}
- Exercise 4 (Foundation Builder+) starts at: Line_{ex4_start:05d}
- Solutions section (Brief Explanations) starts at: Line_{sol_start:05d}

CURRENT EXERCISE TIER (this batch): {current_tier}
All questions in this batch must have exercise_tier = {current_tier}.

# QUESTION TYPE TAXONOMY (compressed to NCERT standard)

Every question is exactly ONE of these 3 types:

## type = "scq" (Single Choice Question)
- Exactly one correct option from 4 choices (a/b/c/d) or labeled (A)(B)(C)(D)
- Sub-formats (`scq_format`):
  - `standard` — direct MCQ
  - `assertion_reason` — Assertion + Reason with the 4 standard codes (A/B/C/D)
  - `statement_selection` — Match the Following / Multiple Matching / Column-I-Column-II / List-I-List-II
- `answer_key`: "A" / "B" / "C" / "D"

## type = "mcq" (Multi-Correct, falls back to single-correct gracefully)
- One or more correct options from 4 choices
- Used when source labels it "One or More than One Option Correct"
- `answer_key`: comma-separated string like "A,C" or just "B" if only one correct

## type = "subjective" (Free-form answer)
- Sub-formats (`answer_format`):
  - `descriptive` — Fill-in-blanks, True/False, VSA, SA, LA, Reasoning, HOTS (text answers)
  - `numerical` — Integer/Numeric Questions (worked numerical with units)
  - `diagram` — Draw/label diagram or describe figure
- `answer_key`: brief text answer if explicitly given in solutions, else null

## Special: Passage / Case-Based grouping
- If a passage/stem is followed by 2+ sub-questions sharing the passage:
  - Return ONE entry with type="passage" and "sub_questions" array
  - The `passage` field MUST hold the line range of the passage stem itself (NOT null, NOT empty)
  - Do NOT set the top-level `question` field for passage entries — it is only used for non-passage types
  - Each sub-question has its own type (scq/mcq/subjective), scq_format, answer_format, question line range, and answer_key
  - The passage entry counts as 1 + len(sub_questions) toward batch count

# EXTRACTION RULES

1. Find question START line (where "1." or "2." or numbered question begins) and END line (just before next question or section header).

2. Detect type from current subsection heading:
   - "Multiple Choice", "Single Option Correct", "MCQs" → scq, scq_format=standard
   - "Assertion-Reason", "Assertion & Reason" → scq, scq_format=assertion_reason
   - "Match the Following", "Multiple Matching", "Column I/II", "List-I/II" → scq, scq_format=statement_selection
   - "One or More than One Option Correct", "More Than One Correct" → mcq
   - "Fill in the Blanks" → subjective, answer_format=descriptive
   - "True / False" → subjective, answer_format=descriptive
   - "Very Short Answer", "Short Answer", "Long Answer", "Reasoning Based", "HOTS" → subjective, answer_format=descriptive (or numerical if computation)
   - "Integer/Numeric" → subjective, answer_format=numerical
   - "Passage Based", "Case Based" → passage with sub_questions
   - "Text-Book Questions", "Exemplar Questions" → infer type from question content (mostly scq or subjective)

3. Detect `exercise_tier` (1/2/3/4) from line range vs the boundaries above.

4. Detect `foundation_type` from question text — look for [NTSE], [KVPY], [JSTSE], [Olympiad] tags appearing anywhere in the question lines. Set the matching tag string ("NTSE" / "KVPY" / "JSTSE" / "OLYMPIAD") if found, else null.

5. Map answer from Solutions section (Line_{sol_start:05d} onwards). The solutions are organized by question-type subsection. Match by subsection + question number.
   - For SCQ: answer_key is "A"/"B"/"C"/"D" (lowercase a/b/c/d in solutions → uppercase)
   - For MCQ: comma-separated like "A,C"
   - For subjective numerical: numeric string like "55" or "1.5"
   - For subjective descriptive: brief text answer
   - For Fill-in-blanks: the word(s) that fill the blank
   - For True/False: "True" or "False"
   - If no explicit answer found, set to null. Do NOT solve.

6. If a solution exists in the Solutions section, return its line range as `solution`. Else null.

# OUTPUT FORMAT (strict JSON)

For regular questions:
[
  {{
    "type": "scq",
    "scq_format": "standard",
    "exercise_tier": 1,
    "foundation_type": null,
    "answer_key": "A",
    "question": {{"start": 1839, "end": 1843}},
    "solution": {{"start": 3236, "end": 3236}}
  }},
  {{
    "type": "subjective",
    "answer_format": "numerical",
    "exercise_tier": 4,
    "foundation_type": "KVPY",
    "answer_key": "30",
    "question": {{"start": 3215, "end": 3220}},
    "solution": {{"start": 3700, "end": 3705}}
  }}
]

For passage groups:
{{
  "type": "passage",
  "exercise_tier": 1,
  "foundation_type": null,
  "passage": {{"start": 1983, "end": 1995}},
  "sub_questions": [
    {{
      "type": "scq", "scq_format": "standard",
      "answer_key": "C",
      "question": {{"start": 1996, "end": 1998}},
      "solution": {{"start": 3308, "end": 3308}}
    }}
  ]
}}

EOF: {{"eof": true, "last_content_line": <int>}}

# CRITICAL RULES
- Use line INDEX numbers from Line_XXXXX prefixes
- Each question must have UNIQUE non-overlapping line ranges
- Question START line MUST be a line that begins with `N. ` or `N.` (a numbered question marker). If the START_READING_FROM line is mid-question (e.g., orphan options like "(d) infinity"), SKIP forward to the next clean numbered question — do NOT treat orphan content as a new question.
- Question END must NOT include the answer line if answer is on next line
- Skip section headers, OCR noise, table headers like "Column I" alone
- Do NOT extract from Solutions section as new questions — Solutions are mappings only
- Return EOF when past the last actual question (before solutions section or end of doc)
"""


def build_extraction_prompt(start_line: int, batch_size: int,
                             ex1_start: int, ex2_start: int, ex3_start: int,
                             ex4_start: int, sol_start: int,
                             stop_at: int, current_tier: int) -> str:
    return EXTRACTION_PROMPT_TEMPLATE.format(
        start_line=start_line,
        batch_size=batch_size,
        ex1_start=ex1_start,
        ex2_start=ex2_start,
        ex3_start=ex3_start,
        ex4_start=ex4_start,
        sol_start=sol_start,
        stop_at=stop_at,
        current_tier=current_tier,
    )
