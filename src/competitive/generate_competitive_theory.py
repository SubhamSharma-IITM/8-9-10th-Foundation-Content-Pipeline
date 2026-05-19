"""
Step 11: Generate theory for 12 competitive-only subconcepts.

Forked from src/content_gen/generate_full_chapter.py (NCERT pattern):
- Cache creation pattern with system + MMD reuse across all 12 calls
- gemini-3.1-pro-preview HIGH thinking (same as NCERT for quality)
- Cost tracking via usage_metadata

Surgical changes for competitive theory-only:
- THEORY ONLY — no questions, no examples, no capacity formulas
- Tone: NCERT teacher style + NTSE/KVPY/JSTSE awareness
- Output: theory text + key_formulas + VisualContent

Usage:
  python src/competitive/generate_competitive_theory.py            # all 12
  python src/competitive/generate_competitive_theory.py SAMPLE     # one only
  python src/competitive/generate_competitive_theory.py REDO       # only failed ones
"""
import json, os, sys, time, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from google import genai
from google.genai import types

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
MMD_PATH = os.path.join(BASE, 'experiments/01_ocr_benchmarks/mathpix/ch01_light_competitive/ch01_light_competitive.mmd')
SCHEMA_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_schema_sealed.json')
MAPPING_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_mapping_verified.json')
OUT_DIR = os.path.join(BASE, 'experiments/05_content_generation/comp_theory')
os.makedirs(OUT_DIR, exist_ok=True)

MODEL = 'gemini-3.1-pro-preview'
THINKING = 'HIGH'
PRICING = {'input_uncached': 2.00, 'input_cached': 1.00, 'output': 12.00}
INR_PER_USD = 85


SYSTEM_PROMPT = r"""You are an experienced CBSE Class 10 Physics teacher who also coaches students for competitive exams (NTSE, KVPY, JSTSE, Olympiad).

You are creating THEORY content for one subconcept at a time, drawn from the competitive coaching foundation book chapter cached below. Each subconcept will be requested separately.

## YOUR ROLE
- Speak directly to a Class 10 student preparing for board exams AND competitive exams
- Tone: warm, clear, teacher-like (same as a good NCERT teacher would explain), but slightly denser with formulas because competitive students need them
- Build from intuition first, then formal definitions, then formulas, then derivations (where appropriate)
- Anticipate student confusion points and address them inline

## WHAT YOU GENERATE
**THEORY ONLY.** Do NOT generate:
- Questions (already extracted from exercise sections)
- Solved examples (already extracted)
- Practice problems
- "Test yourself" sections

Only the explanatory theory text + key formulas + visual content metadata.

## CONTENT GROUNDING
- Read the line range provided for each subconcept from the cached chapter MMD
- Theory must be GROUNDED in those lines — do not invent content not present in the source
- You may reorganize, simplify, or expand explanations for student clarity
- For derivations, follow the source PDF's logic but write more student-friendly steps

## MATHEMATICAL NOTATION (CRITICAL)
- Inline math: \(...\)  Example: The focal length is \( f = R/2 \)
- Display math: \[...\]  Example: \[ \frac{1}{f} = (\mu - 1)\left(\frac{1}{R_1} - \frac{1}{R_2}\right) \]
- NEVER use $...$ or $$...$$ delimiters
- All formulas, variables, and equations MUST be in LaTeX

## FORMATTING
- **Bold** key terms on first introduction (e.g., "This is called the **lens maker formula**")
- Use numbered lists for step-by-step derivations (1. 2. 3.)
- Use bullet points for properties or rules
- Keep paragraphs short (3-4 sentences max)
- For competitive-only/connecting topics, briefly note: "This is beyond NCERT Class 10 syllabus but important for competitive exams"

## OUTPUT FORMAT — STRICT JSON
{
  "subconcept_code": "COMP_C29.S2",
  "subconcept_name": "Lens Maker Formula",
  "theory": "Full theory text with \(...\) LaTeX, **bold terms**, numbered derivations, and short paragraphs...",
  "key_formulas": [
    "\\frac{1}{f} = (\\mu - 1)\\left(\\frac{1}{R_1} - \\frac{1}{R_2}\\right)",
    "..."
  ],
  "VisualContent": {
    "needed": false,
    "source_image_ref": null,
    "image_generation_needed": false,
    "image_description": null,
    "generation_description": null
  }
}

CRITICAL: Return raw JSON only. No markdown fences, no commentary.
"""


def build_user_prompt(sub_info):
    """Build per-subconcept user prompt."""
    code = sub_info['code']
    name = sub_info['name']
    parent = sub_info['parent_concept']
    tier = sub_info['tier']
    line_start = sub_info['line_start']
    line_end = sub_info['line_end']
    is_conn = sub_info['is_connecting_topic']
    formulas = sub_info['formulas']
    figures = sub_info['figures']

    conn_note = ""
    if is_conn:
        conn_note = "\n## NOTE: This is a CONNECTING_TOPIC — advanced material from Class 11-12 included for competitive exam preparation. Bridge it to Class 10 understanding without dumbing it down."

    tier_guidance = {
        'thin': 'Theory should be concise (~200-400 words). Focus on the core idea + key formula.',
        'medium': 'Theory should be substantive (~400-700 words). Include derivation if formulas present in source.',
        'rich': 'Theory should be thorough (~700-1200 words). Include intuition, derivation steps, special cases, and applications mentioned in source.',
    }

    return f"""# GENERATE THEORY FOR ONE SUBCONCEPT

**Subconcept code:** {code}
**Subconcept name:** {name}
**Parent concept:** {parent}
**Source line range in cached chapter:** Lines {line_start} to {line_end}
**Tier:** {tier} ({tier_guidance[tier]})
**Source content stats:** {formulas} formulas, {figures} figures in source range
{conn_note}

## TASK
Read the cached chapter content at lines {line_start}-{line_end}. Generate teacher-quality theory text for this subconcept.

Write theory ONLY — no questions, no examples, no exercises (those are extracted separately).

Use the system prompt's tone, formatting rules, LaTeX delimiters, and JSON output schema.
"""


def load_targets():
    """Load the 12 competitive-only subconcepts from mapping."""
    with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
        mapping = json.load(f)
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    code_info = {}
    for c in schema['concepts']:
        for s in c['subconcepts']:
            code_info[s['id']] = {
                'code': s['id'],
                'name': s['name'],
                'parent_concept': c['name'],
                'tier': s.get('tier', 'thin'),
                'is_connecting_topic': s.get('is_connecting_topic', False),
                'line_start': s['line_start'],
                'line_end': s['line_end'],
                'line_count': s['line_count'],
                'formulas': s['formulas'],
                'figures': s['figures'],
            }

    targets = []
    for m in mapping['mappings']:
        if m['category'] == 'competitive_only':
            targets.append(code_info[m['comp_code']])
    return targets


def call_model(client, cache, sub_info):
    """Generate theory for one subconcept."""
    user_prompt = build_user_prompt(sub_info)

    config = types.GenerateContentConfig(
        response_mime_type='application/json',
        temperature=0.3,
        max_output_tokens=8000,
        thinking_config=types.ThinkingConfig(thinking_level=THINKING),
        cached_content=cache.name,
    )

    t0 = time.time()
    response = client.models.generate_content(
        model=MODEL,
        contents=user_prompt,
        config=config,
    )
    elapsed = time.time() - t0

    um = response.usage_metadata
    tokens = {
        'input': getattr(um, 'prompt_token_count', 0) or 0,
        'output': getattr(um, 'candidates_token_count', 0) or 0,
        'cached': getattr(um, 'cached_content_token_count', 0) or 0,
        'thinking': getattr(um, 'thoughts_token_count', 0) or 0,
        'elapsed_s': elapsed,
    }

    raw_text = ''
    for part in response.candidates[0].content.parts:
        if hasattr(part, 'thought') and part.thought:
            continue
        if hasattr(part, 'text') and part.text:
            raw_text += part.text

    text = raw_text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()

    try:
        result = json.loads(text)
    except Exception as e:
        result = {'error': f'json_parse_failed: {e}', 'raw': text[:500]}

    return result, tokens


def cost_inr(tokens):
    uncached = tokens['input'] - tokens['cached']
    cost_usd = (
        (uncached / 1e6) * PRICING['input_uncached'] +
        (tokens['cached'] / 1e6) * PRICING['input_cached'] +
        ((tokens['output'] + tokens['thinking']) / 1e6) * PRICING['output']
    )
    return cost_usd, cost_usd * INR_PER_USD


def validate_theory(result, sub_info):
    """Quality checks. Returns list of issues."""
    issues = []
    if 'error' in result:
        issues.append(f'parse error: {result["error"]}')
        return issues
    if not result.get('theory'):
        issues.append('missing theory field')
    else:
        theory = result['theory']
        # LaTeX presence
        if '\\(' not in theory and '\\[' not in theory and sub_info['formulas'] > 0:
            issues.append('source has formulas but theory has no LaTeX')
        # Forbidden $ delimiters
        if re.search(r'(?<!\\)\$[^$]+\$', theory):
            issues.append('theory uses forbidden $...$ delimiters')
        # Bold terms
        if theory.count('**') < 4:
            issues.append('fewer than 2 bold key terms')
        # Length per tier
        tier_min = {'thin': 200, 'medium': 400, 'rich': 700}
        if len(theory) < tier_min.get(sub_info['tier'], 200):
            issues.append(f'theory too short for tier={sub_info["tier"]} ({len(theory)} chars)')
    if 'VisualContent' not in result:
        issues.append('missing VisualContent field')
    return issues


def main():
    mode = sys.argv[1].upper() if len(sys.argv) > 1 else 'ALL'

    api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        print('ERROR: Set GEMINI_API_KEY')
        sys.exit(1)

    targets = load_targets()
    print(f'Total competitive-only subconcepts: {len(targets)}')

    if mode == 'SAMPLE':
        # Pick first medium tier non-connecting target for sample
        targets = [t for t in targets if t['tier'] == 'medium' and not t['is_connecting_topic']][:1]
        print(f'SAMPLE mode: generating only {targets[0]["code"]}: {targets[0]["name"]}')
    elif mode == 'REDO':
        # Find which targets don't have output yet or have validation issues
        existing = set()
        for f in os.listdir(OUT_DIR):
            if f.endswith('.json') and f.startswith('COMP_'):
                code = f.replace('.json', '')
                existing.add(code)
        targets = [t for t in targets if t['code'] not in existing]
        print(f'REDO mode: {len(targets)} subconcepts need generation')

    if not targets:
        print('Nothing to generate. Done.')
        return

    with open(MMD_PATH, 'r', encoding='utf-8') as f:
        mmd = f.read()

    client = genai.Client(api_key=api_key)

    print(f'\nCreating cache for {MODEL} / {THINKING}...')
    cache = client.caches.create(
        model=MODEL,
        config=types.CreateCachedContentConfig(
            system_instruction=SYSTEM_PROMPT,
            contents=[types.Content(role='user', parts=[types.Part.from_text(text=mmd)])],
            ttl=f'{3600}s',
        ),
    )
    print(f'Cache: {cache.name}\n')

    grand_tokens = {'input': 0, 'output': 0, 'cached': 0, 'thinking': 0, 'elapsed_s': 0.0}
    success_count = 0
    fail_count = 0
    results_summary = []

    for i, sub in enumerate(targets, 1):
        print(f"\n{'='*70}")
        print(f"[{i}/{len(targets)}] {sub['code']}: {sub['name']}")
        print(f"  Parent: {sub['parent_concept']} | Tier: {sub['tier']} | Lines {sub['line_start']}-{sub['line_end']}")
        print(f"  Connecting: {sub['is_connecting_topic']} | Formulas: {sub['formulas']} | Figures: {sub['figures']}")

        try:
            result, tokens = call_model(client, cache, sub)
        except Exception as e:
            print(f'  ERROR: {str(e)[:200]}')
            fail_count += 1
            results_summary.append({'code': sub['code'], 'status': 'error', 'error': str(e)[:200]})
            continue

        for k in ('input', 'output', 'cached', 'thinking', 'elapsed_s'):
            grand_tokens[k] += tokens[k]

        cost_usd, cost_inr_val = cost_inr(tokens)
        print(f"  Tokens: input={tokens['input']:,} (cached={tokens['cached']:,}) + output={tokens['output']:,} + thinking={tokens['thinking']:,}")
        print(f"  Time: {tokens['elapsed_s']:.1f}s | Cost: Rs {cost_inr_val:.3f}")

        # Validate
        issues = validate_theory(result, sub)
        if issues:
            print(f"  VALIDATION ISSUES: {issues}")

        # Save
        out_path = os.path.join(OUT_DIR, f"{sub['code']}.json")
        result['_meta'] = {
            'tier': sub['tier'],
            'parent_concept': sub['parent_concept'],
            'is_connecting_topic': sub['is_connecting_topic'],
            'source_lines': f"{sub['line_start']}-{sub['line_end']}",
            'tokens': tokens,
            'cost_inr': round(cost_inr_val, 4),
            'validation_issues': issues,
        }
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        if 'error' not in result:
            success_count += 1
            results_summary.append({'code': sub['code'], 'status': 'success', 'issues': issues, 'cost_inr': round(cost_inr_val, 4)})
            # Print preview
            theory = result.get('theory', '')
            print(f"  Theory preview ({len(theory)} chars):")
            print(f"    {theory[:200].replace(chr(10), ' ')}...")
        else:
            fail_count += 1
            results_summary.append({'code': sub['code'], 'status': 'fail', 'error': result.get('error')})

    grand_cost_usd, grand_cost_inr = cost_inr(grand_tokens)

    summary = {
        'mode': mode,
        'targets_processed': len(targets),
        'success': success_count,
        'failed': fail_count,
        'total_tokens': grand_tokens,
        'total_cost_usd': round(grand_cost_usd, 6),
        'total_cost_inr': round(grand_cost_inr, 4),
        'cost_per_subconcept_inr': round(grand_cost_inr / max(len(targets), 1), 4),
        'results': results_summary,
    }
    summary_path = os.path.join(OUT_DIR, '_summary.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*70}")
    print(f"FINAL SUMMARY (mode={mode})")
    print(f"{'='*70}")
    print(f"Success: {success_count} / Failed: {fail_count}")
    print(f"Tokens: {grand_tokens['input']:,} in (cached={grand_tokens['cached']:,}), {grand_tokens['output']:,} out, {grand_tokens['thinking']:,} thinking")
    print(f"Total cost: Rs {grand_cost_inr:.3f} (${grand_cost_usd:.5f})")
    print(f"Per subconcept: Rs {grand_cost_inr / max(len(targets), 1):.4f}")
    print(f"\nSummary: {summary_path}")
    print(f"Outputs: {OUT_DIR}/COMP_*.json")


if __name__ == '__main__':
    main()
