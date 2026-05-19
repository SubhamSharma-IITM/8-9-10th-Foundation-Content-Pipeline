"""
Content Generation Prompt Templates

Architecture:
  LAYER 1: System prompt (cached with chapter MMD) — shared across all subconcepts
  LAYER 2: Generation instruction (per subconcept) — swappable when research layer arrives
  LAYER 3: Context (per subconcept) — existing questions as one-shot + line range highlight

The model receives: cached(Layer 1 + MMD) + Layer 2 + Layer 3 as user message.
"""

# ═══════════════════════════════════════════════════════════════════════
# LAYER 1: SYSTEM PROMPT (cached with chapter MMD)
# ═══════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are an expert CBSE Class 10 Science teacher creating study material for students.

## YOUR ROLE
You create theory explanations, questions, and solved examples that a student will directly study from.
Your content must feel like it comes from a skilled, caring teacher — clear, precise, and insightful.
Everything you write must be grounded in the NCERT chapter text provided below.

## WHO WILL USE THIS CONTENT
Indian school students in Classes 8-10 studying for CBSE board exams. They will:
- Read your theory to understand concepts
- Attempt your questions to test their understanding
- Study your solved examples to learn problem-solving approaches
- Use your solutions to verify their answers

## CONTENT PHILOSOPHY (NCERT Style for Classes 8-10)
1. CONSTRUCTIVIST: Start from what the student already knows (everyday experience),
   then build towards the formal concept. Never open with jargon.
2. STAY IN THE ZONE: Every question must be answerable using ONLY the concepts
   in the provided source text. Never require knowledge from outside this subconcept.
   Questions TEST understanding — they never introduce new concepts.
3. PROGRESSIVE SCAFFOLDING: Theory builds concept → Easy questions check recall →
   Medium questions apply the concept → Hard questions challenge with unfamiliar scenarios.
4. TEACHER-LIKE TONE: Simple sentences. Relatable examples from daily life.
   Anticipate where students get confused. Explain the "why" behind every "what."
5. EACH QUESTION TESTS A UNIQUE COGNITIVE TASK: No two questions should test the same
   concept at the same level in the same way. If you can't articulate what makes a question
   different from another, don't include it.

## QUESTION TYPES (Only 2 main types exist in CBSE Class 8-10)

### SCQ (Single Correct Question)
Student selects exactly ONE option from A/B/C/D. The Question field contains the COMPLETE block including all options.

SCQ sub-formats:
- STANDARD: Direct 4-option MCQ testing factual/conceptual/application understanding
- ASSERTION_REASON: "Assertion (A): [statement]. Reason (R): [statement]." + 4 fixed evaluation options (Both true R explains A / Both true R doesn't explain A / A true R false / A false R true)
- STATEMENT_SELECTION: Multiple numbered statements listed, options are combinations like "(A) I and II (B) I, II and III (C) II and III (D) I and III"

### Subjective
Student writes an answer. Three answer formats:
- DESCRIPTIVE: Explain, compare, justify, define, give reason. Text answer.
- NUMERICAL: Calculate using formula with steps. Answer is a value with units. Show: Given → Formula → Substitution → Answer with units. CBSE gives marks for each step.
- DIAGRAM: Draw/label a diagram, or answer based on a given figure. Describe what the diagram should show.

## DIFFICULTY LEVELS (model decides within the assigned count)
- Easy: Recall textbook content directly. Define, name, identify. One mental step.
- Medium: Apply a concept — formula (1-2 steps), explain why, compare. Textbook-like context but not a copy-paste.
- Hard: Unfamiliar scenario, 3+ step reasoning, evaluate claims, cross-topic. Student constructs reasoning path.

## QUESTION PATTERN EXAMPLES (reference these when you see pattern codes)

N-SCQ-1 (Assertion-Reason with formula):
"Assertion (A): A point object at 26 cm from convex mirror f=26 cm. Image will not form at infinity.
Reason (R): The equation 1/f = 1/v + 1/u gives v = infinity.
(A) Both true, R explains A (B) Both true, R doesn't explain A (C) A true R false (D) A false R true"

N-SCQ-2 (Standard formula MCQ):
"A convex mirror of focal length 15 cm forms an image at 10 cm. The object distance is:
(A) -30 cm (B) +30 cm (C) -10 cm (D) +10 cm"

N-SUBJ-1 (Direct formula, 2-3 marks): "Object at 10 cm from convex mirror f=15 cm. Find position and nature."
N-SUBJ-2 (Multi-step, 3-5 marks): "Object 7 cm at 27 cm from concave mirror f=18 cm. Find screen distance, size, nature."
N-SUBJ-4 (Explain formula concept): "The magnification by a plane mirror is +1. What does this mean?"

C-SCQ-1 (Statement-selection): "Arnav wrote statements I, II, III about mirrors. Which combination is correct? (A) I and II (B) I,II,III..."
C-SCQ-2 (Standard conceptual): "Choose the correct explanation for why the sky appears blue. (A)... (B)... (C)... (D)..."
C-SCQ-3 (Application): "Which lens for reading small letters? (A) Convex f=50cm (B) Concave f=50cm (C) Convex f=5cm (D) Concave f=5cm"

C-SUBJ-1 (Explain why): "A student claims field at X is stronger than Y. Explain with reason if correct."
C-SUBJ-2 (Compare): "Differentiate between real and virtual images. Give one example of each."
C-SUBJ-3 (Define): "Define the principal focus of a concave mirror."

D-SCQ-1 (Image property): "Concave mirror image is virtual, erect, enlarged. Where is the object? (A)...(B)...(C)...(D)..."
D-SUBJ-1 (Draw diagram): "Draw and label a ray diagram showing image formation when object is between F and C."
D-SUBJ-2 (Identify from figure): "Image shows an optical instrument. A. Identify it. B. What type of image? C. Calculate focal length."

## OUTPUT FORMAT
Respond with strict JSON. No markdown wrapping. Follow this exact schema:

{
  "subconcept_id": "C2.S5",
  "theory": "Complete theory explanation for this subconcept. Teacher-like tone.",
  "scqs": [
    {
      "scq_format": "standard|assertion_reason|statement_selection",
      "difficulty": "Easy|Medium|Hard",
      "question": "Complete question block including all options",
      "answer": "A|B|C|D",
      "solution": "Why this answer is correct"
    }
  ],
  "subjective": [
    {
      "answer_format": "descriptive|numerical|diagram",
      "difficulty": "Easy|Medium|Hard",
      "question": "Complete question",
      "answer": "Short answer or numerical value with units",
      "solution": "Full worked solution or detailed explanation"
    }
  ],
  "examples": [
    {
      "difficulty": "Easy|Medium|Hard",
      "question": "Problem statement",
      "solution": "Step-by-step worked solution: Given → Find → Formula → Substitute → Answer → Interpret"
    }
  ]
}
"""


# ═══════════════════════════════════════════════════════════════════════
# LAYER 2: GENERATION INSTRUCTION (per subconcept)
# This is the SWAP POINT for research layer.
# Currently: hardcoded from category splits + pattern codes.
# Future: research layer generates this block dynamically.
# ═══════════════════════════════════════════════════════════════════════

def build_generation_instruction(
    subconcept_id: str,
    subconcept_name: str,
    line_start: int,
    line_end: int,
    category: str,
    type_split: dict,
    examples_to_generate: int,
    pattern_assignments: dict,
) -> str:
    """
    Build the generation instruction for one subconcept.

    This is Layer 2 — the part that gets swapped when research layer arrives.
    Currently uses hardcoded splits. Research layer would replace this entire string.
    """
    instruction = f"""## GENERATION TASK FOR SUBCONCEPT {subconcept_id}

Subconcept: {subconcept_name}
Source content: Lines {line_start}-{line_end} of the chapter text above.
Category: {category}

READ lines {line_start}-{line_end} carefully before generating. All content must be grounded in those lines.

### WHAT TO GENERATE:

"""
    # Questions
    for stype, count in type_split.items():
        if count <= 0:
            continue
        patterns = pattern_assignments.get(stype, [])
        pattern_str = ' or '.join(patterns) if patterns else 'any appropriate'

        if stype == 'scq':
            instruction += f"**{count} SCQ(s)** — Follow pattern(s): {pattern_str}\n"
        elif stype == 'subj_numerical':
            instruction += f"**{count} Subjective-NUMERICAL** — Follow pattern(s): {pattern_str}\n"
            instruction += f"  (Show complete worked solution: Given → Formula → Substitution → Answer with units)\n"
        elif stype == 'subj_descriptive':
            instruction += f"**{count} Subjective-DESCRIPTIVE** — Follow pattern(s): {pattern_str}\n"
        elif stype == 'subj_diagram':
            instruction += f"**{count} Subjective-DIAGRAM** — Follow pattern(s): {pattern_str}\n"
            instruction += f"  (Describe what the diagram should show. Reference figure numbers from the chapter where applicable.)\n"

    # Examples
    if examples_to_generate > 0:
        instruction += f"\n**{examples_to_generate} Solved Example(s)** — Progressive difficulty.\n"
        instruction += f"  Format: Given → Find → Formula → Substitute → Answer → Interpret nature of result.\n"
        instruction += f"  Use realistic numerical values with proper sign convention.\n"

    instruction += f"""
### RULES:
- Each question must test a DIFFERENT cognitive task
- Use NCERT sign convention (New Cartesian) for all numerical work
- Solutions must be complete — not just the final answer
- Do NOT test concepts from outside lines {line_start}-{line_end}
"""
    return instruction


# ═══════════════════════════════════════════════════════════════════════
# LAYER 3: CONTEXT (per subconcept)
# ═══════════════════════════════════════════════════════════════════════

def build_context(
    existing_questions: list,
    existing_examples: list,
) -> str:
    """
    Build context with FULL question text, options, answers — not summaries.
    These serve as one-shot format references AND grounding for what NOT to duplicate.
    """
    if not existing_questions and not existing_examples:
        return ""

    context = "\n### EXISTING QUESTIONS FOR THIS SUBCONCEPT\n"
    context += "(These are already in the database. Study their FORMAT and STYLE. Do NOT duplicate what they test.)\n\n"

    if existing_questions:
        for q in existing_questions:
            source = "Back Exercise" if q['id'].startswith('BACK') else "In-text Question"
            context += f"--- {source}: {q['id']} [{q['type']}, {q['difficulty']}] ---\n"
            # Full question text
            qtext = q.get('question_text', '')
            if qtext:
                context += f"Question: {qtext}\n"
            # Options (for SCQs)
            opts = q.get('options', {})
            if opts:
                for letter, text in opts.items():
                    context += f"  ({letter}) {text}\n"
            # Answer
            ans = q.get('answer')
            if ans:
                context += f"Answer: {ans}\n"
            context += "\n"

    if existing_examples:
        context += "### EXISTING SOLVED EXAMPLES (from NCERT)\n\n"
        for ex in existing_examples:
            context += f"--- {ex['id']} (NCERT) ---\n"
            if ex.get('question'):
                context += f"Question: {ex['question']}\n"
            context += "\n"

    context += "YOUR TASK: Generate NEW content that tests DIFFERENT cognitive tasks than the above.\n"
    context += "Match the quality, tone, and precision of the existing questions.\n"
    return context


# ═══════════════════════════════════════════════════════════════════════
# FULL PROMPT BUILDER
# ═══════════════════════════════════════════════════════════════════════

def build_full_prompt(
    subconcept_id: str,
    subconcept_name: str,
    line_start: int,
    line_end: int,
    category: str,
    type_split: dict,
    examples_to_generate: int,
    pattern_assignments: dict,
    existing_questions: list,
    existing_examples: list,
) -> tuple:
    """
    Build the complete prompt.

    Returns (system_prompt, user_prompt).
    system_prompt gets cached with the chapter MMD.
    user_prompt is sent fresh per subconcept.
    """
    layer2 = build_generation_instruction(
        subconcept_id, subconcept_name,
        line_start, line_end,
        category, type_split,
        examples_to_generate, pattern_assignments,
    )

    layer3 = build_context(existing_questions, existing_examples)

    user_prompt = layer2 + layer3

    return SYSTEM_PROMPT, user_prompt


# ═══════════════════════════════════════════════════════════════════════
# PATTERN EXAMPLES (injected into system prompt for reference)
# ═══════════════════════════════════════════════════════════════════════

PATTERN_EXAMPLES = {
    'N-SCQ-1': """Assertion-Reason with formula:
Assertion (A): A point object placed at distance of 26 cm from a convex mirror of focal length 26 cm. The image will not form at infinity.
Reason (R): For above given system the equation 1/f = 1/v + 1/u gives v = infinity.
(A) Both A and R are true, and R is the correct explanation of A.
(B) Both A and R are true, and R is not the correct explanation of A.
(C) A is true but R is false.
(D) A is false but R is true.""",

    'N-SCQ-2': """Standard formula MCQ:
A convex mirror of focal length 15 cm forms an image at 10 cm from the mirror. The object distance is:
(A) -30 cm (B) +30 cm (C) -10 cm (D) +10 cm""",

    'N-SUBJ-1': """Direct formula application (2-3 marks):
An object is placed at a distance of 10 cm from a convex mirror of focal length 15 cm. Find the position and nature of the image.
Solution: u = -10 cm, f = +15 cm. Using 1/v + 1/u = 1/f: 1/v = 1/15 - 1/(-10) = 1/15 + 1/10 = 1/6. v = +6 cm. Image is 6 cm behind the mirror, virtual and erect.""",

    'N-SUBJ-2': """Multi-step numerical (3-5 marks):
An object of size 7.0 cm is placed at 27 cm in front of a concave mirror of focal length 18 cm. At what distance from the mirror should a screen be placed to get a sharp image? Find the size and nature of the image.
Solution: u = -27 cm, f = -18 cm. 1/v = 1/f - 1/u = 1/(-18) - 1/(-27) = -1/18 + 1/27 = -1/54. v = -54 cm. Screen at 54 cm. m = -v/u = -(-54)/(-27) = -2. h' = m × h = -2 × 7.0 = -14 cm. Image is real, inverted, enlarged.""",

    'C-SCQ-1': """Statement-selection:
Arnav wrote the following statements about reflection from curved surfaces:
I. Concave mirrors can produce both real and virtual images depending on the position of the object.
II. Convex mirrors always produce real, inverted images regardless of the object's position.
III. In both concave and convex mirrors, the image location can be determined using the mirror formula.
Choose the correct option: (A) I and II (B) I, II and III (C) II and III (D) I and III""",

    'D-SCQ-1': """Image property identification:
The image formed by a concave mirror is observed to be virtual, erect and larger than the object. Where should be the position of the object?
(A) Between the principal focus and the centre of curvature
(B) At the centre of curvature
(C) Beyond the centre of curvature
(D) Between the pole of the mirror and its principal focus""",

    'D-SUBJ-1': """Diagram-based (2-3 marks):
The above image shows the formation of an image with an optical instrument.
A. Identify the optical instrument (shown schematically as a rectangle) in the image.
B. What type of image is formed in this case?
C. Based on the measurements given in the image, calculate the focal length of the instrument.""",
}


# ═══════════════════════════════════════════════════════════════════════
# TEST: Build prompt for C2.S5
# ═══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import json, sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    # Load data
    with open('experiments/03_topology_generation/ch09_unified_mapping.json','r') as f:
        unified = json.load(f)
    with open('experiments/03_topology_generation/ch09_line_ranges.json','r') as f:
        lr = json.load(f)

    # Test subconcept
    sid = 'C2.S5'
    name = lr[sid]['name']
    line_start = lr[sid]['line_start']
    line_end = lr[sid]['line_end']
    category = 'NUMERICAL'
    type_split = {'scq': 1, 'subj_numerical': 1, 'subj_descriptive': 1}
    examples_to_gen = 1
    patterns = {
        'scq': ['N-SCQ-1', 'N-SCQ-2'],
        'subj_numerical': ['N-SUBJ-1', 'N-SUBJ-2'],
        'subj_descriptive': ['N-SUBJ-4'],
    }

    u = unified[sid]
    existing_q = u['back_exercises'] + u['intext_questions']
    existing_ex = u['solved_examples']

    system, user = build_full_prompt(
        sid, name, line_start, line_end,
        category, type_split, examples_to_gen, patterns,
        existing_q, existing_ex,
    )

    print("=== SYSTEM PROMPT (cached with MMD) ===")
    print(f"Length: {len(system)} chars")
    print(system[:500])
    print("...")

    print(f"\n=== USER PROMPT (per subconcept) ===")
    print(f"Length: {len(user)} chars")
    print(user)

    print(f"\n=== TOTAL PROMPT SIZE ===")
    print(f"System: {len(system)} chars")
    print(f"User: {len(user)} chars")
    print(f"Note: Chapter MMD (~62K chars) is cached alongside system prompt")
