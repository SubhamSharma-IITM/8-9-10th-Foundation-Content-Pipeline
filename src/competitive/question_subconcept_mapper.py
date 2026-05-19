"""
Step 10: Competitive Question -> Competitive Subconcept Mapping.

Forked from src/topology/exercise_mapper.py (NCERT pattern):
  - Explicit client.caches.create() for MMD reuse
  - MEDIUM thinking for content verification
  - JSON truncation recovery
  - Token usage tracking

Differences for competitive:
  - Targets COMP_C{x}.S{y} subconcepts (not NCERT)
  - Adds master_schema_category (overlap/competitive_only) by lookup
  - Class 10 Science difficulty definitions (NOT JEE/NEET)
  - Difficulty must respect exercise tier biases but is per-question
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
OUT_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_questions_mapped.json')

MODEL = 'gemini-3-flash-preview'
THINKING_LEVEL = 'LOW'  # MEDIUM caused output truncation on batch tasks (thinking ate budget)
PRICING = {'input_uncached': 0.50, 'input_cached': 0.25, 'output': 3.00}
INR_PER_USD = 85

api_key = os.environ.get('GEMINI_API_KEY', '')
if not api_key:
    print('ERROR: Set GEMINI_API_KEY')
    sys.exit(1)


SYSTEM_PROMPT = """You are an experienced CBSE Class 10 Science teacher mapping coaching exercise questions to their teaching subconcept and tagging difficulty.

You have access to the FULL CHAPTER TEXT (cached). The chapter is from a competitive coaching foundation book.

# YOUR TASK FOR EACH QUESTION:
1. MAP — assign exactly ONE COMP_C{x}.S{y} subconcept code that the question tests
2. TAG difficulty — Easy, Medium, or Hard from a Class 10 Science student's perspective

# MAPPING RULES:
- Each question maps to EXACTLY ONE competitive subconcept (no splits)
- Match on physics CONTENT, not just keyword overlap
- A question may use vocabulary from one topic but actually test another — judge by what concept the student must apply to solve it
- Verify by reading the actual chapter text at the subconcept's line range when uncertain

# DIFFICULTY DEFINITIONS (Class 10 CBSE Science — NOT JEE/NEET)

A Class 10 student studying NCERT Science + this coaching foundation book has just mastered:
- Reflection and Refraction basics, mirror/lens formulae, sign convention, magnification
- Has familiarity with simple algebraic manipulation, no calculus

## EASY (only if it meets ALL of these)
- One-look-and-answer recall: definition, naming, fact recognition
- True/False on a textbook line, Fill-in-blank with single word
- Identification by image type/sign with NO calculation
- A formula stated directly (e.g., "what is f = R/2 also called?") — NO substitution
- Student answers in under 30 seconds without writing anything down

## MEDIUM (default for most coaching questions)
- ANY question requiring formula substitution, even if single-step (e.g., "f = R/2, R = 20cm, find f")
- Distractor MCQs where 2+ options look plausible and student must reason to eliminate
- Sign convention application (e.g., "object at u = -10 cm, focal length f = -15 cm, find v")
- Standard mirror/lens word problems with given values
- Compare two scenarios (concave vs convex, real vs virtual)
- Assertion-Reason where both statements come from textbook
- "Which of these is incorrect?" / "Find the wrong statement" types
- Student needs 1-3 minutes with pen and paper

## HARD
- Non-standard scenario requiring concept transfer (multiple reflections, two mirrors at angle, image of image)
- Multi-concept synthesis (mirror + lens + refraction together)
- Algebra-heavy derivation (Newton's formula application, lens combination Power addition with derivation)
- Trick distractors where common student misconception leads to wrong answer
- Long Answer questions requiring full derivation + diagram + numerical
- HOTS questions explicitly labeled, NTSE/KVPY/JSTSE tagged questions
- Connecting topics (TIR, Critical Angle, Lens Maker Formula, Combination of Lenses with derivation, Silvering, Interference/Diffraction/Polarisation)
- Student needs 4+ minutes or skips on first attempt and returns later

# CRITICAL CALIBRATION RULES

1. **Default bias = Medium**, not Easy. Most coaching questions are Medium because they require at least one substitution or reasoning step.

2. **Mark Easy ONLY for pure recall.** If the question requires ANY calculation, formula substitution, or distractor reasoning, it is Medium minimum.

3. **Use exercise tier as prior, not absolute:**
   - Tier 1 (Master Boards) → expect ~30% Easy, ~60% Medium, ~10% Hard
   - Tier 2 (NCERT Textbook + Exemplar) → expect ~25% Easy, ~65% Medium, ~10% Hard
   - Tier 3 (Foundation Builder) → expect ~10% Easy, ~60% Medium, ~30% Hard
   - Tier 4 (Foundation Builder+) → expect ~5% Easy, ~45% Medium, ~50% Hard
   - NTSE/KVPY/JSTSE tagged questions → strongly skew Hard regardless of tier

4. If a question is from Tier 3 or Tier 4 and you are tempted to label Easy, recheck — coaching builders rarely include trivial questions in advanced tiers. Most likely it is Medium.

5. ANY question involving Connecting Topics (TIR, Critical Angle, Lens Maker, Combination, Silvering, Interference, Diffraction, Polarisation, Refraction at Spherical Surfaces) is Medium minimum, often Hard.

# OUTPUT FORMAT (strict JSON, no markdown):
{
  "mappings": [
    {"q": 0, "code": "COMP_C5.S1", "diff": "Easy"},
    {"q": 1, "code": "COMP_C7.S1", "diff": "Medium"}
  ]
}

OUTPUT RULES:
- "q" = question index from input (integer)
- "code" = competitive subconcept code (e.g., COMP_C5.S1) — MUST exist in the subconcept list provided
- "diff" = exactly one of "Easy", "Medium", "Hard"
- DO NOT include subconcept name, reasoning, parent concept, or any other text fields
- One entry per input question, in any order

# CODE FORMAT — STRICT
Valid codes follow this EXACT format: COMP_C<n>.S<n>
- Uppercase only: COMP, C, S
- Underscore between COMP and C: COMP_C
- Dot between concept and S: C5.S1
- No spaces, no hyphens, no extra punctuation

VALID examples: COMP_C5.S1, COMP_C17.S1, COMP_C29.S4
INVALID (DO NOT produce): comp_c5.s1, COMP-C5-S1, COMP_C5_S1, C5.S1, COMP_C5, COMP.C5.S1

CRITICAL: Use ONLY codes from the COMP subconcept list provided. Do not invent codes.
If you are uncertain which subconcept a question belongs to, pick the closest one based on physics content."""


def load_inputs():
    with open(MMD_PATH, 'r', encoding='utf-8') as f:
        mmd = f.read()
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
        ncert_mapping = json.load(f)
    with open(QUESTIONS_PATH, 'r', encoding='utf-8') as f:
        questions = json.load(f)['cleaned']
    return mmd, schema, ncert_mapping, questions


def build_subconcept_block(schema):
    """Build the candidate subconcept list for the prompt."""
    lines = []
    for c in schema['concepts']:
        for s in c['subconcepts']:
            tag = ' [CONNECTING]' if s.get('is_connecting_topic') else ''
            lines.append(f"  {s['id']}{tag} | Parent: {c['name']} | Sub: {s['name']} | Lines {s['line_start']}-{s['line_end']}")
    return '\n'.join(lines)


def build_question_block(questions_batch, start_idx):
    """Build the question payload for one batch.
    For passage entries, send the stem + concatenated sub-question hints as ONE q.
    The passage gets a single subconcept code (same for all its sub-questions).
    """
    lines = []
    for offset, q in enumerate(questions_batch):
        idx = start_idx + offset
        if q.get('type') == 'passage':
            stem = (q.get('passage_text', '') or '')[:300]
            sub_hints = ' | '.join(
                (sq.get('question_text', '') or '')[:80]
                for sq in q.get('sub_questions', [])[:3]
            )
            lines.append(f"\nQ{idx} | tier={q.get('exercise_tier')} | type=passage | stem: {stem}")
            lines.append(f"   sub-questions hint: {sub_hints[:300]}")
        else:
            qtext = (q.get('question_text', '') or '')[:300]
            ft = q.get('foundation_type')
            ft_str = f" [{ft}]" if ft else ''
            lines.append(f"\nQ{idx} | tier={q.get('exercise_tier')}{ft_str} | type={q.get('type')}/{q.get('scq_format') or q.get('answer_format')} | text: {qtext}")
    return '\n'.join(lines)


class CompMapper:
    def __init__(self):
        self.client = genai.Client(api_key=api_key)
        self._cache = None
        self.total_tokens = {'input': 0, 'output': 0, 'cached': 0, 'thinking': 0, 'time_s': 0.0, 'calls': 0}

    def _ensure_cache(self, system_prompt: str, mmd: str):
        if self._cache is not None:
            return
        try:
            self._cache = self.client.caches.create(
                model=MODEL,
                config=types.CreateCachedContentConfig(
                    system_instruction=system_prompt,
                    contents=[types.Content(role='user', parts=[types.Part.from_text(text=mmd)])],
                    ttl=f'{3600}s',
                ),
            )
            print(f'  Cache created: {self._cache.name}')
        except Exception as e:
            print(f'  Cache failed (continuing without cache): {e}')
            self._cache = None

    def call(self, system_prompt: str, user_prompt: str, mmd: str = None):
        if mmd:
            self._ensure_cache(system_prompt, mmd)

        config = types.GenerateContentConfig(
            response_mime_type='application/json',
            temperature=0.2,
            max_output_tokens=32000,
            thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL),
        )
        if self._cache:
            config.cached_content = self._cache.name
        else:
            config.system_instruction = system_prompt

        t0 = time.time()
        response = self.client.models.generate_content(
            model=MODEL,
            contents=user_prompt,
            config=config,
        )
        elapsed = time.time() - t0

        # Token usage
        um = response.usage_metadata
        tokens = {
            'input': getattr(um, 'prompt_token_count', 0) or 0,
            'output': getattr(um, 'candidates_token_count', 0) or 0,
            'cached': getattr(um, 'cached_content_token_count', 0) or 0,
            'thinking': getattr(um, 'thoughts_token_count', 0) or 0,
        }
        for k in ('input', 'output', 'cached', 'thinking'):
            self.total_tokens[k] += tokens[k]
        self.total_tokens['time_s'] += elapsed
        self.total_tokens['calls'] += 1
        print(f'  Tokens: input={tokens["input"]:,} (cached={tokens["cached"]:,}) + output={tokens["output"]:,} + thinking={tokens["thinking"]:,} | {elapsed:.1f}s')

        # Extract text (skip thinking parts)
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
        except json.JSONDecodeError:
            # Truncation recovery
            result = None
            brace = re.search(r'\{.*', text, re.DOTALL)
            if brace:
                json_str = brace.group()
                last = json_str.rfind('}')
                if last > 0:
                    truncated = json_str[:last+1]
                    if truncated.count('[') > truncated.count(']'):
                        truncated += ']'
                    if truncated.count('{') > truncated.count('}'):
                        truncated += '}'
                    try:
                        result = json.loads(truncated)
                    except json.JSONDecodeError:
                        pass
            if result is None:
                return {'error': 'json_parse_failed', 'raw': text[:500]}

        if isinstance(result, list):
            result = {'mappings': result}
        return result


def normalize_code(raw_code: str, valid_codes: set) -> tuple:
    """Normalize a possibly-mangled code into our canonical COMP_C<n>.S<n> form.

    Returns (normalized_code, status) where status is one of:
      - 'exact'      → already valid
      - 'normalized' → cleaned successfully and matches a valid code
      - 'invalid'    → cannot be salvaged → put in redo bucket
    """
    if not raw_code:
        return None, 'invalid'
    s = str(raw_code).strip()

    # 1. Already exact
    if s in valid_codes:
        return s, 'exact'

    # 2. Try simple uppercasing
    upper = s.upper()
    if upper in valid_codes:
        return upper, 'normalized'

    # 3. Replace common separator mistakes: hyphens, double-dots, underscores in wrong places
    cleaned = upper.replace('-', '_').replace('..', '.').replace(' ', '')
    if cleaned in valid_codes:
        return cleaned, 'normalized'

    # 4. Try regex: extract digits and rebuild canonical form
    m = re.search(r'C\s*(\d+)[._\s]+S\s*(\d+)', upper)
    if m:
        rebuilt = f'COMP_C{m.group(1)}.S{m.group(2)}'
        if rebuilt in valid_codes:
            return rebuilt, 'normalized'

    # 5. Try if model dropped COMP_ prefix
    if upper.startswith('C') and not upper.startswith('COMP'):
        rebuilt = f'COMP_{upper}'
        if rebuilt in valid_codes:
            return rebuilt, 'normalized'

    return s, 'invalid'


def cost_inr(tokens):
    uncached = tokens['input'] - tokens['cached']
    cost_usd = (
        (uncached / 1e6) * PRICING['input_uncached'] +
        (tokens['cached'] / 1e6) * PRICING['input_cached'] +
        ((tokens['output'] + tokens['thinking']) / 1e6) * PRICING['output']
    )
    return cost_usd, cost_usd * INR_PER_USD


def main(sample_size=None, tier_filter=None):
    mmd, schema, ncert_mapping, questions = load_inputs()
    print(f'Loaded: {len(questions)} cleaned questions')

    # Build category lookup: COMP code -> overlap or competitive_only
    cat_lookup = {}
    for m in ncert_mapping['mappings']:
        cat_lookup[m['comp_code']] = m['category']

    # Tier filter for targeted dry run
    if tier_filter:
        questions = [q for q in questions if q.get('exercise_tier') in tier_filter]
        print(f'TIER FILTER: only tiers {tier_filter} → {len(questions)} questions')

    # Sample size for dry run
    if sample_size:
        questions = questions[:sample_size]
        print(f'DRY RUN: limited to first {sample_size} questions')

    subconcept_block = build_subconcept_block(schema)
    mapper = CompMapper()

    # Build user prompt
    question_block = build_question_block(questions, start_idx=0)
    user_prompt = f"""# COMPETITIVE SUBCONCEPTS (use ONLY these codes — {len(schema['concepts'])} concepts, {sum(len(c['subconcepts']) for c in schema['concepts'])} subconcepts):

{subconcept_block}

# QUESTIONS TO MAP ({len(questions)} questions):
{question_block}

Map each question to its competitive subconcept code and tag difficulty per the rubric in the system prompt."""

    print(f'\nPrompt size: {len(user_prompt):,} chars (~{len(user_prompt)//4:,} tokens)')
    print('Calling LLM...')

    result = mapper.call(SYSTEM_PROMPT, user_prompt, mmd=mmd)

    if 'error' in result:
        print(f'ERROR: {result["error"]}')
        print(result.get('raw', '')[:500])
        return

    mappings = result.get('mappings', [])
    print(f'\nGot {len(mappings)} mappings (expected {len(questions)})')

    # Build lookup tables from schema (code -> name + parent)
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

    # Validation/normalization pass
    enriched = []
    redo_bucket = []  # invalid codes that need re-mapping
    normalization_log = []  # codes that were salvaged via normalization
    seen_q = set()
    duplicate_q = []
    difficulty_dist = {'Easy': 0, 'Medium': 0, 'Hard': 0, 'other': 0}

    for m in mappings:
        raw_code = m.get('code') or m.get('comp_code')
        q_idx = m.get('q') if 'q' in m else m.get('q_index')
        diff = m.get('diff') or m.get('difficulty', 'Medium')

        # Track duplicates
        if q_idx in seen_q:
            duplicate_q.append(q_idx)
            continue
        seen_q.add(q_idx)

        # Normalize code
        norm_code, status = normalize_code(raw_code, valid_codes)

        if status == 'invalid':
            redo_bucket.append({
                'q_index': q_idx,
                'raw_code_from_llm': raw_code,
                'reason': 'code not in schema and not salvageable',
            })
            continue

        if status == 'normalized':
            normalization_log.append({
                'q_index': q_idx,
                'raw': raw_code,
                'normalized_to': norm_code,
            })

        # Validate difficulty
        if diff not in ('Easy', 'Medium', 'Hard'):
            diff = 'Medium'  # default
        difficulty_dist[diff] += 1

        info = code_lookup[norm_code]
        cat = cat_lookup.get(norm_code, 'unknown')
        enriched.append({
            'q_index': q_idx,
            'comp_code': norm_code,
            'comp_name': info['name'],
            'comp_parent_concept': info['parent_concept'],
            'comp_parent_code': info['parent_code'],
            'is_connecting_topic': info['is_connecting_topic'],
            'master_schema_category': cat,
            'difficulty': diff,
        })

    # Find missing questions (LLM didn't return them)
    expected_indices = set(range(len(questions)))
    returned_indices = {m['q_index'] for m in enriched}
    missing_q = sorted(expected_indices - returned_indices)
    for q_idx in missing_q:
        redo_bucket.append({
            'q_index': q_idx,
            'raw_code_from_llm': None,
            'reason': 'LLM did not return mapping for this question',
        })

    # Cost
    cost_usd, cost_inr_val = cost_inr(mapper.total_tokens)

    # Save
    output = {
        'mappings': enriched,
        'redo_bucket': redo_bucket,
        'normalization_log': normalization_log,
        'duplicate_q_indices': duplicate_q,
        'stats': {
            'total_input_questions': len(questions),
            'mapped_clean': len(enriched),
            'normalized_count': len(normalization_log),
            'redo_count': len(redo_bucket),
            'duplicate_count': len(duplicate_q),
            'difficulty_distribution': difficulty_dist,
            'cost_usd': round(cost_usd, 6),
            'cost_inr': round(cost_inr_val, 4),
            'tokens': mapper.total_tokens,
        }
    }
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f'\n=== RESULTS ===')
    print(f'Mapped clean: {len(enriched)}/{len(questions)}')
    print(f'Normalized:   {len(normalization_log)} (codes salvaged via cleanup)')
    print(f'Redo bucket:  {len(redo_bucket)} (need re-mapping)')
    print(f'Duplicates:   {len(duplicate_q)}')
    print(f'Difficulty:   {difficulty_dist}')
    print(f'Cost: Rs {cost_inr_val:.3f}')
    print(f'\nSaved: {OUT_PATH}')

    if normalization_log:
        print(f'\nNormalization examples:')
        for n in normalization_log[:5]:
            print(f'  Q{n["q_index"]}: "{n["raw"]}" → {n["normalized_to"]}')

    if redo_bucket:
        print(f'\nRedo bucket samples:')
        for r in redo_bucket[:5]:
            print(f'  Q{r["q_index"]}: {r["reason"]} (raw: {r.get("raw_code_from_llm")})')

    # Sample 8 mappings for review (text lookup in our code, NOT from LLM)
    print(f'\n=== SAMPLE MAPPINGS ===')
    for m in enriched[:8]:
        q_idx = m['q_index']
        if q_idx is not None and q_idx < len(questions):
            q = questions[q_idx]
            qtext = (q.get('question_text', '') or '')[:80]
            print(f'\nQ{q_idx} (tier {q.get("exercise_tier")}): {qtext}')
            print(f'  -> {m["comp_code"]}: {m["comp_name"]}')
            print(f'     [{m["difficulty"]}] [{m["master_schema_category"]}]')


if __name__ == '__main__':
    sample = int(sys.argv[1]) if len(sys.argv) > 1 else None
    tier = None
    if len(sys.argv) > 2:
        tier = [int(t) for t in sys.argv[2].split(',')]
    main(sample_size=sample, tier_filter=tier)
