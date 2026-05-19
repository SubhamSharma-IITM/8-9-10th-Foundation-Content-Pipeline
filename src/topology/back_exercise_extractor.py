"""
Back Exercise & In-Text Question Extractor

Extracts questions from MathPix MMD, classifies question type by code.
Difficulty tagging and subconcept mapping are separate (model-based) steps.

Output: ch09_exercises.json with all extracted questions.
"""

import re
import json
import sys
from pathlib import Path


def extract_back_exercises(lines: list[str]) -> list[dict]:
    """
    Extract back exercise questions from the EXERCISES section.
    Identifies question type (SCQ/Integer/Subjective) via regex.
    """
    # Find exercises section start.
    # Tolerant of OCR misreads: Ch12 came through as "E X E R C J S E S" (J/I confusion).
    # Pattern: any non-whitespace char in the I-position to absorb such artifacts.
    ex_header_re = re.compile(r'E\s*X\s*E\s*R\s*C\s*\S\s*S\s*E\s*S?', re.IGNORECASE)
    ex_start = None
    for i, line in enumerate(lines):
        if ex_header_re.search(line) or re.search(r'section.*EXERCISES?', line, re.IGNORECASE):
            ex_start = i + 1
            break

    if ex_start is None:
        print("WARNING: No EXERCISES section found")
        return []

    exercises = []
    current_q = None

    for i in range(ex_start, len(lines)):
        line = lines[i].strip()
        if not line:
            continue

        # New question starts with "N. " pattern
        q_match = re.match(r'^(\d+)\.\s+(.+)', line)
        if q_match:
            # Save previous question
            if current_q:
                current_q['type'] = _classify_question_type(current_q)
                exercises.append(current_q)

            current_q = {
                'num': int(q_match.group(1)),
                'text': q_match.group(2).strip(),
                'line_start': i + 1,
                'options': {},
                'full_text': line,
                'continuation_lines': [],
            }
        elif current_q:
            # Check for options: (a), (b), (c), (d)
            opt_match = re.match(r'^\(([a-d])\)\s+(.+)', line)
            if opt_match:
                opt_letter = opt_match.group(1).upper()
                opt_text = opt_match.group(2).strip()
                current_q['options'][opt_letter] = opt_text
            else:
                # Continuation of current question
                current_q['continuation_lines'].append(line)
                current_q['full_text'] += ' ' + line

    # Save last question
    if current_q:
        current_q['type'] = _classify_question_type(current_q)
        exercises.append(current_q)

    # Clean up
    for ex in exercises:
        ex['line_end'] = ex['line_start'] + len(ex['continuation_lines']) + len(ex['options'])
        # Remove internal tracking
        del ex['continuation_lines']
        # Clean full_text
        ex['full_text'] = re.sub(r'\s+', ' ', ex['full_text']).strip()

    return exercises


def extract_intext_questions(lines: list[str]) -> list[dict]:
    """
    Extract in-text questions (appear after "Q U E S T I O N S" sections).
    """
    questions = []
    in_q_block = False
    block_num = 0

    for i, line in enumerate(lines):
        # Detect question block start
        if 'Q U E S T I O N' in line or re.search(r'section.*\{QUESTIONS\}', line):
            in_q_block = True
            block_num += 1
            continue

        # Detect question block end (next section/subsection)
        if in_q_block and re.search(r'\\(sub)?section', line):
            in_q_block = False
            continue

        if in_q_block:
            q_match = re.match(r'^(\d+)\.\s+(.+)', line.strip())
            if q_match:
                q_text = q_match.group(2).strip()
                q_type = _classify_intext_question(q_text)
                questions.append({
                    'num': int(q_match.group(1)),
                    'block': block_num,
                    'text': q_text,
                    'line': i + 1,
                    'type': q_type,
                    'isBackExercise': False,
                    'isInTextQuestion': True,
                })

    return questions


def _classify_question_type(q: dict) -> str:
    """
    Classify back exercise question type by code/regex.

    Rules:
    - Has 4 options (a/b/c/d) → SCQ
    - Has "find", "calculate", "what is the value", numerical answer expected → Integer
    - Otherwise → Subjective
    """
    # If has options → SCQ
    if len(q['options']) >= 3:
        return 'scq'

    text = q['full_text'].lower()

    # Integer indicators: asks for a numerical answer
    integer_patterns = [
        r'find the (?:position|distance|focal length|power|magnification|size|speed|value)',
        r'calculate',
        r'what is the (?:focal length|power|speed|distance|magnification)',
        r'at what distance',
        r'how far',
        r'\d+\s*cm\b.*(?:find|calculate|determine)',  # given values + asks to find
        r'(?:focal length|radius of curvature|power).*\d+.*(?:find|what)',
    ]

    for pattern in integer_patterns:
        if re.search(pattern, text):
            # But check: if it also asks "nature" or "draw" → subjective (not pure numerical)
            if re.search(r'draw|ray diagram|nature.*image|explain|describe|name|support', text):
                # Mixed: asks for calculation AND explanation/diagram
                # Check if calculation is primary
                if re.search(r'find.*position|find.*size|calculate.*distance', text):
                    return 'integer'  # Primary is numerical
                return 'subjective'
            return 'integer'

    # Subjective indicators
    subjective_patterns = [
        r'explain',
        r'describe',
        r'draw',
        r'ray diagram',
        r'name the type',
        r'support your answer',
        r'what does this mean',
        r'why',
        r'verify',
        r'what should be the range',
        r'will this lens produce',
    ]

    for pattern in subjective_patterns:
        if re.search(pattern, text):
            return 'subjective'

    # Default: if has numbers/units in the question → likely integer
    if re.search(r'\d+\s*(?:cm|m|mm|D|dioptre)', text):
        return 'integer'

    return 'subjective'


def _classify_intext_question(text: str) -> str:
    """Classify in-text question type."""
    t = text.lower()

    if re.search(r'define|name|what is the si unit|state', t):
        return 'subjective'  # short answer recall

    if re.search(r'find|calculate|what is the (?:speed|focal|power)', t):
        return 'integer'

    return 'subjective'


def load_answer_key(chapter_mapping_path: str, chapter_num: int = 9) -> dict:
    """Load answer key for back exercises from chapter_mapping.json."""
    with open(chapter_mapping_path, 'r') as f:
        mapping = json.load(f)

    key = f'ch{chapter_num}'
    answers = mapping.get('back_exercise_answers', {}).get(key, {})
    return answers


def merge_answer_key(exercises: list[dict], answers: dict) -> list[dict]:
    """Merge answer key into extracted exercises."""
    for ex in exercises:
        q_num = str(ex['num'])
        if q_num in answers:
            ans = answers[q_num]
            if isinstance(ans, str):
                ex['answer'] = ans
            elif isinstance(ans, list):
                ex['answer'] = ans  # multi-part answer
            else:
                ex['answer'] = str(ans)
        else:
            ex['answer'] = None
    return exercises


if __name__ == '__main__':
    import argparse
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(PROJECT_ROOT))
    from src.common import chapter_config
    from src.common.backup import safe_write_json

    parser = argparse.ArgumentParser(description='Back-exercise + in-text question extractor (FREE)')
    parser.add_argument('--chapter', help='Chapter key from chapter_config registry')
    parser.add_argument('mmd_path', nargs='?', help='Legacy: MMD path (used if --chapter omitted)')
    parser.add_argument('output_dir', nargs='?', help='Legacy: output dir')
    args = parser.parse_args()

    chapter_num_for_answers = 9  # legacy default
    if args.chapter:
        cfg = chapter_config.load(args.chapter)
        mmd_path = str(cfg.mmd_path)
        cfg.topology_dir.mkdir(parents=True, exist_ok=True)
        out_path_obj = cfg.exercises_path
        # try to extract chapter number from chapter_id (e.g. "ch12" -> 12)
        import re as _re
        _m = _re.match(r'ch(\d+)', cfg.chapter_id)
        if _m:
            chapter_num_for_answers = int(_m.group(1))
    else:
        mmd_path = args.mmd_path or 'experiments/01_ocr_benchmarks/mathpix/ch09_light/ch09_mathpix.mmd'
        output_dir = Path(args.output_dir or 'experiments/03_topology_generation')
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path_obj = output_dir / 'ch09_exercises.json'

    mapping_path = str(PROJECT_ROOT / 'data' / 'ncert' / 'class10' / 'chapter_mapping.json')

    with open(mmd_path, 'r', encoding='utf-8') as f:
        lines = [l.rstrip('\n') for l in f.readlines()]

    # Extract
    back_exercises = extract_back_exercises(lines)
    intext_questions = extract_intext_questions(lines)

    # Merge answer key
    if Path(mapping_path).exists():
        answers = load_answer_key(mapping_path, chapter_num=chapter_num_for_answers)
        back_exercises = merge_answer_key(back_exercises, answers)

    # Summary
    print("=" * 80)
    print("BACK EXERCISES")
    print("=" * 80)

    type_counts = {'scq': 0, 'integer': 0, 'subjective': 0}
    for ex in back_exercises:
        type_counts[ex['type']] += 1
        ans_str = f" | Answer: {ex.get('answer', '?')}" if ex.get('answer') else ""
        opts = f" | Options: {len(ex['options'])}" if ex['options'] else ""
        print(f"  Q{ex['num']:>2} [{ex['type']:>10}] (L{ex['line_start']}){opts}{ans_str}")
        print(f"       {ex['text'][:100]}")

    print(f"\n  TOTAL: {len(back_exercises)} | SCQ: {type_counts['scq']} | Integer: {type_counts['integer']} | Subjective: {type_counts['subjective']}")

    print(f"\n{'=' * 80}")
    print("IN-TEXT QUESTIONS")
    print("=" * 80)

    for q in intext_questions:
        print(f"  Block {q['block']} Q{q['num']} [{q['type']:>10}] (L{q['line']})")
        print(f"       {q['text'][:100]}")

    print(f"\n  TOTAL: {len(intext_questions)}")

    # Save
    output = {
        'back_exercises': back_exercises,
        'intext_questions': intext_questions,
        'summary': {
            'back_exercise_count': len(back_exercises),
            'intext_question_count': len(intext_questions),
            'type_distribution': type_counts,
        }
    }

    safe_write_json(out_path_obj, output)
    print(f"\nSaved: {out_path_obj}")
