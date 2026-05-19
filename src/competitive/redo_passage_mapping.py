"""
Surgical redo for passage-type questions only.
Reads existing comp_questions_mapped.json, finds passage entries in redo_bucket,
re-feeds them with a passage-aware prompt, merges results back.
"""
import json, os, re, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from google import genai
from google.genai import types

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
MMD_PATH = os.path.join(BASE, 'experiments/01_ocr_benchmarks/mathpix/ch01_light_competitive/ch01_light_competitive.mmd')
SCHEMA_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_schema_sealed.json')
MAPPING_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_mapping_verified.json')
QUESTIONS_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_questions_cleaned.json')
MAPPED_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_questions_mapped.json')

MODEL = 'gemini-3-flash-preview'
THINKING_LEVEL = 'LOW'
PRICING = {'input_uncached': 0.50, 'input_cached': 0.25, 'output': 3.00}
INR_PER_USD = 85

api_key = os.environ.get('GEMINI_API_KEY', '')
if not api_key:
    print('ERROR: Set GEMINI_API_KEY')
    sys.exit(1)

client = genai.Client(api_key=api_key)


PASSAGE_PROMPT = """You are mapping passage-based questions from a Class 10 Physics competitive coaching book to their teaching subconcept.

A "passage" entry contains a stem (the passage text) plus 2-5 sub-questions. The whole passage as a unit teaches ONE subconcept — assign that subconcept code to the passage.

Use the SAME competitive subconcept list and difficulty rubric as the main mapping task.

# COMPETITIVE SUBCONCEPTS (use ONLY these codes):
{subconcept_block}

# PASSAGES TO MAP:
{passage_block}

# OUTPUT (strict JSON, code-only, no names/reasoning):
{{
  "mappings": [
    {{"q": 51, "code": "COMP_C29.S2", "diff": "Medium"}},
    {{"q": 105, "code": "COMP_C22.S1", "diff": "Easy"}}
  ]
}}

CODE FORMAT: COMP_C<n>.S<n> (uppercase, underscore between COMP/C, dot between concept/S).
Use ONLY codes from the list above. One entry per passage."""


def load_inputs():
    with open(MMD_PATH, 'r', encoding='utf-8') as f:
        mmd = f.read()
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
        ncert_mapping = json.load(f)
    with open(QUESTIONS_PATH, 'r', encoding='utf-8') as f:
        questions = json.load(f)['cleaned']
    with open(MAPPED_PATH, 'r', encoding='utf-8') as f:
        mapped = json.load(f)
    return mmd, schema, ncert_mapping, questions, mapped


def normalize_code(raw_code, valid_codes):
    if not raw_code: return None, 'invalid'
    s = str(raw_code).strip()
    if s in valid_codes: return s, 'exact'
    upper = s.upper()
    if upper in valid_codes: return upper, 'normalized'
    cleaned = upper.replace('-', '_').replace(' ', '')
    if cleaned in valid_codes: return cleaned, 'normalized'
    m = re.search(r'C\s*(\d+)[._\s]+S\s*(\d+)', upper)
    if m:
        rebuilt = f'COMP_C{m.group(1)}.S{m.group(2)}'
        if rebuilt in valid_codes: return rebuilt, 'normalized'
    return s, 'invalid'


def main():
    mmd, schema, ncert_mapping, questions, mapped = load_inputs()

    # Find unique passage q_indices in redo_bucket (deduplicate)
    redo_q_indices = sorted(set(r['q_index'] for r in mapped.get('redo_bucket', []) if r.get('q_index') is not None))
    passage_indices = [i for i in redo_q_indices if i < len(questions) and questions[i].get('type') == 'passage']
    print(f'Passages needing redo: {len(passage_indices)}')

    if not passage_indices:
        print('Nothing to redo. Done.')
        return

    # Build subconcept block
    sub_lines = []
    for c in schema['concepts']:
        for s in c['subconcepts']:
            tag = ' [CONNECTING]' if s.get('is_connecting_topic') else ''
            sub_lines.append(f"  {s['id']}{tag} | Parent: {c['name']} | Sub: {s['name']}")
    subconcept_block = '\n'.join(sub_lines)

    # Build passage block
    passage_lines = []
    for qi in passage_indices:
        q = questions[qi]
        stem = (q.get('passage_text', '') or '')[:300]
        sub_hints = ' | '.join(
            (sq.get('question_text', '') or '')[:80]
            for sq in q.get('sub_questions', [])[:3]
        )
        passage_lines.append(f"\nQ{qi} | tier={q.get('exercise_tier')} | passage stem: {stem}")
        passage_lines.append(f"   sub-questions hint: {sub_hints[:300]}")
    passage_block = '\n'.join(passage_lines)

    prompt = PASSAGE_PROMPT.format(
        subconcept_block=subconcept_block,
        passage_block=passage_block,
    )

    print(f'Prompt size: {len(prompt):,} chars (~{len(prompt)//4:,} tokens)')
    print('Calling LLM (passage-only redo)...')

    t0 = time.time()
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            temperature=0.2,
            max_output_tokens=4000,
            thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL),
        ),
    )
    elapsed = time.time() - t0
    um = response.usage_metadata
    tokens = {
        'input': getattr(um, 'prompt_token_count', 0) or 0,
        'output': getattr(um, 'candidates_token_count', 0) or 0,
        'cached': getattr(um, 'cached_content_token_count', 0) or 0,
        'thinking': getattr(um, 'thoughts_token_count', 0) or 0,
    }
    print(f'Tokens: input={tokens["input"]:,}, output={tokens["output"]:,}, thinking={tokens["thinking"]:,} | {elapsed:.1f}s')

    text = response.text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    result = json.loads(text)
    new_mappings = result.get('mappings', [])

    # Build lookup tables
    code_lookup = {}
    for c in schema['concepts']:
        for s in c['subconcepts']:
            code_lookup[s['id']] = {
                'name': s['name'],
                'parent_concept': c['name'],
                'parent_code': c['id'],
                'is_connecting_topic': s.get('is_connecting_topic', False),
            }
    valid_codes = set(code_lookup.keys())
    cat_lookup = {m['comp_code']: m['category'] for m in ncert_mapping['mappings']}

    # Enrich and merge into existing mappings
    successfully_mapped = []
    still_failing = []
    for m in new_mappings:
        raw = m.get('code')
        qi = m.get('q')
        diff = m.get('diff', 'Medium')
        norm, status = normalize_code(raw, valid_codes)
        if status == 'invalid':
            still_failing.append({'q_index': qi, 'raw_code_from_llm': raw, 'reason': f'redo failed: code "{raw}" not salvageable'})
            continue
        info = code_lookup[norm]
        successfully_mapped.append({
            'q_index': qi,
            'comp_code': norm,
            'comp_name': info['name'],
            'comp_parent_concept': info['parent_concept'],
            'comp_parent_code': info['parent_code'],
            'is_connecting_topic': info['is_connecting_topic'],
            'master_schema_category': cat_lookup.get(norm, 'unknown'),
            'difficulty': diff if diff in ('Easy', 'Medium', 'Hard') else 'Medium',
            '_redo_pass': True,
        })

    # Merge: add to mappings, remove resolved from redo_bucket
    resolved_qis = {m['q_index'] for m in successfully_mapped}
    mapped['mappings'].extend(successfully_mapped)
    mapped['redo_bucket'] = [
        r for r in mapped['redo_bucket']
        if r.get('q_index') not in resolved_qis
    ]
    # Add still-failing items back
    mapped['redo_bucket'].extend(still_failing)

    # Update stats
    s = mapped['stats']
    s['mapped_clean'] = len(mapped['mappings'])
    s['redo_count'] = len(mapped['redo_bucket'])
    cost_usd = (
        ((tokens['input'] - tokens['cached']) / 1e6) * PRICING['input_uncached'] +
        (tokens['cached'] / 1e6) * PRICING['input_cached'] +
        ((tokens['output'] + tokens['thinking']) / 1e6) * PRICING['output']
    )
    cost_inr = cost_usd * INR_PER_USD
    s['cost_inr'] = round(s.get('cost_inr', 0) + cost_inr, 4)
    s['cost_usd'] = round(s.get('cost_usd', 0) + cost_usd, 6)
    # Update difficulty distribution
    for m in successfully_mapped:
        d = m['difficulty']
        s['difficulty_distribution'][d] = s['difficulty_distribution'].get(d, 0) + 1

    with open(MAPPED_PATH, 'w', encoding='utf-8') as f:
        json.dump(mapped, f, indent=2, ensure_ascii=False)

    print(f'\n=== REDO RESULTS ===')
    print(f'Successfully mapped: {len(successfully_mapped)}/{len(passage_indices)}')
    print(f'Still failing:       {len(still_failing)}')
    print(f'Redo cost:           Rs {cost_inr:.4f}')
    print(f'\nUpdated final stats:')
    print(f'  Total mapped: {s["mapped_clean"]}/{s["total_input_questions"]}')
    print(f'  Redo bucket:  {s["redo_count"]}')
    print(f'  Total cost:   Rs {s["cost_inr"]}')

    print(f'\nNew passage mappings:')
    for m in successfully_mapped:
        print(f'  Q{m["q_index"]} -> {m["comp_code"]}: {m["comp_name"]}  [{m["difficulty"]}] [{m["master_schema_category"]}]')


if __name__ == '__main__':
    main()
