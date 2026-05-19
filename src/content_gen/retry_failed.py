"""Retry failed subconcepts with fresh cache each round."""
import json, os, sys, time, re, math
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from google import genai
from google.genai import types
from prompt_templates_v2 import SYSTEM_PROMPT, build_full_prompt
from post_process import post_process_content, validate_latex

BASE = os.path.join(os.path.dirname(__file__), '..', '..')
MODEL = 'gemini-3.1-pro-preview'
THINKING = 'HIGH'
OUT_DIR = os.path.join(BASE, 'experiments/05_content_generation/ch09_full')

CATEGORIES = {
    'C1.S1': 'CONCEPTUAL', 'C2.S1': 'CONCEPTUAL', 'C2.S2': 'DIAGRAM',
    'C2.S3': 'DIAGRAM', 'C2.S4': 'CONCEPTUAL', 'C2.S5': 'NUMERICAL',
    'C3.S1': 'CONCEPTUAL', 'C3.S2': 'CONCEPTUAL', 'C3.S3': 'NUMERICAL',
    'C3.S4': 'CONCEPTUAL', 'C3.S5': 'DIAGRAM', 'C3.S6': 'DIAGRAM',
    'C3.S7': 'NUMERICAL', 'C3.S8': 'NUMERICAL',
}
QUESTION_CAPS = {'rich': 8, 'medium': 6, 'thin': 4}
EXAMPLE_CAPS = {'rich': 3, 'medium': 2, 'thin': 1}
SPLITS = {
    'NUMERICAL': {'scq': 0.40, 'subj_numerical': 0.40, 'subj_descriptive': 0.20},
    'CONCEPTUAL': {'scq': 0.50, 'subj_descriptive': 0.40, 'subj_numerical': 0.10},
    'DIAGRAM': {'scq': 0.40, 'subj_diagram': 0.40, 'subj_descriptive': 0.20},
}
PATTERN_MAP = {
    'NUMERICAL': {'scq': ['N-SCQ-1', 'N-SCQ-2'], 'subj_numerical': ['N-SUBJ-1', 'N-SUBJ-2'], 'subj_descriptive': ['N-SUBJ-4']},
    'CONCEPTUAL': {'scq': ['C-SCQ-1', 'C-SCQ-2', 'C-SCQ-3'], 'subj_descriptive': ['C-SUBJ-1', 'C-SUBJ-2', 'C-SUBJ-3'], 'subj_numerical': ['N-SUBJ-1']},
    'DIAGRAM': {'scq': ['D-SCQ-1', 'D-SCQ-2'], 'subj_diagram': ['D-SUBJ-1', 'D-SUBJ-2', 'D-SUBJ-3'], 'subj_descriptive': ['C-SUBJ-1']},
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


def find_failed(out_dir):
    failed = []
    for fname in sorted(os.listdir(out_dir)):
        if not fname.endswith('.json') or fname == 'ch09_full_results.json':
            continue
        with open(os.path.join(out_dir, fname), 'r') as f:
            data = json.load(f)
        if 'error' in data.get('content', {}):
            failed.append(fname.replace('.json', ''))
    return failed


def main():
    api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        print("ERROR: Set GEMINI_API_KEY")
        sys.exit(1)

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

    failed_sids = find_failed(OUT_DIR)
    max_rounds = 3
    round_num = 0

    while failed_sids and round_num < max_rounds:
        round_num += 1
        print(f"\n{'#' * 80}")
        print(f"RETRY ROUND {round_num} -- {len(failed_sids)} subconcepts: {failed_sids}")
        print(f"{'#' * 80}")

        cache = client.caches.create(
            model=MODEL,
            config=types.CreateCachedContentConfig(
                system_instruction=SYSTEM_PROMPT,
                contents=[types.Content(role="user", parts=[types.Part.from_text(text=mmd)])],
                ttl=f"{3600}s",
            ),
        )
        print(f"  Fresh cache: {cache.name}")

        still_failed = []

        for sid in failed_sids:
            data = lr[sid]
            name = data['name']
            cat = CATEGORIES[sid]
            tier = budget[sid]['tier']
            u = unified.get(sid, {})

            existing_q = u.get('total_existing', 0)
            existing_ex = u.get('total_existing_examples', 0)
            q_gen = max(0, QUESTION_CAPS[tier] - existing_q)
            e_gen = max(0, EXAMPLE_CAPS[tier] - existing_ex)
            split = compute_split(q_gen, cat) if q_gen > 0 else {}

            sub_images = [
                {'code': code, 'caption': info.get('caption', info.get('derived_caption', '')), 'local_file': info.get('local_file')}
                for code, info in img_codes.items() if info['subconcept_id'] == sid
            ]

            existing_questions = u.get('back_exercises', []) + u.get('intext_questions', [])
            existing_examples = u.get('solved_examples', [])

            _, user_prompt = build_full_prompt(
                sid, name, data['line_start'], data['line_end'],
                cat, split, e_gen, PATTERN_MAP[cat],
                existing_questions, existing_examples, sub_images,
            )

            parts = [types.Part.from_text(text=user_prompt)]
            for img_info in sub_images:
                local = img_info.get('local_file')
                if local and os.path.exists(local):
                    with open(local, 'rb') as f:
                        img_bytes = f.read()
                    parts.append(types.Part.from_text(text=f"\n[Image: {img_info['code']}]"))
                    parts.append(types.Part.from_bytes(data=img_bytes, mime_type='image/jpeg'))

            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
                max_output_tokens=16000,
                thinking_config=types.ThinkingConfig(thinking_level=THINKING),
                cached_content=cache.name,
            )

            print(f"\n  {sid}: {name}...")
            start = time.time()
            try:
                resp = client.models.generate_content(
                    model=MODEL,
                    contents=types.Content(role="user", parts=parts),
                    config=config,
                )
            except Exception as e:
                print(f"    API ERROR: {str(e)[:100]}")
                still_failed.append(sid)
                continue

            elapsed = time.time() - start
            um = resp.usage_metadata
            tokens = {
                'input': getattr(um, 'prompt_token_count', 0) or 0,
                'output': getattr(um, 'candidates_token_count', 0) or 0,
                'cached': getattr(um, 'cached_content_token_count', 0) or 0,
                'thinking': getattr(um, 'thoughts_token_count', 0) or 0,
            }
            uncached = tokens['input'] - tokens['cached']
            cost = (uncached / 1e6 * 2.00) + (tokens['cached'] / 1e6 * 1.00) + ((tokens['output'] + tokens['thinking']) / 1e6 * 12.00)

            print(f"    Tokens: out={tokens['output']}, think={tokens['thinking']} | Rs {cost * 85:.2f} | {elapsed:.1f}s")

            raw = ''
            for part in resp.candidates[0].content.parts:
                if hasattr(part, 'thought') and part.thought:
                    continue
                if hasattr(part, 'text') and part.text:
                    raw += part.text

            content = None
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
                        pass

            if content and 'error' not in content:
                content = post_process_content(content)
                checks = validate_latex(content)
                n = len(content.get('scqs', [])) + len(content.get('subjective', [])) + len(content.get('examples', []))
                print(f"    SUCCESS: {n} items | LaTeX={'PASS' if checks['latex_compliant'] else 'FAIL'}")

                result = {
                    'content': content,
                    'cost': {'tokens': tokens, 'uncached': uncached, 'cost_usd': cost, 'cost_inr': cost * 85, 'elapsed': round(elapsed, 1)},
                }
                with open(os.path.join(OUT_DIR, f'{sid}.json'), 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
            else:
                print(f"    STILL FAILED | raw={len(raw)} chars")
                still_failed.append(sid)
                result = {
                    'content': {'error': 'json_parse_failed', 'raw': raw[:2000]},
                    'cost': {'tokens': tokens, 'cost_usd': cost, 'cost_inr': cost * 85, 'elapsed': round(elapsed, 1)},
                }
                with open(os.path.join(OUT_DIR, f'{sid}.json'), 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)

        # Delete cache after round
        try:
            client.caches.delete(name=cache.name)
            print(f"\n  Cache deleted: {cache.name}")
        except:
            pass

        failed_sids = still_failed

    if failed_sids:
        print(f"\nSTILL FAILED AFTER {max_rounds} ROUNDS: {failed_sids}")
    else:
        print(f"\nALL RETRIES SUCCESSFUL after {round_num} round(s)")


if __name__ == '__main__':
    main()
