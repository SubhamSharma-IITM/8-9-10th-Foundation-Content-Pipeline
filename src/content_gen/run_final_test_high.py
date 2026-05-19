"""Final validation test — 3.1 Pro MEDIUM with all rules."""
import json, os, sys, time, re
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from google import genai
from google.genai import types
from prompt_templates_v2 import SYSTEM_PROMPT, build_full_prompt

BASE = os.path.join(os.path.dirname(__file__), '..', '..')

with open(os.path.join(BASE, 'experiments/01_ocr_benchmarks/mathpix/ch09_light/ch09_mathpix.mmd'), 'r', encoding='utf-8') as f:
    mmd = f.read()
with open(os.path.join(BASE, 'experiments/03_topology_generation/ch09_line_ranges.json'), 'r') as f:
    lr = json.load(f)
with open(os.path.join(BASE, 'experiments/03_topology_generation/ch09_unified_mapping.json'), 'r') as f:
    unified = json.load(f)
with open(os.path.join(BASE, 'experiments/03_topology_generation/ch09_image_codes.json'), 'r') as f:
    img_codes = json.load(f)

MODEL = 'gemini-3.1-pro-preview'
THINKING = 'HIGH'
sid = 'C2.S5'

# Image codes for this subconcept
sub_images = []
for code, info in img_codes.items():
    if info['subconcept_id'] == sid:
        sub_images.append({
            'code': code,
            'caption': info.get('caption', ''),
            'local_file': info.get('local_file'),
        })

# Build prompt
u = unified[sid]
system_prompt, user_prompt = build_full_prompt(
    sid, lr[sid]['name'], lr[sid]['line_start'], lr[sid]['line_end'],
    'NUMERICAL',
    {'scq': 1, 'subj_numerical': 1, 'subj_descriptive': 1},
    1,
    {'scq': ['N-SCQ-1', 'N-SCQ-2'], 'subj_numerical': ['N-SUBJ-1', 'N-SUBJ-2'], 'subj_descriptive': ['N-SUBJ-4']},
    u['back_exercises'] + u['intext_questions'],
    u['solved_examples'],
    sub_images,
)

client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])

# Cache
print(f"Creating cache for {MODEL}...")
cache = client.caches.create(
    model=MODEL,
    config=types.CreateCachedContentConfig(
        system_instruction=system_prompt,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=mmd)])],
        ttl=f"{3600}s",
    ),
)
print(f"Cache: {cache.name}")

# Build parts: text + images
parts = [types.Part.from_text(text=user_prompt)]
for img_info in sub_images:
    local = img_info.get('local_file')
    if local and os.path.exists(local):
        with open(local, 'rb') as f:
            img_bytes = f.read()
        parts.append(types.Part.from_text(text=f"\n[Image: {img_info['code']}]"))
        parts.append(types.Part.from_bytes(data=img_bytes, mime_type='image/jpeg'))
        print(f"  Attached: {img_info['code']} ({len(img_bytes)//1024}KB)")

# Call
config = types.GenerateContentConfig(
    response_mime_type="application/json",
    temperature=0.3,
    max_output_tokens=16000,
    thinking_config=types.ThinkingConfig(thinking_level=THINKING),
    cached_content=cache.name,
)

print(f"\nCalling {MODEL} / {THINKING}...")
start = time.time()
resp = client.models.generate_content(
    model=MODEL,
    contents=types.Content(role="user", parts=parts),
    config=config,
)
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
cost_usd = (uncached / 1e6 * 2.00) + (tokens['cached'] / 1e6 * 1.00) + ((tokens['output'] + tokens['thinking']) / 1e6 * 12.00)

print(f"Tokens: in={tokens['input']} (cached={tokens['cached']}), out={tokens['output']}, think={tokens['thinking']}")
print(f"Cost: ${cost_usd:.6f} | Rs {cost_usd * 85:.4f}")
print(f"Time: {elapsed:.1f}s")

# Parse
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
        content = json.loads(js)
    else:
        content = {'error': 'parse_failed', 'raw': raw[:500]}

# Save
result = {
    'content': content,
    'cost': {
        'tokens': tokens, 'uncached': uncached,
        'cost_usd': cost_usd, 'cost_inr': cost_usd * 85,
        'elapsed': round(elapsed, 1),
    },
}
out_path = os.path.join(BASE, 'experiments/05_content_generation/C2.S5_FINAL_3.1pro_HIGH.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
print(f"\nSaved: {out_path}")

# Print content
print(f"\n{'=' * 100}")
print(f"FINAL TEST — {MODEL} / {THINKING}")
print(f"Cost: Rs {cost_usd * 85:.2f} | Time: {elapsed:.1f}s")
print(f"{'=' * 100}")

print(f"\n--- THEORY ---")
print(content.get('theory', 'ERROR'))

for i, s in enumerate(content.get('scqs', [])):
    print(f"\n--- SCQ {i + 1} [{s.get('scq_format', '?')}, {s.get('difficulty', '?')}] ---")
    print(f"Q: {s.get('question', '')}")
    print(f"A: {s.get('answer', '')}")
    print(f"S: {s.get('solution', '')}")
    vc = s.get('visual_content', {})
    if vc.get('needed'):
        print(f"IMG: ref={vc.get('source_image_ref')} gen_needed={vc.get('image_generation_needed')}")

for i, s in enumerate(content.get('subjective', [])):
    print(f"\n--- SUBJ {i + 1} [{s.get('answer_format', '?')}, {s.get('difficulty', '?')}] ---")
    print(f"Q: {s.get('question', '')}")
    print(f"A: {s.get('answer', '')}")
    print(f"S: {s.get('solution', '')}")
    vc = s.get('visual_content', {})
    if vc.get('needed'):
        print(f"IMG: ref={vc.get('source_image_ref')} gen_needed={vc.get('image_generation_needed')}")
        if vc.get('generation_description'):
            print(f"GEN: {vc['generation_description'][:100]}")

for i, e in enumerate(content.get('examples', [])):
    print(f"\n--- EXAMPLE {i + 1} [{e.get('difficulty', '?')}] ---")
    print(f"Q: {e.get('question', '')}")
    print(f"S: {e.get('solution', '')}")

# Compliance checks
all_text = json.dumps(content, ensure_ascii=False)

has_dollar = bool(re.search(r'(?<!\\)\$(?!\$)', all_text))
has_parens = '\\(' in all_text
has_brackets = '\\[' in all_text
img_refs = re.findall(r'IMG_C\d+\.S\d+_\d+', all_text)
gen_needed = any(
    item.get('visual_content', {}).get('image_generation_needed')
    for item in content.get('scqs', []) + content.get('subjective', []) + content.get('examples', [])
)
theory_vc = content.get('theory_visual_content', {})

print(f"\n{'=' * 60}")
print(f"COMPLIANCE CHECKS")
print(f"{'=' * 60}")
print(f"LaTeX \\(...\\) used: {'PASS' if has_parens else 'FAIL'}")
print(f"LaTeX \\[...\\] used: {'PASS' if has_brackets else 'N/A (may not need display math)'}")
print(f"Dollar $ used: {'FAIL' if has_dollar else 'PASS (no $ found)'}")
print(f"Image codes referenced: {img_refs if img_refs else 'None'}")
print(f"Image generation flagged: {gen_needed}")
print(f"Theory visual content: {theory_vc}")
print(f"Output has visual_content fields: {'PASS' if 'visual_content' in json.dumps(content.get('scqs', [{}])[0]) else 'CHECK'}")
