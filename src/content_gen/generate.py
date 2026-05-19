"""
Content Generator — Test run on one subconcept.

Uses Gemini 3 Flash Preview with MEDIUM thinking + content caching.
Follows Stage 2 caching pattern from reference pipeline.
"""

import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from google import genai
from google.genai import types
from prompt_templates import SYSTEM_PROMPT, build_full_prompt

MODEL = "gemini-3-flash-preview"
THINKING_LEVEL = os.environ.get('THINKING_LEVEL', 'MEDIUM')
API_KEY = os.environ.get('GEMINI_API_KEY', '')


def generate_for_subconcept(
    subconcept_id: str,
    chapter_mmd: str,
    line_ranges: dict,
    unified_mapping: dict,
    categories: dict,
    type_splits: dict,
    pattern_assignments: dict,
    budget: dict,
    client=None,
    cache_handle=None,
) -> tuple:
    """
    Generate content for one subconcept.

    Returns (result_dict, cache_handle, cost_dict)
    """
    lr = line_ranges[subconcept_id]
    u = unified_mapping.get(subconcept_id, {})
    b = budget[subconcept_id]

    sid = subconcept_id
    name = lr['name']
    line_start = lr['line_start']
    line_end = lr['line_end']
    category = categories[sid]
    split = type_splits[sid]
    examples_gen = b['examples_to_generate']
    patterns = pattern_assignments[category]
    existing_q = u.get('back_exercises', []) + u.get('intext_questions', [])
    existing_ex = u.get('solved_examples', [])

    # Build prompts
    system_prompt, user_prompt = build_full_prompt(
        sid, name, line_start, line_end,
        category, split, examples_gen, patterns,
        existing_q, existing_ex,
    )

    # Create cache if needed (system prompt + MMD)
    if cache_handle is None:
        try:
            cache_handle = client.caches.create(
                model=MODEL,
                config=types.CreateCachedContentConfig(
                    system_instruction=system_prompt,
                    contents=[types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=chapter_mmd)]
                    )],
                    ttl=f"{3600}s",
                ),
            )
            print(f"  Cache created: {cache_handle.name}")
        except Exception as e:
            print(f"  Cache failed: {e}")
            cache_handle = None

    # Build config
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.3,
        max_output_tokens=16000,
        thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL),
    )

    if cache_handle:
        config.cached_content = cache_handle.name
    else:
        config.system_instruction = system_prompt

    # Call model
    print(f"  Calling Gemini for {sid}...")
    start_time = time.time()

    response = client.models.generate_content(
        model=MODEL,
        contents=user_prompt,
        config=config,
    )

    elapsed = time.time() - start_time

    # Extract tokens
    um = response.usage_metadata
    tokens = {
        'input': getattr(um, 'prompt_token_count', 0) or 0,
        'output': getattr(um, 'candidates_token_count', 0) or 0,
        'cached': getattr(um, 'cached_content_token_count', 0) or 0,
        'thinking': getattr(um, 'thoughts_token_count', 0) or 0,
    }
    uncached = tokens['input'] - tokens['cached']
    cost_usd = (uncached/1e6*0.50) + (tokens['cached']/1e6*0.25) + ((tokens['output']+tokens['thinking'])/1e6*3.00)

    cost = {
        'tokens': tokens,
        'uncached': uncached,
        'cost_usd': cost_usd,
        'cost_inr': cost_usd * 85,
        'elapsed_seconds': round(elapsed, 1),
    }

    print(f"  Tokens: input={tokens['input']} (cached={tokens['cached']}), output={tokens['output']}, thinking={tokens['thinking']}")
    print(f"  Cost: ${cost_usd:.6f} USD | Rs {cost['cost_inr']:.4f} INR")
    print(f"  Time: {elapsed:.1f}s")

    # Parse response
    raw_text = ""
    for part in response.candidates[0].content.parts:
        if hasattr(part, 'thought') and part.thought:
            continue
        if hasattr(part, 'text') and part.text:
            raw_text += part.text

    try:
        result = json.loads(raw_text.strip())
    except json.JSONDecodeError:
        import re
        brace = re.search(r'\{.*', raw_text, re.DOTALL)
        if brace:
            json_str = brace.group()
            # Fix truncation
            while json_str.count('{') > json_str.count('}'):
                json_str += '}'
            while json_str.count('[') > json_str.count(']'):
                json_str += ']'
            try:
                result = json.loads(json_str)
            except:
                result = {'error': 'json_parse_failed', 'raw': raw_text[:500]}
        else:
            result = {'error': 'no_json_found', 'raw': raw_text[:500]}

    return result, cache_handle, cost


if __name__ == '__main__':
    if not API_KEY:
        print("ERROR: Set GEMINI_API_KEY")
        sys.exit(1)

    # Load all data
    with open('experiments/01_ocr_benchmarks/mathpix/ch09_light/ch09_mathpix.mmd', 'r', encoding='utf-8') as f:
        mmd = f.read()
    with open('experiments/03_topology_generation/ch09_line_ranges.json', 'r') as f:
        lr = json.load(f)
    with open('experiments/03_topology_generation/ch09_unified_mapping.json', 'r') as f:
        unified = json.load(f)
    with open('experiments/03_topology_generation/ch09_generation_budget.json', 'r') as f:
        budget = json.load(f)

    # Hardcoded from our analysis
    categories = {
        'C1.S1': 'CONCEPTUAL', 'C2.S1': 'CONCEPTUAL', 'C2.S2': 'DIAGRAM',
        'C2.S3': 'DIAGRAM', 'C2.S4': 'CONCEPTUAL', 'C2.S5': 'NUMERICAL',
        'C3.S1': 'CONCEPTUAL', 'C3.S2': 'CONCEPTUAL', 'C3.S3': 'NUMERICAL',
        'C3.S4': 'CONCEPTUAL', 'C3.S5': 'DIAGRAM', 'C3.S6': 'DIAGRAM',
        'C3.S7': 'NUMERICAL', 'C3.S8': 'NUMERICAL',
    }

    SPLITS = {
        'NUMERICAL':  {'scq': 0.40, 'subj_numerical': 0.40, 'subj_descriptive': 0.20},
        'CONCEPTUAL': {'scq': 0.50, 'subj_descriptive': 0.40, 'subj_numerical': 0.10},
        'DIAGRAM':    {'scq': 0.40, 'subj_diagram': 0.40, 'subj_descriptive': 0.20},
        'FACTUAL':    {'scq': 0.60, 'subj_descriptive': 0.40},
    }

    QUESTION_CAPS = {'rich': 8, 'medium': 6, 'thin': 4}

    PATTERN_MAP = {
        'NUMERICAL': {'scq': ['N-SCQ-1', 'N-SCQ-2'], 'subj_numerical': ['N-SUBJ-1', 'N-SUBJ-2'], 'subj_descriptive': ['N-SUBJ-4']},
        'CONCEPTUAL': {'scq': ['C-SCQ-1', 'C-SCQ-2', 'C-SCQ-3'], 'subj_descriptive': ['C-SUBJ-1', 'C-SUBJ-2', 'C-SUBJ-3'], 'subj_numerical': ['N-SUBJ-1']},
        'DIAGRAM': {'scq': ['D-SCQ-1', 'D-SCQ-2'], 'subj_diagram': ['D-SUBJ-1', 'D-SUBJ-2', 'D-SUBJ-3'], 'subj_descriptive': ['C-SUBJ-1']},
        'FACTUAL': {'scq': ['F-SCQ-1', 'F-SCQ-2'], 'subj_descriptive': ['F-SUBJ-1', 'F-SUBJ-2']},
    }

    import math
    def compute_split(N, category):
        split = SPLITS[category]
        result = {}
        total = 0
        for stype, prop in split.items():
            count = round(N * prop)
            result[stype] = count
            total += count
        diff = N - total
        if diff != 0:
            largest = max(result, key=result.get)
            result[largest] += diff
        return {k: v for k, v in result.items() if v > 0}

    # Compute type splits for all subconcepts
    type_splits = {}
    for sid in lr:
        cat = categories[sid]
        existing = unified.get(sid, {}).get('total_existing', 0)
        q_gen = max(0, QUESTION_CAPS[budget[sid]['tier']] - existing)
        type_splits[sid] = compute_split(q_gen, cat) if q_gen > 0 else {}

    # Test on C2.S5
    test_sid = sys.argv[1] if len(sys.argv) > 1 else 'C2.S5'
    print(f"=" * 80)
    print(f"GENERATING CONTENT FOR {test_sid}: {lr[test_sid]['name']}")
    print(f"=" * 80)

    client = genai.Client(api_key=API_KEY)

    result, cache, cost = generate_for_subconcept(
        test_sid, mmd, lr, unified, categories,
        type_splits, PATTERN_MAP, budget,
        client=client,
    )

    # Save
    output_path = f'experiments/05_content_generation/{test_sid}_generated.json'
    os.makedirs('experiments/05_content_generation', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({'content': result, 'cost': cost}, f, indent=2, ensure_ascii=False)

    print(f"\n=== GENERATED CONTENT ===")
    print(json.dumps(result, indent=2, ensure_ascii=False)[:3000])
    print(f"\nSaved: {output_path}")
