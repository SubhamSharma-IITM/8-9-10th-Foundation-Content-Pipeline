"""
Clean extracted competitive questions using production-grade cleaners
forked from Question Uploading App stages 3 and 4.

For each extracted question:
  - Slice raw text from MMD using line ranges
  - Apply MathPix artifact cleanup
  - Normalize options to (A)(B)(C)(D) format with <br/> injection
  - Protect LaTeX math blocks during regex passes
  - Insert line breaks safely
  - Normalize whitespace and answer format

Output:
  - comp_questions_cleaned.json (all questions with cleaned question_text/options/solution_text)
  - comp_questions_pending.json (those missing answer_key or solution — for later completion)
"""
import json, os, re, sys
from typing import List, Tuple
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
MMD_PATH = os.path.join(BASE, 'experiments/01_ocr_benchmarks/mathpix/ch01_light_competitive/ch01_light_competitive.mmd')
EXTRACTED_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_questions_extracted.json')
CLEANED_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_questions_cleaned.json')
PENDING_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_questions_pending.json')


# ── Math block protection (forked from stage3) ──
def _protect_math_blocks(text: str) -> Tuple[str, List[str]]:
    """Replace $...$ and $$...$$ with placeholders to shield from regex."""
    placeholders = []
    counter = [0]

    def _make(match):
        placeholders.append(match.group(0))
        ph = f"\x01MATHPH{counter[0]}\x02"
        counter[0] += 1
        return ph

    # $$...$$ first (display math)
    text = re.sub(r'\$\$[^$]+\$\$', _make, text, flags=re.DOTALL)
    # $...$ (inline math)
    text = re.sub(r'\$[^$]+\$', _make, text)
    # \(...\) and \[...\]
    text = re.sub(r'\\\([^)]*\\\)', _make, text, flags=re.DOTALL)
    text = re.sub(r'\\\[[^\]]*\\\]', _make, text, flags=re.DOTALL)
    return text, placeholders


def _restore_math_blocks(text: str, placeholders: List[str]) -> str:
    for i, ph in enumerate(placeholders):
        text = text.replace(f"\x01MATHPH{i}\x02", ph)
    return text


# ── MathPix artifact cleanup (forked from stage3) ──
def clean_mathpix_artifacts(text: str) -> str:
    if not text:
        return text
    cleaned = text
    cleaned = re.sub(r"\\(and|or|the|in|of|is|for|at|to|with)\b", r"\1", cleaned)
    cleaned = cleaned.replace("\\&", "&amp;")
    cleaned = re.sub(r"\\(text|mathrm|mathbf)\s+\{", r"\\\1{", cleaned)
    cleaned = re.sub(r"\?height=\d+&width=\d+", "", cleaned)
    return cleaned


# ── Whitespace normalization ──
def normalize_whitespace(text: str) -> str:
    if not text:
        return text
    cleaned = re.sub(r"[^\S\n]+", " ", text)
    lines = [line.strip() for line in cleaned.split("\n")]
    return "\n".join(lines).strip()


# ── Strip leading question number (e.g. "1. ", "23. ") ──
def strip_question_number(text: str) -> str:
    if not text:
        return text
    return re.sub(r"^\s*\d+\s*[.\)]\s*", "", text, count=1)


# ── Strip [NTSE]/[KVPY]/[JSTSE] tags from question text ──
def strip_foundation_tags(text: str) -> str:
    return re.sub(r"\s*\[(NTSE|KVPY|JSTSE|OLYMPIAD)\]\s*", " ", text)


# ── Normalize options to (A)(B)(C)(D) — adapted from stage4 ──
def normalize_options(text: str) -> str:
    """Convert various option formats to (A)(B)(C)(D) with proper line breaks."""
    if not text:
        return ""
    protected, ph = _protect_math_blocks(text)
    result = protected

    # Already uppercase (A)(B) — just ensure line break before (A) if missing
    if re.search(r'\(A\)', result) and re.search(r'\(B\)', result):
        if not re.search(r'\n\s*\(A\)', result):
            result = re.sub(r'(?<!\n)\s*(\(A\))', r'\n\1', result, count=1)
        return _restore_math_blocks(result, ph)

    # (a)(b)(c)(d) lowercase parens → uppercase
    result = re.sub(r'(\n|^)\s*\(\s*a\s*\)', r'\1(A)', result, flags=re.MULTILINE)
    result = re.sub(r'(\n|^)\s*\(\s*b\s*\)', r'\1(B)', result, flags=re.MULTILINE)
    result = re.sub(r'(\n|^)\s*\(\s*c\s*\)', r'\1(C)', result, flags=re.MULTILINE)
    result = re.sub(r'(\n|^)\s*\(\s*d\s*\)', r'\1(D)', result, flags=re.MULTILINE)
    # First (a) on same line as question stem
    result = re.sub(r'(?<!\n)\s*\(\s*a\s*\)', r'\n(A)', result, count=1)

    # 1. 2. 3. 4. format
    result = re.sub(r'(\n|^)\s*1\.\s*', r'\1(A) ', result, flags=re.MULTILINE)
    result = re.sub(r'(\n|^)\s*2\.\s*', r'\1(B) ', result, flags=re.MULTILINE)
    result = re.sub(r'(\n|^)\s*3\.\s*', r'\1(C) ', result, flags=re.MULTILINE)
    result = re.sub(r'(\n|^)\s*4\.\s*', r'\1(D) ', result, flags=re.MULTILINE)

    # (1)(2)(3)(4)
    result = re.sub(r'(\n|^)\s*\(\s*1\s*\)', r'\1(A)', result, flags=re.MULTILINE)
    result = re.sub(r'(\n|^)\s*\(\s*2\s*\)', r'\1(B)', result, flags=re.MULTILINE)
    result = re.sub(r'(\n|^)\s*\(\s*3\s*\)', r'\1(C)', result, flags=re.MULTILINE)
    result = re.sub(r'(\n|^)\s*\(\s*4\s*\)', r'\1(D)', result, flags=re.MULTILINE)

    # Final pass: ensure linebreak before (A) if inline
    if re.search(r'\(A\)', result) and not re.search(r'\n\s*\(A\)', result):
        result = re.sub(r'(?<!\n)\s*(\(A\))', r'\n\1', result, count=1)

    return _restore_math_blocks(result, ph)


# ── Normalize answer per question type ──
def normalize_answer(answer, question_type, scq_format=None):
    if answer is None or answer == '':
        return None
    answer = str(answer).strip()
    # Map lowercase a/b/c/d to uppercase for SCQ/MCQ
    if question_type in ('scq', 'mcq'):
        # Extract letter(s) from possible formats
        letters = re.findall(r'\b([a-dA-D])\b', answer)
        if letters:
            uniq = sorted(set(L.upper() for L in letters))
            return ','.join(uniq) if question_type == 'mcq' else uniq[0]
    # Numerical: strip whitespace, keep as-is
    return answer


# ── Slice raw text from MMD ──
def slice_text(mmd_lines, start, end):
    if start is None or end is None:
        return ''
    end = min(end + 1, len(mmd_lines))
    return ''.join(mmd_lines[start:end]).strip()


# ── Clean a single question entry ──
def clean_question(entry, mmd_lines):
    qtype = entry.get('type')
    if qtype == 'passage':
        prange = entry.get('passage', {})
        passage_text = slice_text(mmd_lines, prange.get('start'), prange.get('end'))
        passage_text = normalize_whitespace(clean_mathpix_artifacts(passage_text))

        cleaned_subs = []
        for sq in entry.get('sub_questions', []):
            cleaned_subs.append(clean_single(sq, mmd_lines))
        return {
            'type': 'passage',
            'exercise_tier': entry.get('exercise_tier'),
            'foundation_type': entry.get('foundation_type'),
            'passage_text': passage_text,
            'sub_questions': cleaned_subs,
            '_exercise_name': entry.get('_exercise_name'),
            '_passage_lines': prange,
        }
    return clean_single(entry, mmd_lines)


def clean_single(entry, mmd_lines):
    qrange = entry.get('question', {})
    srange = entry.get('solution') or {}
    qtype = entry.get('type')
    scq_fmt = entry.get('scq_format')
    ans_fmt = entry.get('answer_format')

    # Slice raw text
    raw_q = slice_text(mmd_lines, qrange.get('start'), qrange.get('end'))
    raw_s = slice_text(mmd_lines, srange.get('start'), srange.get('end')) if srange.get('start') is not None else ''

    # Question text cleaning
    q_text = clean_mathpix_artifacts(raw_q)
    q_text = strip_foundation_tags(q_text)
    q_text = strip_question_number(q_text)
    # For SCQ/MCQ, normalize options to (A)(B)(C)(D)
    if qtype in ('scq', 'mcq') and scq_fmt != 'statement_selection':
        q_text = normalize_options(q_text)
    q_text = normalize_whitespace(q_text)

    # Solution text cleaning
    s_text = clean_mathpix_artifacts(raw_s) if raw_s else ''
    if s_text:
        # Strip leading "1. (a)" or similar from solution
        s_text = re.sub(r'^\s*\d+\s*[.\)]\s*\([a-dA-D]\)\s*', '', s_text, count=1)
        s_text = normalize_whitespace(s_text)

    # Normalize answer
    answer = normalize_answer(entry.get('answer_key'), qtype, scq_fmt)

    return {
        'type': qtype,
        'scq_format': scq_fmt,
        'answer_format': ans_fmt,
        'exercise_tier': entry.get('exercise_tier'),
        'foundation_type': entry.get('foundation_type'),
        'question_text': q_text,
        'options': extract_options(q_text) if qtype in ('scq', 'mcq') else None,
        'answer_key': answer,
        'solution_text': s_text or None,
        '_exercise_name': entry.get('_exercise_name'),
        '_question_lines': qrange,
        '_solution_lines': srange if srange.get('start') is not None else None,
    }


def extract_options(q_text):
    """Extract options A/B/C/D from cleaned question text."""
    if not q_text:
        return {}
    options = {}
    pattern = r'\(([A-D])\)\s*(.+?)(?=\n\s*\([A-D]\)|\Z)'
    for m in re.finditer(pattern, q_text, re.DOTALL):
        letter, text = m.group(1), m.group(2).strip()
        options[letter] = text
    return options if options else None


def main():
    print('=' * 70)
    print('STEP 8b: CLEAN EXTRACTED QUESTIONS')
    print('=' * 70)

    with open(MMD_PATH, 'r', encoding='utf-8') as f:
        mmd_lines = f.readlines()
    with open(EXTRACTED_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    questions = data['extracted']
    print(f'Loaded: {len(questions)} extracted questions')

    cleaned = []
    pending_no_answer = []
    pending_no_solution = []
    pending_no_options = []

    for i, entry in enumerate(questions):
        c = clean_question(entry, mmd_lines)
        c['_index'] = i
        cleaned.append(c)

        # Track pending
        if c.get('type') == 'passage':
            for j, sq in enumerate(c.get('sub_questions', [])):
                if not sq.get('answer_key'):
                    pending_no_answer.append({'idx': i, 'sub_idx': j, 'reason': 'missing answer_key'})
                if not sq.get('solution_text'):
                    pending_no_solution.append({'idx': i, 'sub_idx': j, 'reason': 'missing solution_text'})
                if sq.get('type') in ('scq', 'mcq') and not sq.get('options'):
                    pending_no_options.append({'idx': i, 'sub_idx': j, 'reason': 'options not parseable'})
            continue
        if not c.get('answer_key'):
            pending_no_answer.append({'idx': i, 'reason': 'missing answer_key', 'tier': c.get('exercise_tier'), 'type': c.get('type')})
        if not c.get('solution_text'):
            pending_no_solution.append({'idx': i, 'reason': 'missing solution_text', 'tier': c.get('exercise_tier'), 'type': c.get('type')})
        if c.get('type') in ('scq', 'mcq') and not c.get('options'):
            pending_no_options.append({'idx': i, 'reason': 'options not parseable', 'tier': c.get('exercise_tier'), 'type': c.get('type')})

    # Save cleaned
    with open(CLEANED_PATH, 'w', encoding='utf-8') as f:
        json.dump({'cleaned': cleaned, 'total': len(cleaned)}, f, indent=2, ensure_ascii=False)

    pending = {
        'no_answer': pending_no_answer,
        'no_solution': pending_no_solution,
        'no_options': pending_no_options,
        'summary': {
            'total_questions': len(cleaned),
            'missing_answer': len(pending_no_answer),
            'missing_solution': len(pending_no_solution),
            'missing_options': len(pending_no_options),
        }
    }
    with open(PENDING_PATH, 'w', encoding='utf-8') as f:
        json.dump(pending, f, indent=2, ensure_ascii=False)

    print(f'\nResults:')
    print(f'  Total cleaned: {len(cleaned)}')
    print(f'  Missing answer: {len(pending_no_answer)}')
    print(f'  Missing solution: {len(pending_no_solution)}')
    print(f'  Missing/unparseable options: {len(pending_no_options)}')
    print(f'\nFiles:')
    print(f'  Cleaned: {CLEANED_PATH}')
    print(f'  Pending: {PENDING_PATH}')

    # Show 3 cleaned samples
    print(f'\n{"=" * 70}\nSAMPLE CLEANED OUTPUT\n{"=" * 70}')
    shown_types = set()
    for c in cleaned:
        if c.get('type') == 'passage': continue
        key = f"{c.get('type')}/{c.get('scq_format') or c.get('answer_format')}"
        if key in shown_types: continue
        if len(shown_types) >= 3: break
        shown_types.add(key)
        print(f'\n[{key}]  Tier {c.get("exercise_tier")}  Answer: {c.get("answer_key")}')
        print(f'Question text:\n{c.get("question_text", "")[:500]}')
        if c.get('options'):
            print(f'Options:')
            for L, t in c['options'].items():
                print(f'  ({L}) {t[:80]}')
        if c.get('solution_text'):
            print(f'Solution:\n{c.get("solution_text", "")[:300]}')


if __name__ == '__main__':
    main()
