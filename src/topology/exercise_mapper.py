"""
Exercise → Subconcept Mapper + Difficulty Tagger + Question Type Validator

Two approaches tested:
  A: Schema-only (subconcept names + questions)
  B: Schema + line ranges + cached MMD (model verifies by reading actual content)

Uses Gemini with MEDIUM thinking budget + content caching (Stage 2 pattern).
"""

import json
import os
import re
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

MODEL = "gemini-3-flash-preview"
THINKING_LEVEL = "MEDIUM"  # String enum, not integer — matches PROOF-READING-V5.0 pattern


class ExerciseMapper:
    """Maps exercises to subconcepts using cached chapter MMD."""

    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self._cache_handle = None

    def _ensure_cache(self, system_prompt: str, chapter_mmd: str):
        """Cache system prompt + chapter MMD (Stage 2 pattern)."""
        if self._cache_handle is not None:
            return

        try:
            self._cache_handle = self.client.caches.create(
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
            print(f"  Cache created: {self._cache_handle.name}")
        except Exception as e:
            print(f"  Cache creation failed: {e}")
            self._cache_handle = None

    def _call_gemini_once(self, client, system_prompt, user_prompt, chapter_mmd):
        """Single Gemini attempt - returns (raw_text, tokens) or raises."""
        # Note: caching is AI Studio specific; on Vertex AI we send inline
        if chapter_mmd and client is self.client:
            self._ensure_cache(system_prompt, chapter_mmd)

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
            max_output_tokens=16000,
            thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL),
        )
        if client is self.client and self._cache_handle:
            config.cached_content = self._cache_handle.name
            contents = user_prompt
        elif chapter_mmd:
            # Vertex AI path: no cache, inline the MMD context
            config.system_instruction = system_prompt
            contents = f"DOCUMENT (chapter MMD for context):\n{chapter_mmd}\n\n{user_prompt}"
        else:
            config.system_instruction = system_prompt
            contents = user_prompt

        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=config,
        )
        raw_text = ""
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'thought') and part.thought:
                continue
            if hasattr(part, 'text') and part.text:
                raw_text += part.text
        um = response.usage_metadata
        tokens = {
            "input": getattr(um, 'prompt_token_count', 0) or 0,
            "output": getattr(um, 'candidates_token_count', 0) or 0,
            "cached": getattr(um, 'cached_content_token_count', 0) or 0,
            "thinking": getattr(um, 'thoughts_token_count', 0) or 0,
        }
        return raw_text, tokens

    def call(self, system_prompt: str, user_prompt: str, chapter_mmd: str = None) -> dict:
        """Provider cascade: AI Studio Gemini -> Vertex AI Gemini -> Anthropic Claude.
        Mirrors QA App Stage 2 / Stage 9 dual-path dispatch."""
        raw_text = ""
        tokens = {"input": 0, "output": 0, "cached": 0, "thinking": 0}
        provider_used = "gemini_aistudio"

        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from src.common.llm_client import is_permission_error, make_gemini_client, make_anthropic_client

        # ── Try 1: AI Studio Gemini ──
        try:
            raw_text, tokens = self._call_gemini_once(self.client, system_prompt, user_prompt, chapter_mmd)
        except Exception as e1:
            if not is_permission_error(e1):
                raise
            print(f"  AI Studio Gemini denied -> falling back to Vertex AI Gemini...")
            # ── Try 2: Vertex AI Gemini (same model, paid quota) ──
            try:
                vertex_client = make_gemini_client(prefer_vertex=True)
                provider_used = "gemini_vertex"
                raw_text, tokens = self._call_gemini_once(vertex_client, system_prompt, user_prompt, chapter_mmd)
            except Exception as e2:
                if not is_permission_error(e2) and "404" not in str(e2) and "not found" not in str(e2).lower():
                    raise
                print(f"  Vertex AI failed -> falling back to Anthropic Claude...")
                # ── Try 3: Anthropic Claude ──
                provider_used = "anthropic"
                anthropic_client = make_anthropic_client()
                msg_content = []
                if chapter_mmd:
                    msg_content.append({
                        "type": "text",
                        "text": f"DOCUMENT (chapter MMD for context):\n{chapter_mmd}",
                        "cache_control": {"type": "ephemeral"},
                    })
                msg_content.append({"type": "text", "text": user_prompt})
                response = anthropic_client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=8192,
                    system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": msg_content}],
                    timeout=120,
                )
                raw_text = response.content[0].text
                usage = response.usage
                tokens = {
                    "input": getattr(usage, 'input_tokens', 0) or 0,
                    "output": getattr(usage, 'output_tokens', 0) or 0,
                    "cached": getattr(usage, 'cache_read_input_tokens', 0) or 0,
                    "thinking": 0,
                }

        print(f"  [{provider_used}] Tokens: input={tokens['input']}, output={tokens['output']}, cached={tokens['cached']}, thinking={tokens['thinking']}")

        # Parse JSON (with truncation recovery from Stage 2 pattern)
        text = raw_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        result = None
        # Try direct parse
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON object
        if result is None:
            brace = re.search(r'\{.*', text, re.DOTALL)
            if brace:
                json_str = brace.group()
                # Fix truncation: if mappings array isn't closed, close it
                if '"mappings"' in json_str:
                    # Find last complete mapping object
                    # Each mapping ends with }
                    last_complete = json_str.rfind('}')
                    if last_complete > 0:
                        truncated = json_str[:last_complete+1]
                        # Close the array and outer object
                        if truncated.count('[') > truncated.count(']'):
                            truncated += ']'
                        if truncated.count('{') > truncated.count('}'):
                            truncated += '}'
                        try:
                            result = json.loads(truncated)
                        except json.JSONDecodeError:
                            pass

        if result is None:
            result = {"error": "json_parse_failed", "raw": text[:500]}

        # Normalize: if result is a list, wrap it
        if isinstance(result, list):
            result = {"mappings": result}

        result["_tokens"] = tokens
        result["_provider"] = provider_used
        return result


# ═══════════════════════════════════════════════════════════════════════════
# APPROACH A: Schema-only (no MMD context)
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT_A = """You are an expert CBSE Class 10 Science teacher who precisely classifies questions.

Your tasks:
1. MAP each question to exactly ONE subconcept from the provided schema.
2. TAG each question with difficulty: Easy, Medium, or Hard.
3. VALIDATE the question type (scq/integer/subjective) — mark as "correct" or suggest the right type.

DIFFICULTY DEFINITIONS:
- Easy: Student recalls textbook content directly. Define, name, list, identify. One mental step.
- Medium: Student must USE a concept — apply formula (1-2 steps), explain why, compare. Not a direct textbook quote.
- Hard: Unfamiliar scenario, multi-step reasoning (3+), evaluate claims, cross-topic synthesis.

RULES:
- Each question maps to EXACTLY ONE subconcept. No splits.
- Use EXACT subconcept names from the schema provided.
- For difficulty, consider what cognitive operation the student must perform, not just topic complexity.
- For type validation: scq = has 4 options, integer = numerical answer expected, subjective = text answer expected."""

def build_prompt_A(schema: dict, questions: list, line_ranges: dict) -> str:
    """Approach A: Schema + subconcept descriptions only."""
    chapter = list(schema.keys())[0]
    concepts = schema[chapter]

    schema_text = f"CHAPTER: {chapter}\n\nSUBCONCEPTS:\n"
    for concept, subs in concepts.items():
        for sub in subs:
            schema_text += f"  [{concept}] > {sub}\n"

    q_text = "\nQUESTIONS TO CLASSIFY:\n"
    for q in questions:
        src = "BACK" if q.get('isBackExercise', True) else "INTEXT"
        blk = f"_B{q['block']}" if q.get('block') else ""
        qid = f"{src}{blk}_Q{q['num']}"
        qtype = q.get('type', 'unknown')
        text = q.get('text', q.get('full_text', ''))[:300]
        opts = ""
        if q.get('options'):
            opts = " | Options: " + " / ".join(f"({k}) {v[:40]}" for k, v in q['options'].items())
        q_text += f"\n{qid} [extracted_type: {qtype}]: {text}{opts}\n"

    return schema_text + q_text + """
OUTPUT (strict JSON, no markdown):
{"mappings": [{"id": "BACK_Q1", "subconcept": "exact name", "concept": "parent concept", "difficulty": "Easy|Medium|Hard", "type_validation": "correct|scq|integer|subjective", "reasoning": "1 line why"}]}"""


# ═══════════════════════════════════════════════════════════════════════════
# APPROACH B: Schema + line ranges + cached MMD (verification loop)
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT_B = """You are an expert CBSE Class 10 Science teacher who precisely classifies questions.

You have access to the FULL CHAPTER TEXT (cached). You also have LINE RANGES for each subconcept.

YOUR PROCESS (think step by step):
1. Read the question carefully.
2. Identify which subconcept it most likely belongs to from the schema.
3. VERIFY: Go to the line range for that subconcept in the chapter text. Read the actual content.
4. CONFIRM: Does the question test content from those specific lines? If yes, assign it. If not, check the next most likely subconcept's line range.
5. Only output your final assignment after verification.

ALSO:
- TAG difficulty: Easy (recall), Medium (apply/explain), Hard (multi-step/unfamiliar).
- VALIDATE question type: Is the extracted type correct? If not, suggest the right one.

DIFFICULTY DEFINITIONS:
- Easy: Recall textbook content. Define, name, list. One step.
- Medium: Apply a concept — formula (1-2 steps), explain why, compare. Textbook-like context.
- Hard: Unfamiliar scenario, 3+ step reasoning, evaluate, cross-topic.

RULES:
- Each question → EXACTLY ONE subconcept.
- Use EXACT subconcept names from the schema.
- Verify by reading the actual chapter content at the line ranges before finalizing."""

def build_prompt_B(schema: dict, questions: list, line_ranges: dict) -> str:
    """Approach B: Schema + line ranges for verification."""
    chapter = list(schema.keys())[0]
    concepts = schema[chapter]

    schema_text = f"CHAPTER: {chapter}\n\nSUBCONCEPTS WITH LINE RANGES:\n"
    for concept, subs in concepts.items():
        for sub in subs:
            # Find line range for this subconcept
            lr = None
            for sid, data in line_ranges.items():
                if data['name'] == sub:
                    lr = data
                    break
            if lr:
                schema_text += f"  [{concept}] > {sub}  (Lines {lr['line_start']}-{lr['line_end']})\n"
            else:
                schema_text += f"  [{concept}] > {sub}\n"

    q_text = "\nQUESTIONS TO CLASSIFY:\n"
    for q in questions:
        src = "BACK" if q.get('isBackExercise', True) else "INTEXT"
        blk = f"_B{q['block']}" if q.get('block') else ""
        qid = f"{src}{blk}_Q{q['num']}"
        qtype = q.get('type', 'unknown')
        text = q.get('text', q.get('full_text', ''))[:300]
        opts = ""
        if q.get('options'):
            opts = " | Options: " + " / ".join(f"({k}) {v[:40]}" for k, v in q['options'].items())
        q_text += f"\n{qid} [extracted_type: {qtype}]: {text}{opts}\n"

    return schema_text + q_text + """
REMEMBER: For each question, VERIFY by checking the line range content in the chapter before finalizing.

OUTPUT (strict JSON, no markdown):
{"mappings": [{"id": "BACK_Q1", "subconcept": "exact name", "concept": "parent concept", "difficulty": "Easy|Medium|Hard", "type_validation": "correct|scq|integer|subjective", "reasoning": "1 line why this subconcept after verifying line range content"}]}"""


def run_approach(approach: str, mapper: ExerciseMapper, schema: dict,
                 questions: list, line_ranges: dict, mmd_text: str) -> dict:
    """Run one approach and return results."""
    print(f"\n{'='*60}")
    print(f"APPROACH {approach}")
    print(f"{'='*60}")

    if approach == "A":
        system_prompt = SYSTEM_PROMPT_A
        user_prompt = build_prompt_A(schema, questions, line_ranges)
        result = mapper.call(system_prompt, user_prompt)
    else:
        system_prompt = SYSTEM_PROMPT_B
        user_prompt = build_prompt_B(schema, questions, line_ranges)
        # For B: cache the MMD as context
        mapper._cache_handle = None  # Reset cache for fresh approach
        result = mapper.call(system_prompt, user_prompt, chapter_mmd=mmd_text)

    return result


def print_results(result: dict, label: str):
    """Print mapping results."""
    mappings = result.get('mappings', [])
    print(f"\n--- {label}: {len(mappings)} mappings ---")
    for m in mappings:
        tv = m.get('type_validation', 'correct')
        tv_mark = "" if tv == "correct" else f" [TYPE: {tv}]"
        print(f"  {m['id']:<20} [{m['difficulty']:>6}] -> {m['subconcept'][:55]}{tv_mark}")
        print(f"  {'':20}   {m.get('reasoning', '')[:80]}")


# ═══════════════════════════════════════════════════════════════════════
# SOLVED EXAMPLE MAPPING (Code-based, no LLM needed)
# ═══════════════════════════════════════════════════════════════════════

def map_solved_examples(exercises: dict, line_ranges: dict) -> list:
    """
    Map solved examples to subconcepts by line range.
    Pure code — no LLM call needed. The example's line_start falls within
    a subconcept's [line_start, line_end) range.
    """
    mappings = []
    for ex in exercises.get('solved_examples', []):
        matched_sid = None
        matched_name = None
        for sid, lr_data in line_ranges.items():
            if lr_data['line_start'] <= ex['line_start'] < lr_data['line_end']:
                matched_sid = sid
                matched_name = lr_data['name']
                break

        mappings.append({
            'id': ex['id'].replace(' ', '_').upper(),  # "Example 9.1" -> "EXAMPLE_9.1"
            'subconcept_id': matched_sid or 'UNMAPPED',
            'subconcept': matched_name or 'UNMAPPED',
            'source': 'code_line_range',
            'type': 'solved_example',
            'difficulty': 'Medium',  # NCERT examples are typically medium
            'has_solution': ex.get('has_solution', True),
            'question': ex.get('question', ''),
            'line_start': ex.get('line_start'),
            'line_end': ex.get('line_end'),
            'isFromNCERT': True,
        })

    return mappings


# ═══════════════════════════════════════════════════════════════════════
# UNIFIED OUTPUT: Merge all mappings into one file
# ═══════════════════════════════════════════════════════════════════════

def build_unified_mapping(
    llm_mappings: list,
    example_mappings: list,
    line_ranges: dict,
    exercises_data: dict = None,
) -> dict:
    """
    Merge LLM-mapped questions + code-mapped examples into ONE unified output.
    Organized by subconcept ID for easy consumption by later pipeline stages.

    Output structure:
    {
        "C2.S5": {
            "subconcept_name": "Mirror Formula and Magnification",
            "back_exercises": [...],
            "intext_questions": [...],
            "solved_examples": [...],
            "total_existing": N
        },
        ...
    }
    """
    # Initialize per-subconcept buckets
    unified = {}
    for sid, data in line_ranges.items():
        unified[sid] = {
            'subconcept_name': data['name'],
            'back_exercises': [],
            'intext_questions': [],
            'solved_examples': [],
            'total_existing': 0,
        }

    # Place LLM-mapped questions (use subconcept ID matching via name)
    sid_by_name = {data['name']: sid for sid, data in line_ranges.items()}

    # Build full question lookup from exercises data
    full_questions = {}
    if exercises_data:
        for ex in exercises_data.get('back_exercises', []):
            qid = f"BACK_Q{ex['num']}"
            full_questions[qid] = {
                'text': ex.get('text', ex.get('full_text', '')),
                'options': ex.get('options', {}),
                'answer': ex.get('answer'),
            }
        for q in exercises_data.get('intext_questions', []):
            blk = f"_B{q['block']}" if q.get('block') else ''
            qid = f"INTEXT{blk}_Q{q['num']}"
            full_questions[qid] = {
                'text': q.get('text', ''),
                'options': {},
                'answer': None,
            }

    for m in llm_mappings:
        sub_name = m.get('subconcept', '')
        matched_sid = None
        for sname, sid in sid_by_name.items():
            if sub_name[:30] in sname[:30] or sname[:30] in sub_name[:30]:
                matched_sid = sid
                break

        if not matched_sid:
            continue

        # Include FULL question data — not just summary
        fq = full_questions.get(m['id'], {})
        entry = {
            'id': m['id'],
            'type': m.get('type', 'subjective'),
            'difficulty': m.get('difficulty', 'Medium'),
            'reasoning': m.get('reasoning', ''),
            'question_text': fq.get('text', ''),
            'options': fq.get('options', {}),
            'answer': fq.get('answer'),
        }

        if m['id'].startswith('BACK'):
            unified[matched_sid]['back_exercises'].append(entry)
        elif m['id'].startswith('INTEXT'):
            unified[matched_sid]['intext_questions'].append(entry)

    # Place code-mapped solved examples
    for ex in example_mappings:
        sid = ex.get('subconcept_id')
        if sid and sid in unified:
            unified[sid]['solved_examples'].append({
                'id': ex['id'],
                'source': 'code_line_range',
                'isFromNCERT': True,
                'question': ex.get('question', ''),
                'has_solution': ex.get('has_solution', True),
            })

    # Compute totals
    for sid, bucket in unified.items():
        bucket['total_existing'] = (
            len(bucket['back_exercises']) +
            len(bucket['intext_questions'])
        )
        # Solved examples counted separately (not in question total)
        bucket['total_existing_examples'] = len(bucket['solved_examples'])

    return unified


if __name__ == '__main__':
    import argparse
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(PROJECT_ROOT))
    # Importing llm_client triggers .env loading via python-dotenv BEFORE
    # we check os.environ.get('GEMINI_API_KEY', '') below.
    from src.common import chapter_config, llm_client  # noqa: F401
    from src.common.backup import safe_write_json
    from src.common.cost_gate import CostEstimate, confirm_spend, log_spend

    parser = argparse.ArgumentParser(description='Exercise/in-text question -> subconcept mapper (PAID LLM)')
    parser.add_argument('--chapter', help='Chapter key from chapter_config')
    parser.add_argument('--dry-run', action='store_true', help='Skip LLM call')
    parser.add_argument('--yes', action='store_true', help='Auto-confirm cost gate')
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    if args.chapter:
        cfg = chapter_config.load(args.chapter)
        schema_path = str(cfg.schema_path)
        exercises_path = str(cfg.exercises_path)
        line_ranges_path = str(cfg.line_ranges_path)
        mmd_path = str(cfg.mmd_path)
        mapped_path = cfg.mapped_path
        unified_path = cfg.unified_mapping_path
        chapter_key_for_log = args.chapter
    else:
        schema_path = 'experiments/03_topology_generation/ch09_schema.json'
        exercises_path = 'experiments/03_topology_generation/ch09_exercises.json'
        line_ranges_path = 'experiments/03_topology_generation/ch09_line_ranges.json'
        mmd_path = 'experiments/01_ocr_benchmarks/mathpix/ch09_light/ch09_mathpix.mmd'
        mapped_path = Path('experiments/03_topology_generation/ch09_mapped_B.json')
        unified_path = Path('experiments/03_topology_generation/ch09_unified_mapping.json')
        chapter_key_for_log = 'ch09_light_ncert_legacy'

    api_key = os.environ.get('GEMINI_API_KEY', '')

    # Load data
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    with open(exercises_path, 'r', encoding='utf-8') as f:
        exercises = json.load(f)
    with open(line_ranges_path, 'r', encoding='utf-8') as f:
        line_ranges = json.load(f)
    with open(mmd_path, 'r', encoding='utf-8') as f:
        mmd_text = f.read()

    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    # Step 1: Map solved examples by code (no LLM)
    example_mappings = map_solved_examples(exercises, line_ranges)
    print(f"=== SOLVED EXAMPLES (code-mapped) ===")
    for em in example_mappings:
        print(f"  {em['id']} -> {em['subconcept_id']}: {em['subconcept'][:50]}")

    # Step 2: Map back exercises + in-text questions via LLM (Approach B)
    all_questions = []
    for ex in exercises['back_exercises']:
        ex['isBackExercise'] = True
        all_questions.append(ex)
    for q in exercises['intext_questions']:
        q['isBackExercise'] = False
        all_questions.append(q)

    # Cost gate
    n_qs = len(all_questions)
    est = CostEstimate(
        stage='exercise_mapper_llm',
        chapter_key=chapter_key_for_log,
        item_count=n_qs,
        inr_estimate=max(2.0, round(n_qs * 0.3, 2)),  # ~Rs 0.3/question empirical
        model=MODEL,
        thinking_level=THINKING_LEVEL,
        notes=f"map {n_qs} questions to {sum(len(s) for s in list(schema.values())[0].values())} subconcepts",
    )
    proceed = confirm_spend(est, yes=args.yes, dry_run=args.dry_run)

    llm_mappings = []
    actual_inr = 0.0

    if args.dry_run:
        print("[dry-run] skipping LLM mapping. Loading existing mapped_path if present...")
        if mapped_path.exists():
            llm_result = json.loads(mapped_path.read_text(encoding='utf-8'))
            llm_mappings = llm_result.get('mappings', [])
            print(f"  Loaded {len(llm_mappings)} existing mappings.")
        else:
            print("  No existing mappings - downstream will see empty mapping list.")
    elif proceed and api_key:
        print(f"\n=== QUESTIONS (LLM-mapped, Approach B) ===")
        mapper = ExerciseMapper(api_key)
        llm_result = run_approach("B", mapper, schema, all_questions, line_ranges, mmd_text)
        llm_mappings = llm_result.get('mappings', [])

        tokens = llm_result.get('_tokens', {})
        provider = llm_result.get('_provider', 'gemini')
        uncached = tokens.get('input', 0) - tokens.get('cached', 0)
        cached = tokens.get('cached', 0)
        output_t = tokens.get('output', 0)
        thinking_t = tokens.get('thinking', 0)
        if provider == 'anthropic':
            # claude-sonnet-4-6: $3/MTok input, $15/MTok output, $0.30/MTok cache read, $3.75/MTok cache write
            cost_usd = (uncached/1e6*3.00) + (cached/1e6*0.30) + (output_t/1e6*15.00)
        else:
            # gemini-3-flash-preview: $0.50/MTok input (uncached), $0.25/MTok cached, $3/MTok output+thinking
            cost_usd = (uncached/1e6*0.50) + (cached/1e6*0.25) + ((output_t+thinking_t)/1e6*3.00)
        actual_inr = round(cost_usd * 85.0, 4)
        print(f"\n  Provider: {provider} | Cost: ${cost_usd:.6f} USD | Rs {actual_inr} INR")
        print(f"  Tokens: input={tokens.get('input',0)} (cached={cached}), output={output_t}, thinking={thinking_t}")

        safe_write_json(mapped_path, llm_result)
        log_spend(est, actual_inr=actual_inr, status='ok')
    elif proceed and not api_key:
        print("ERROR: GEMINI_API_KEY not set in environment. Cannot run LLM mapping.")
        log_spend(est, actual_inr=0.0, status='no_api_key')
        sys.exit(2)
    else:
        print("Aborted at cost gate.")
        sys.exit(1)

    # Step 3: Build unified output
    print(f"\n=== UNIFIED MAPPING ===")
    unified = build_unified_mapping(llm_mappings, example_mappings, line_ranges, exercises_data=exercises)

    print(f"\n{'ID':<8} {'SUBCONCEPT':<50} {'BACK':>4} {'INTX':>4} {'EX':>3} {'TOTAL':>5}")
    print("-" * 85)
    for sid, bucket in unified.items():
        total = bucket['total_existing']
        ex = bucket['total_existing_examples']
        print(f"{sid:<8} {bucket['subconcept_name'][:50]:<50} {len(bucket['back_exercises']):>4} {len(bucket['intext_questions']):>4} {ex:>3} {total:>5}")

    total_all = sum(b['total_existing'] for b in unified.values())
    total_ex = sum(b['total_existing_examples'] for b in unified.values())
    print(f"\nTOTAL: {total_all} questions + {total_ex} solved examples = {total_all + total_ex} items mapped")

    # Save unified output (with backup of prior version)
    safe_write_json(unified_path, unified)
    print(f"\nSaved: {unified_path}")
