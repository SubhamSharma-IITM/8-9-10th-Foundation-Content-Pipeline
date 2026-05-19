"""
Production extraction loop for competitive Ch1 Light exercises.

Per-exercise batches with adaptive sizing (forked from stage2_llm_mapper logic).
Cost tracking from Gemini usageMetadata. Regex validation per batch.
"""
import json, os, re, sys, time
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from google import genai
from google.genai import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from question_extractor_prompt import SYSTEM_INSTRUCTION, build_extraction_prompt

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
MMD_PATH = os.path.join(BASE, 'experiments/01_ocr_benchmarks/mathpix/ch01_light_competitive/ch01_light_competitive.mmd')
OUT_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_questions_extracted.json')
COST_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_extraction_cost.json')

# Pricing for gemini-3-flash-preview standard (real-time)
PRICING = {
    'input_uncached': 0.50,  # $/1M tokens
    'input_cached': 0.25,
    'output': 3.00,  # includes thinking
}
INR_PER_USD = 85

# Exercise boundaries (validated)
EX1_START = 1836
EX2_START = 2111
EX3_START = 2176
EX4_START = 2999
SOL_START = 3232

EXERCISES = [
    {'tier': 1, 'name': 'Master Boards', 'start': EX1_START, 'end': EX2_START - 1},
    {'tier': 2, 'name': 'Master NCERT', 'start': EX2_START, 'end': EX3_START - 1},
    {'tier': 3, 'name': 'Foundation Builder', 'start': EX3_START, 'end': EX4_START - 1},
    {'tier': 4, 'name': 'Foundation Builder+', 'start': EX4_START, 'end': SOL_START - 1},
]

# Adaptive batching constants (from stage2)
BATCH_DEFAULT = 12
BATCH_MIN = 3
BATCH_MAX = 18
BLIND_JUMP = 50
MAX_CONSECUTIVE_EMPTY = 3

MODEL = 'gemini-3-flash-preview'
THINKING = 'LOW'
MAX_OUTPUT = 12000

api_key = os.environ.get('GEMINI_API_KEY', '')
if not api_key:
    print('ERROR: Set GEMINI_API_KEY')
    sys.exit(1)

client = genai.Client(api_key=api_key)


def decorate_lines(lines):
    return ''.join(f'Line_{i:05d}: {line}' for i, line in enumerate(lines))


def snap_to_question_start(lines, start_line, max_line):
    """Snap forward to next line beginning with `N. ` within max_line."""
    for i in range(start_line, min(max_line, len(lines))):
        if re.match(r'^\d+\.\s|^\d+\.', lines[i].strip()):
            return i
    return max_line  # past end → caller terminates


def extract_one_batch(decorated, start_line, batch_size, stop_at, tier):
    """Single LLM call. Returns (parsed, usage_dict)."""
    prompt = build_extraction_prompt(
        start_line=start_line, batch_size=batch_size,
        ex1_start=EX1_START, ex2_start=EX2_START,
        ex3_start=EX3_START, ex4_start=EX4_START,
        sol_start=SOL_START,
        stop_at=stop_at, current_tier=tier,
    )

    t0 = time.time()
    response = client.models.generate_content(
        model=MODEL,
        contents=[decorated, prompt],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type='application/json',
            temperature=0.1,
            max_output_tokens=MAX_OUTPUT,
            thinking_config=types.ThinkingConfig(thinking_level=THINKING),
        ),
    )
    elapsed = time.time() - t0

    # Token usage from usageMetadata
    usage = {'input': 0, 'output': 0, 'cached': 0, 'time_s': elapsed}
    um = getattr(response, 'usage_metadata', None)
    if um:
        usage['input'] = getattr(um, 'prompt_token_count', 0) or 0
        usage['output'] = getattr(um, 'candidates_token_count', 0) or 0
        usage['cached'] = getattr(um, 'cached_content_token_count', 0) or 0

    try:
        parsed = json.loads(response.text)
    except Exception as e:
        return None, usage

    return parsed, usage


def validate_entry(entry, lines, exercise_end, tier):
    """Returns issue string if invalid, else None."""
    if entry.get('type') == 'passage':
        prange = entry.get('passage', {})
        if not prange or prange.get('start') is None:
            return 'passage missing passage range'
        if prange['start'] >= exercise_end:
            return f'passage start {prange["start"]} beyond exercise end {exercise_end}'
        return None

    qrange = entry.get('question', {})
    if not qrange or qrange.get('start') is None:
        return 'missing question.start'
    start = qrange['start']
    if start >= exercise_end:
        return f'question start {start} beyond exercise end {exercise_end}'
    if start >= len(lines):
        return f'start {start} beyond doc end'

    line_text = lines[start].strip()
    scq_fmt = entry.get('scq_format', '')
    if scq_fmt == 'statement_selection':
        if not re.match(r'^\d+\.|^\\section\*\{(?:List|Column)', line_text, re.IGNORECASE):
            return f'statement_selection start "{line_text[:50]}" not N./List/Column'
    else:
        if not re.match(r'^\d+\.', line_text):
            return f'start "{line_text[:50]}" does not begin with N.'

    # Foundation tag check
    ft = entry.get('foundation_type')
    if ft:
        block = ''.join(lines[start:qrange.get('end', start) + 1])
        if f'[{ft}]' not in block:
            return f'foundation_type={ft} but tag not found in lines'

    # Tier mismatch check
    if entry.get('exercise_tier') != tier:
        return f'exercise_tier={entry.get("exercise_tier")} expected {tier}'

    return None


def extract_exercise(decorated, lines, exercise):
    """Loop extraction over one exercise with adaptive batching."""
    tier = exercise['tier']
    name = exercise['name']
    end_line = exercise['end']
    cursor = exercise['start']

    print(f"\n{'='*70}")
    print(f"EXERCISE {tier}: {name} | lines {exercise['start']}-{end_line}")
    print('='*70)

    extracted = []
    batch_size = BATCH_DEFAULT
    consecutive_empty = 0
    total_usage = {'input': 0, 'output': 0, 'cached': 0, 'time_s': 0.0, 'calls': 0}

    while cursor < end_line:
        # Snap cursor to next clean question start
        snapped = snap_to_question_start(lines, cursor, end_line)
        if snapped >= end_line:
            print(f"  No more questions in this exercise (cursor at {snapped} >= {end_line})")
            break
        cursor = snapped

        print(f"\n  → Batch from L{cursor}, size={batch_size}, stop_at=L{end_line}")
        result, usage = extract_one_batch(decorated, cursor, batch_size, end_line, tier)

        total_usage['input'] += usage['input']
        total_usage['output'] += usage['output']
        total_usage['cached'] += usage['cached']
        total_usage['time_s'] += usage['time_s']
        total_usage['calls'] += 1

        if result is None:
            print(f"    JSON parse failed. Shrinking batch, jumping cursor.")
            consecutive_empty += 1
            batch_size = max(BATCH_MIN, batch_size // 2)
            cursor += BLIND_JUMP
            if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                print(f"    Stopping after {consecutive_empty} consecutive failures")
                break
            continue

        # EOF
        if isinstance(result, dict) and result.get('eof'):
            print(f"    Model returned EOF.")
            break

        if not isinstance(result, list) or len(result) == 0:
            consecutive_empty += 1
            print(f"    Empty batch ({consecutive_empty}/{MAX_CONSECUTIVE_EMPTY})")
            batch_size = max(BATCH_MIN, batch_size // 2)
            cursor += BLIND_JUMP
            if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                print(f"    Stopping after {consecutive_empty} consecutive empty batches")
                break
            continue

        # Validate each entry
        valid_entries = []
        new_cursor = cursor
        for entry in result:
            issue = validate_entry(entry, lines, end_line, tier)
            if issue:
                print(f"    DROP: {issue}")
                continue
            valid_entries.append(entry)
            # Track highest end line to advance cursor
            if entry.get('type') == 'passage':
                last_sub = max((sq.get('question', {}).get('end', 0) for sq in entry.get('sub_questions', [])), default=0)
                new_cursor = max(new_cursor, last_sub)
            else:
                qend = entry.get('question', {}).get('end', cursor)
                new_cursor = max(new_cursor, qend)

        if not valid_entries:
            consecutive_empty += 1
            cursor += BLIND_JUMP
            batch_size = max(BATCH_MIN, batch_size // 2)
            print(f"    All entries dropped. Empty count={consecutive_empty}")
            if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                break
            continue

        # Success
        consecutive_empty = 0
        extracted.extend(valid_entries)
        cursor = new_cursor + 1
        batch_size = min(BATCH_MAX, batch_size + 1)
        print(f"    +{len(valid_entries)} questions. Cursor → L{cursor}. Total: {len(extracted)}")

    return extracted, total_usage


def calculate_cost(usage):
    """Cost in USD/INR from token usage."""
    uncached = usage['input'] - usage['cached']
    cost_usd = (
        (uncached / 1e6) * PRICING['input_uncached'] +
        (usage['cached'] / 1e6) * PRICING['input_cached'] +
        (usage['output'] / 1e6) * PRICING['output']
    )
    return cost_usd, cost_usd * INR_PER_USD


def main():
    print('=' * 70)
    print('STEP 8: COMPETITIVE EXERCISE EXTRACTION (FULL RUN)')
    print('=' * 70)
    print(f'Model: {MODEL} | Thinking: {THINKING} | Max output: {MAX_OUTPUT}')

    with open(MMD_PATH, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    decorated = decorate_lines(lines)
    print(f'Document: {len(lines)} lines, ~{len(decorated)//4} tokens')

    all_extracted = []
    grand_usage = {'input': 0, 'output': 0, 'cached': 0, 'time_s': 0.0, 'calls': 0}
    per_exercise_stats = []

    for ex in EXERCISES:
        ex_extracted, ex_usage = extract_exercise(decorated, lines, ex)
        for e in ex_extracted:
            e['_exercise_name'] = ex['name']
        all_extracted.extend(ex_extracted)

        ex_cost_usd, ex_cost_inr = calculate_cost(ex_usage)
        per_exercise_stats.append({
            'tier': ex['tier'],
            'name': ex['name'],
            'questions': len(ex_extracted),
            'calls': ex_usage['calls'],
            'input_tokens': ex_usage['input'],
            'output_tokens': ex_usage['output'],
            'cached_tokens': ex_usage['cached'],
            'time_s': round(ex_usage['time_s'], 1),
            'cost_usd': round(ex_cost_usd, 6),
            'cost_inr': round(ex_cost_inr, 4),
        })

        for k in grand_usage:
            grand_usage[k] += ex_usage[k]

    # Save results
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump({
            'extracted': all_extracted,
            'total_questions': len(all_extracted),
        }, f, indent=2, ensure_ascii=False)

    grand_cost_usd, grand_cost_inr = calculate_cost(grand_usage)
    cost_report = {
        'session': 'comp_ch1_extraction',
        'model': MODEL,
        'thinking': THINKING,
        'pricing': PRICING,
        'inr_per_usd': INR_PER_USD,
        'per_exercise': per_exercise_stats,
        'totals': {
            'questions': len(all_extracted),
            'calls': grand_usage['calls'],
            'input_tokens': grand_usage['input'],
            'output_tokens': grand_usage['output'],
            'cached_tokens': grand_usage['cached'],
            'time_s': round(grand_usage['time_s'], 1),
            'cost_usd': round(grand_cost_usd, 6),
            'cost_inr': round(grand_cost_inr, 4),
            'cost_per_question_inr': round(grand_cost_inr / max(len(all_extracted), 1), 6),
        },
    }
    with open(COST_PATH, 'w', encoding='utf-8') as f:
        json.dump(cost_report, f, indent=2, ensure_ascii=False)

    # Summary
    print(f"\n{'='*70}")
    print('FINAL SUMMARY')
    print('='*70)
    type_counts = defaultdict(int)
    foundation_counts = defaultdict(int)
    for e in all_extracted:
        type_counts[f"{e.get('type')}/{e.get('scq_format') or e.get('answer_format') or 'passage'}"] += 1
        if e.get('foundation_type'):
            foundation_counts[e['foundation_type']] += 1

    print(f"\nQuestions per exercise:")
    for s in per_exercise_stats:
        print(f"  Tier {s['tier']} ({s['name']:25s}): {s['questions']:3d} questions in {s['calls']:2d} calls, Rs {s['cost_inr']:.3f}")

    print(f"\nQuestion type breakdown:")
    for t, n in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t:35s}: {n:3d}")

    if foundation_counts:
        print(f"\nFoundation type tags:")
        for ft, n in sorted(foundation_counts.items()):
            print(f"  {ft}: {n}")

    print(f"\n{'='*70}")
    print(f"GRAND TOTAL: {len(all_extracted)} questions, {grand_usage['calls']} calls, {round(grand_usage['time_s'],1)}s")
    print(f"Tokens: {grand_usage['input']:,} in ({grand_usage['cached']:,} cached) + {grand_usage['output']:,} out")
    print(f"COST: Rs {grand_cost_inr:.3f} (${grand_cost_usd:.5f})")
    print(f"Per question: Rs {grand_cost_inr / max(len(all_extracted), 1):.4f}")
    print(f"\nSaved: {OUT_PATH}")
    print(f"Cost report: {COST_PATH}")


if __name__ == '__main__':
    main()
