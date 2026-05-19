"""
Full Chapter Content Generator — All 14 subconcepts.

Model: gemini-3.1-pro-preview HIGH
Post-processing: image code replacement + LaTeX validation after each call.
Cache: reused across all subconcepts (created once with system prompt + MMD).
Cost tracking: per subconcept + total.
"""

import json, os, sys, time, math, re
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from google import genai
from google.genai import types
from prompt_templates_v2 import SYSTEM_PROMPT, build_full_prompt
from post_process import post_process_content, validate_latex, validate_scq_options

BASE = os.path.join(os.path.dirname(__file__), '..', '..')
MODEL = 'gemini-3.1-pro-preview'
THINKING = 'HIGH'

# Pricing
INPUT_UNCACHED_RATE = 2.00  # $/1M
INPUT_CACHED_RATE = 1.00
OUTPUT_RATE = 12.00  # includes thinking
INR_PER_USD = 85

# Caps
QUESTION_CAPS = {'rich': 8, 'medium': 6, 'thin': 4}
EXAMPLE_CAPS = {'rich': 3, 'medium': 2, 'thin': 1}

SPLITS = {
    'NUMERICAL': {'scq': 0.40, 'subj_numerical': 0.40, 'subj_descriptive': 0.20},
    'CONCEPTUAL': {'scq': 0.50, 'subj_descriptive': 0.40, 'subj_numerical': 0.10},
    'DIAGRAM': {'scq': 0.40, 'subj_diagram': 0.40, 'subj_descriptive': 0.20},
    'FACTUAL': {'scq': 0.60, 'subj_descriptive': 0.40},
}

PATTERN_MAP = {
    'NUMERICAL': {'scq': ['N-SCQ-1', 'N-SCQ-2'], 'subj_numerical': ['N-SUBJ-1', 'N-SUBJ-2'], 'subj_descriptive': ['N-SUBJ-4']},
    'CONCEPTUAL': {'scq': ['C-SCQ-1', 'C-SCQ-2', 'C-SCQ-3'], 'subj_descriptive': ['C-SUBJ-1', 'C-SUBJ-2', 'C-SUBJ-3'], 'subj_numerical': ['N-SUBJ-1']},
    'DIAGRAM': {'scq': ['D-SCQ-1', 'D-SCQ-2'], 'subj_diagram': ['D-SUBJ-1', 'D-SUBJ-2', 'D-SUBJ-3'], 'subj_descriptive': ['C-SUBJ-1']},
    'FACTUAL': {'scq': ['F-SCQ-1', 'F-SCQ-2'], 'subj_descriptive': ['F-SUBJ-1', 'F-SUBJ-2']},
}

CATEGORIES = {
    'C1.S1': 'CONCEPTUAL', 'C2.S1': 'CONCEPTUAL', 'C2.S2': 'DIAGRAM',
    'C2.S3': 'DIAGRAM', 'C2.S4': 'CONCEPTUAL', 'C2.S5': 'NUMERICAL',
    'C3.S1': 'CONCEPTUAL', 'C3.S2': 'CONCEPTUAL', 'C3.S3': 'NUMERICAL',
    'C3.S4': 'CONCEPTUAL', 'C3.S5': 'DIAGRAM', 'C3.S6': 'DIAGRAM',
    'C3.S7': 'NUMERICAL', 'C3.S8': 'NUMERICAL',
}


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


def main():
    api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        print("ERROR: Set GEMINI_API_KEY")
        sys.exit(1)

    # Load all data
    with open(os.path.join(BASE, 'experiments/01_ocr_benchmarks/mathpix/ch09_light/ch09_mathpix.mmd'), 'r', encoding='utf-8') as f:
        mmd = f.read()
    with open(os.path.join(BASE, 'experiments/03_topology_generation/ch09_line_ranges.json'), 'r') as f:
        lr = json.load(f)
    with open(os.path.join(BASE, 'experiments/03_topology_generation/ch09_unified_mapping.json'), 'r') as f:
        unified = json.load(f)
    with open(os.path.join(BASE, 'experiments/03_topology_generation/ch09_generation_budget.json'), 'r') as f:
        budget = json.load(f)
    with open(os.path.join(BASE, 'experiments/03_topology_generation/ch09_image_codes.json'), 'r') as f:
        img_codes = json.load(f)

    client = genai.Client(api_key=api_key)

    # Create cache ONCE for entire chapter
    print(f"Creating cache for {MODEL} / {THINKING}...")
    cache = client.caches.create(
        model=MODEL,
        config=types.CreateCachedContentConfig(
            system_instruction=SYSTEM_PROMPT,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=mmd)])],
            ttl=f"{3600}s",
        ),
    )
    print(f"Cache: {cache.name}\n")

    # Output directory
    out_dir = os.path.join(BASE, 'experiments/05_content_generation/ch09_full')
    os.makedirs(out_dir, exist_ok=True)

    # Track totals
    total_cost_usd = 0
    total_time = 0
    total_items = 0
    results = {}
    generation_flags = []

    # Generate for each subconcept
    for sid in sorted(lr.keys()):
        data = lr[sid]
        name = data['name']
        cat = CATEGORIES[sid]
        tier = budget[sid]['tier']
        u = unified.get(sid, {})

        existing_q = u.get('total_existing', 0)
        existing_ex = u.get('total_existing_examples', 0)
        q_gen = max(0, QUESTION_CAPS[tier] - existing_q)
        e_gen = max(0, EXAMPLE_CAPS[tier] - existing_ex)

        if q_gen == 0 and e_gen == 0:
            print(f"\n{sid}: {name} — SKIP (cap filled)")
            continue

        split = compute_split(q_gen, cat) if q_gen > 0 else {}

        # Image codes for this subconcept
        sub_images = [
            {'code': code, 'caption': info.get('caption', info.get('derived_caption', '')), 'local_file': info.get('local_file')}
            for code, info in img_codes.items()
            if info['subconcept_id'] == sid
        ]

        # Build prompt
        existing_questions = u.get('back_exercises', []) + u.get('intext_questions', [])
        existing_examples = u.get('solved_examples', [])

        _, user_prompt = build_full_prompt(
            sid, name, data['line_start'], data['line_end'],
            cat, split, e_gen, PATTERN_MAP[cat],
            existing_questions, existing_examples, sub_images,
        )

        # Build parts: text + images
        parts = [types.Part.from_text(text=user_prompt)]
        for img_info in sub_images:
            local = img_info.get('local_file')
            if local and os.path.exists(local):
                with open(local, 'rb') as f:
                    img_bytes = f.read()
                parts.append(types.Part.from_text(text=f"\n[Image: {img_info['code']}]"))
                parts.append(types.Part.from_bytes(data=img_bytes, mime_type='image/jpeg'))

        # Call model
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.3,
            max_output_tokens=16000,
            thinking_config=types.ThinkingConfig(thinking_level=THINKING),
            cached_content=cache.name,
        )

        print(f"\n{'='*80}")
        print(f"{sid}: {name} [{cat}, {tier}]")
        print(f"  Generate: {q_gen} questions ({split}) + {e_gen} examples")
        print(f"  Images: {len(sub_images)} attached")

        start = time.time()
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=types.Content(role="user", parts=parts),
                config=config,
            )
        except Exception as e:
            print(f"  ERROR: {str(e)[:200]}")
            results[sid] = {'error': str(e)[:200]}
            continue

        elapsed = time.time() - start

        # Tokens + cost
        um = resp.usage_metadata
        tokens = {
            'input': getattr(um, 'prompt_token_count', 0) or 0,
            'output': getattr(um, 'candidates_token_count', 0) or 0,
            'cached': getattr(um, 'cached_content_token_count', 0) or 0,
            'thinking': getattr(um, 'thoughts_token_count', 0) or 0,
        }
        uncached = tokens['input'] - tokens['cached']
        cost = (uncached / 1e6 * INPUT_UNCACHED_RATE) + (tokens['cached'] / 1e6 * INPUT_CACHED_RATE) + ((tokens['output'] + tokens['thinking']) / 1e6 * OUTPUT_RATE)

        total_cost_usd += cost
        total_time += elapsed

        print(f"  Tokens: in={tokens['input']} (cached={tokens['cached']}), out={tokens['output']}, think={tokens['thinking']}")
        print(f"  Cost: ${cost:.4f} | Rs {cost * INR_PER_USD:.2f} | Time: {elapsed:.1f}s")

        # Parse response
        raw = ''
        for part in resp.candidates[0].content.parts:
            if hasattr(part, 'thought') and part.thought:
                continue
            if hasattr(part, 'text') and part.text:
                raw += part.text

        try:
            content = json.loads(raw.strip())
        except json.JSONDecodeError:
            brace = re.search(r'\{.*', raw, re.DOTALL)
            if brace:
                js = brace.group()
                while js.count('{') > js.count('}'):
                    js += '}'
                while js.count('[') > js.count(']'):
                    js += ']'
                try:
                    content = json.loads(js)
                except:
                    content = {'error': 'json_parse_failed', 'raw': raw[:2000]}
            else:
                content = {'error': 'no_json', 'raw': raw[:2000]}

        # Post-process: replace image codes, strip NCERT figure numbers
        if 'error' not in content:
            content = post_process_content(content)
            checks = validate_latex(content)
            print(f"  Validation: LaTeX={'PASS' if checks['latex_compliant'] else 'FAIL'} | ImgClean={'PASS' if checks['image_codes_clean'] else 'FAIL'} | NCERTClean={'PASS' if checks['ncert_refs_clean'] else 'FAIL'}")

            # Count generated items
            n_scq = len(content.get('scqs', []))
            n_subj = len(content.get('subjective', []))
            n_ex = len(content.get('examples', []))
            total_items += n_scq + n_subj + n_ex
            print(f"  Generated: {n_scq} SCQs + {n_subj} Subjective + {n_ex} Examples")

            # Check for image generation flags
            all_items = content.get('scqs', []) + content.get('subjective', []) + content.get('examples', [])
            for item in all_items:
                vc = item.get('visual_content', {})
                if vc.get('image_generation_needed'):
                    flag = {
                        'subconcept_id': sid,
                        'question': item.get('question', '')[:80],
                        'generation_description': vc.get('generation_description', ''),
                    }
                    generation_flags.append(flag)
                    print(f"  IMAGE GEN FLAG: {flag['generation_description'][:60]}")

            tvc = content.get('theory_visual_content', {})
            if tvc.get('image_generation_needed'):
                generation_flags.append({
                    'subconcept_id': sid,
                    'type': 'theory',
                    'generation_description': tvc.get('generation_description', ''),
                })

        # Save individual result
        result_data = {
            'content': content,
            'cost': {
                'tokens': tokens, 'uncached': uncached,
                'cost_usd': cost, 'cost_inr': cost * INR_PER_USD,
                'elapsed': round(elapsed, 1),
            },
        }
        results[sid] = result_data

        with open(os.path.join(out_dir, f'{sid}.json'), 'w', encoding='utf-8') as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)

    # Save combined results
    combined = {
        'model': MODEL,
        'thinking': THINKING,
        'total_cost_usd': total_cost_usd,
        'total_cost_inr': total_cost_usd * INR_PER_USD,
        'total_time_seconds': round(total_time, 1),
        'total_items_generated': total_items,
        'subconcepts': results,
        'image_generation_flags': generation_flags,
    }

    with open(os.path.join(out_dir, 'ch09_full_results.json'), 'w', encoding='utf-8') as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)

    # Final summary
    print(f"\n{'='*80}")
    print(f"GENERATION COMPLETE")
    print(f"{'='*80}")
    print(f"  Model: {MODEL} / {THINKING}")
    print(f"  Subconcepts processed: {len([r for r in results.values() if 'error' not in r])}")
    print(f"  Total items generated: {total_items}")
    print(f"  Total cost: ${total_cost_usd:.4f} USD | Rs {total_cost_usd * INR_PER_USD:.2f}")
    print(f"  Total time: {total_time:.0f}s ({total_time/60:.1f} min)")
    print(f"  Image generation flags: {len(generation_flags)}")
    if generation_flags:
        for flag in generation_flags:
            print(f"    - {flag['subconcept_id']}: {flag.get('generation_description', '')[:60]}")
    print(f"\n  Results: {out_dir}/")


if __name__ == '__main__':
    main()
