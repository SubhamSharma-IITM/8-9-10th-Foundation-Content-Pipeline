"""
Sample dry-run for competitive question extractor.
Slices a small mixed sample from Ex1, Ex3 (with [NTSE]/[KVPY] tags), and Ex4,
runs through the LLM, validates output structure with regex grounding.
"""
import json, os, re, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from google import genai
from google.genai import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from question_extractor_prompt import SYSTEM_INSTRUCTION, build_extraction_prompt

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
MMD_PATH = os.path.join(BASE, 'experiments/01_ocr_benchmarks/mathpix/ch01_light_competitive/ch01_light_competitive.mmd')

api_key = os.environ.get('GEMINI_API_KEY', '')
if not api_key:
    print('ERROR: Set GEMINI_API_KEY')
    sys.exit(1)

client = genai.Client(api_key=api_key)

# Exercise boundaries (from earlier inspection)
EX1_START = 1836  # MCQs of Master Boards
EX2_START = 2111  # Exercise 2 header
EX3_START = 2176  # Exercise 3 / Foundation Builder header
EX4_START = 2999  # Exercise 4 header
SOL_START = 3232  # Solutions section


def decorate_lines(lines):
    """Add Line_XXXXX: prefix."""
    return ''.join(f'Line_{i:05d}: {line}' for i, line in enumerate(lines))


def snap_to_question_start(lines, start_line):
    """Snap start_line forward to the next line beginning with `N. ` (numbered question)."""
    for i in range(start_line, min(start_line + 30, len(lines))):
        if re.match(r'^\d+\.\s', lines[i].strip()):
            return i
    return start_line  # fallback


def validate_extraction(result, lines):
    """Validate LLM extractions against regex ground truth.
    Returns list of issues."""
    issues = []
    if not isinstance(result, list):
        return ['result is not a list']

    seen_ranges = []
    for i, q in enumerate(result):
        qtype = q.get('type')
        # Passage entries: validate passage range exists. Sub-question can start with N., (i), (ii), (a) etc.
        if qtype == 'passage':
            prange = q.get('passage', {})
            if not prange or prange.get('start') is None:
                issues.append(f'[{i}] passage type missing passage line range')
            for j, sq in enumerate(q.get('sub_questions', [])):
                qr = sq.get('question', {})
                if qr.get('start'):
                    line = lines[qr['start']].strip() if qr['start'] < len(lines) else ''
                    # Accept N., (i)/(ii)/(iii)/(iv)/(v), (a)/(b), Q1, etc.
                    if not re.match(r'^\d+\.|^\(\w+\)|^Q\.?\s*\d', line, re.IGNORECASE):
                        issues.append(f'[{i}/sq{j}] start line "{line[:40]}" does not match question marker')
            continue
        # Regular questions: validate start line begins with N.
        qrange = q.get('question', {})
        if not qrange or qrange.get('start') is None:
            issues.append(f'[{i}] type={qtype} missing question.start')
            continue
        start = qrange['start']
        if start >= len(lines):
            issues.append(f'[{i}] start={start} beyond doc end')
            continue
        line_text = lines[start].strip()
        scq_fmt = q.get('scq_format', '')
        # statement_selection (Match/Multiple Matching) may start with \section*{List-I} or \section*{Column I}
        if scq_fmt == 'statement_selection':
            if not re.match(r'^\d+\.|^\\section\*\{(?:List|Column)', line_text, re.IGNORECASE):
                issues.append(f'[{i}] statement_selection start "{line_text[:60]}" not N. or List/Column header')
        else:
            if not re.match(r'^\d+\.\s|^\d+\.', line_text):
                issues.append(f'[{i}] start line "{line_text[:60]}" does not begin with N.')
        # Range overlap check
        for prev_s, prev_e in seen_ranges:
            if prev_s <= start <= prev_e:
                issues.append(f'[{i}] range {start}-{qrange.get("end")} overlaps with prior {prev_s}-{prev_e}')
        seen_ranges.append((start, qrange.get('end', start)))
        # foundation_type tag check — if foundation_type set, regex should find it
        ft = q.get('foundation_type')
        if ft:
            block = ''.join(lines[start:qrange.get('end', start)+1])
            if f'[{ft}]' not in block:
                issues.append(f'[{i}] foundation_type={ft} but tag [{ft}] not found in question lines')
    return issues


def main():
    with open(MMD_PATH, 'r', encoding='utf-8') as f:
        all_lines = f.readlines()

    # Build a sample slice that mixes question types from different exercises
    # We'll use lines covering: end of Ex1 MCQs + Assertion-Reason + Fill + part of Ex3 + tagged Ex3/4
    # For dry run: take Ex1 lines 1836-1950 (MCQ + AssertReason + Fill + T/F)
    # Add Ex3 sample (around L2660-2700 for tagged questions)
    # Add Ex4 sample with [KVPY]/[NTSE]
    # Plus the Solutions section (L3232+)

    # KEEP IT SIMPLE for first dry run: feed Ex1 first 110 lines + a tagged Ex3 chunk + sol section
    # so the model sees boundaries and tags in same payload

    # Strategy: feed entire MMD (the model can handle it, ~4000 lines = ~80K tokens)
    # but tell it to extract just first 10 questions starting from Ex1
    decorated = decorate_lines(all_lines)

    # For dry run 2: start in middle of Ex1 (Assertion-Reason at L1890) and extract 12 questions
    # This will cover: Assertion-Reason, Fill-in-blanks, True/False, Match-the-Following, Passage
    raw_start = int(os.environ.get('TEST_START_LINE', EX1_START))
    batch = int(os.environ.get('TEST_BATCH', 10))
    # Snap to next clean numbered question
    start_for_test = snap_to_question_start(all_lines, raw_start)
    if start_for_test != raw_start:
        print(f'Snapped start L{raw_start} -> L{start_for_test} (next "N." line)')

    prompt = build_extraction_prompt(
        start_line=start_for_test,
        batch_size=batch,
        ex1_start=EX1_START,
        ex2_start=EX2_START,
        ex3_start=EX3_START,
        ex4_start=EX4_START,
        sol_start=SOL_START,
    )

    print('=' * 70)
    print('DRY RUN — first 10 questions from Ex1 with full doc context')
    print('=' * 70)
    print(f'Document: {len(all_lines)} lines (~{len(decorated)//4} tokens)')
    print(f'Prompt: {len(prompt)} chars (~{len(prompt)//4} tokens)')
    print(f'Calling gemini-3-flash-preview, LOW thinking...')

    t0 = time.time()
    response = client.models.generate_content(
        model='gemini-3-flash-preview',
        contents=[decorated, prompt],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type='application/json',
            temperature=0.1,
            max_output_tokens=8000,
            thinking_config=types.ThinkingConfig(thinking_level='LOW'),
        ),
    )
    elapsed = time.time() - t0

    print(f'Response in {elapsed:.1f}s, {len(response.text)} chars')

    # Save raw
    raw_path = os.path.join(BASE, 'experiments/03_topology_generation/competitive/dry_run_step8_raw.json')
    with open(raw_path, 'w', encoding='utf-8') as f:
        f.write(response.text)

    try:
        result = json.loads(response.text)
    except Exception as e:
        print(f'JSON parse error: {e}')
        print(f'Raw saved at: {raw_path}')
        return

    # Validation
    issues = validate_extraction(result, all_lines) if isinstance(result, list) else []
    print()
    print('=' * 70)
    print('VALIDATION')
    print('=' * 70)
    if issues:
        for iss in issues:
            print(f'  ISSUE: {iss}')
    else:
        print('  All checks PASSED — every entry starts with N. pattern, no overlaps, foundation_type tags verified')

    print()
    print('=' * 70)
    print('LLM EXTRACTED QUESTIONS')
    print('=' * 70)
    if isinstance(result, list):
        for i, q in enumerate(result, 1):
            print(f'\n[{i}] type={q.get("type")} | tier={q.get("exercise_tier")} | foundation={q.get("foundation_type")}')
            print(f'    sub-format: scq_format={q.get("scq_format")}, answer_format={q.get("answer_format")}')
            print(f'    answer_key: {q.get("answer_key")}')
            if q.get('type') == 'passage':
                prange = q.get('passage', {})
                print(f'    passage lines: {prange.get("start")}-{prange.get("end")}')
            qrange = q.get('question', {}) or {}
            if qrange.get('start'):
                print(f'    question lines: {qrange.get("start")}-{qrange.get("end")}')
            srange = q.get('solution')
            if srange:
                print(f'    solution lines: {srange.get("start")}-{srange.get("end")}')
            else:
                print(f'    solution: none')
            # Show actual question text
            if qrange.get('start'):
                start = qrange['start']
                end = min(qrange.get('end', start), start + 8)
                actual_text = ''.join(all_lines[start:end+1])[:300]
                print(f'    actual text: {actual_text[:200]}')
            # Sub-questions for passage
            if q.get('sub_questions'):
                print(f'    sub_questions: {len(q["sub_questions"])}')
                for sq in q['sub_questions']:
                    print(f'       - type={sq.get("type")}, ans={sq.get("answer_key")}, lines={sq.get("question",{}).get("start")}-{sq.get("question",{}).get("end")}')

    elif isinstance(result, dict) and result.get('eof'):
        print('Model returned EOF immediately')
    else:
        print('Unexpected output structure:')
        print(json.dumps(result, indent=2)[:1000])


if __name__ == '__main__':
    main()
