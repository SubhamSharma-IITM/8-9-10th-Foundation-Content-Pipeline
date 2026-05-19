"""
Step 6+7: NCERT <-> Competitive subconcept mapping via LLM.
Uses the lean prompt template (step6_prompt_template.py).
"""
import json, os, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from google import genai
from google.genai import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from step6_prompt_template import build_prompt

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
MODEL = 'gemini-3-flash-preview'
THINKING_LEVEL = 'LOW'  # HIGH/MEDIUM eat entire output budget on thinking; LOW leaves room for 41 mappings

api_key = os.environ.get('GEMINI_API_KEY', '')
if not api_key:
    print('ERROR: Set GEMINI_API_KEY')
    sys.exit(1)

client = genai.Client(api_key=api_key)


def build_inputs():
    """Load and format NCERT + Competitive data for the prompt."""
    with open(os.path.join(BASE, 'experiments/03_topology_generation/ch09_schema.json'), 'r', encoding='utf-8') as f:
        ncert = json.load(f)
    with open(os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_schema_sealed.json'), 'r', encoding='utf-8') as f:
        comp = json.load(f)
    with open(os.path.join(BASE, 'experiments/01_ocr_benchmarks/mathpix/ch01_light_competitive/ch01_light_competitive.mmd'), 'r', encoding='utf-8') as f:
        mmd_lines = f.readlines()

    # NCERT block
    ncert_lines = []
    ch_name = list(ncert.keys())[0]
    c_idx = 1
    ncert_count = 0
    for cn, subs in ncert[ch_name].items():
        s_idx = 1
        for sn in subs:
            ncert_lines.append(f'  NCRT_C{c_idx}.S{s_idx} | Parent: {cn} | Sub: {sn}')
            s_idx += 1
            ncert_count += 1
        c_idx += 1
    ncert_block = '\n'.join(ncert_lines)

    # Competitive block
    comp_lines = []
    comp_count = 0
    for concept in comp['concepts']:
        for sub in concept['subconcepts']:
            comp_count += 1
            start = sub['line_start']
            end = min(sub['line_end'], start + 20)
            preview = []
            for i in range(start, min(end, len(mmd_lines))):
                line = mmd_lines[i].strip() if i < len(mmd_lines) else ''
                if not line or line.startswith('\\section') or line.startswith('!['):
                    continue
                if line.startswith('\\begin') or line.startswith('\\end'):
                    continue
                preview.append(line[:200])
                if len(preview) >= 3:
                    break
            tag = ' [CONNECTING_TOPIC]' if sub.get('is_connecting_topic') else ''
            comp_lines.append(f'  {sub["id"]}{tag} | Parent: {concept["name"]} | Sub: {sub["name"]}')
            comp_lines.append(f'    Content: {(" | ".join(preview))[:250] if preview else "(sparse)"}')
            comp_lines.append('')
    comp_block = '\n'.join(comp_lines)

    return ncert_block, comp_block, ncert_count, comp_count


def run_mapping():
    ncert_block, comp_block, ncert_count, comp_count = build_inputs()

    prompt = build_prompt(
        subject='Physics',
        class_level='10',
        chapter_number=1,
        chapter_name='Light - Reflection and Refraction',
        ncert_block=ncert_block,
        competitive_block=comp_block,
        ncert_count=ncert_count,
        competitive_count=comp_count,
    )

    print('=' * 70)
    print('STEP 6: NCERT <-> COMPETITIVE MAPPING')
    print('=' * 70)
    print(f'Model: {MODEL}')
    print(f'NCERT subconcepts: {ncert_count}')
    print(f'Competitive subconcepts: {comp_count}')
    print(f'Prompt size: {len(prompt)} chars (~{len(prompt)//4} tokens)')
    print()
    print(f'Calling {MODEL}...')

    t0 = time.time()
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            temperature=0.1,
            max_output_tokens=32000,
            thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL),
        )
    )
    elapsed = time.time() - t0

    print(f'Response received in {elapsed:.1f}s')
    print(f'Response length: {len(response.text)} chars')

    # Save raw for debugging
    raw_path = os.path.join(BASE, 'experiments/03_topology_generation/competitive/step6_raw_response.txt')
    with open(raw_path, 'w', encoding='utf-8') as f:
        f.write(response.text)

    try:
        result = json.loads(response.text)
    except Exception as e:
        print(f'JSON parse error: {e}')
        print(f'Raw saved to: {raw_path}')
        print(f'Last 300 chars: {response.text[-300:]}')
        return

    mappings = result.get('mappings', [])
    ncert_only = result.get('ncert_only', [])

    overlap = [m for m in mappings if m.get('category') == 'overlap']
    comp_only = [m for m in mappings if m.get('category') == 'competitive_only']

    out_path = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_mapping_verified.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print()
    print('=' * 70)
    print('RESULTS')
    print('=' * 70)
    print(f'Total mappings:   {len(mappings)} / {comp_count}')
    print(f'Overlap:          {len(overlap)}')
    print(f'Competitive-only: {len(comp_only)}')
    print(f'NCERT-only:       {len(ncert_only)}')
    print(f'Saved: {out_path}')

    # Quality checks
    print()
    print('=' * 70)
    print('QUALITY CHECKS')
    print('=' * 70)
    issues = []

    # Check exact count
    if len(mappings) != comp_count:
        issues.append(f'COUNT MISMATCH: {len(mappings)} mappings vs {comp_count} expected')

    # Check all NCERT codes appear
    ncert_codes_expected = set()
    for i in range(1, 4):
        for j in range(1, 10):
            code = f'NCRT_C{i}.S{j}'
            # Build from ncert_block
            if code in ncert_block:
                ncert_codes_expected.add(code)

    ncert_codes_seen = set()
    for m in mappings:
        if m.get('ncert_code'):
            ncert_codes_seen.add(m['ncert_code'])
    for n in ncert_only:
        if n.get('ncert_code'):
            ncert_codes_seen.add(n['ncert_code'])

    missing_ncert = ncert_codes_expected - ncert_codes_seen
    invented_ncert = ncert_codes_seen - ncert_codes_expected
    if missing_ncert:
        issues.append(f'MISSING NCERT codes: {missing_ncert}')
    if invented_ncert:
        issues.append(f'INVENTED NCERT codes: {invented_ncert}')

    if not issues:
        print('All quality checks PASSED')
    else:
        for issue in issues:
            print(f'  ISSUE: {issue}')

    # Print sample mappings
    print()
    print('=' * 70)
    print('SAMPLE RESULTS (first 15 overlaps + all competitive_only)')
    print('=' * 70)
    print()
    print('--- OVERLAPS ---')
    for m in overlap[:15]:
        print(f'  {m["comp_code"]:14s} {m["comp_name"][:35]:35s} -> {m["ncert_code"]:12s} {m["ncert_name"][:40]}')

    if len(overlap) > 15:
        print(f'  ... +{len(overlap)-15} more overlaps')

    print()
    print('--- COMPETITIVE-ONLY ---')
    for m in comp_only:
        print(f'  {m["comp_code"]:14s} {m["comp_name"]}')

    if ncert_only:
        print()
        print('--- NCERT-ONLY (no competitive match) ---')
        for n in ncert_only:
            print(f'  {n["ncert_code"]:14s} {n["ncert_name"]}')


if __name__ == '__main__':
    run_mapping()
