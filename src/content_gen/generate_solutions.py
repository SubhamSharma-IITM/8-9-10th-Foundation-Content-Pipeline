"""
Solution Generation Pass — Generate solutions for existing NCERT questions.

Back exercises + in-text questions have questions + answers but NO worked solutions.
This pass generates solutions using Gemini 3.1 Pro HIGH with cached chapter MMD.

Runs AFTER content generation is complete.
"""

import json, os, sys, time, re
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from google import genai
from google.genai import types
from post_process import post_process_content

BASE = os.path.join(os.path.dirname(__file__), '..', '..')
MODEL = 'gemini-3.1-pro-preview'
THINKING = 'HIGH'

SOLUTION_SYSTEM_PROMPT = r"""You are an expert CBSE Class 10 Science teacher writing solutions for exam questions.

## YOUR TASK
For each question provided, generate a clear, complete solution that a student can study from.
The correct answer is already given — your job is to explain WHY it is correct and HOW to arrive at it.

## MATHEMATICAL NOTATION
- Inline math: \(...\)
- Display math: \[...\]
- NEVER use $...$ delimiters

## FORMATTING
- **Bold** key terms
- Numbered steps for worked solutions
- Keep language simple and teacher-like

## SOLUTION RULES BY QUESTION TYPE

### For SCQ (Single Choice Questions):
1. State why the correct option is right (1-2 sentences with reasoning)
2. Explain why one key distractor is wrong (address the common misconception)
3. Keep concise — 3-5 sentences total

### For Subjective-Numerical:
1. **Given:** List all values with proper NCERT sign convention
2. **Formula:** State which formula applies
3. **Substitution:** Show the calculation step-by-step
4. **Answer:** Final value with units
5. **Interpretation:** What does the sign/magnitude tell us?

### For Subjective-Descriptive:
1. Answer the question directly in the first sentence
2. Provide reasoning grounded in the chapter content
3. If a diagram would help, describe it in the visual_content field
4. 3-6 sentences, teacher-like explanation

## IMAGE HANDLING
If the solution benefits from a diagram (e.g., ray diagram), set:
visual_content.needed = true, image_generation_needed = true, generation_description = "detailed specs"
Reference existing images by their code (IMG_XX) if relevant.

## OUTPUT FORMAT (strict JSON)
{
  "solutions": [
    {
      "question_id": "BACK_Q1",
      "answer": "concise short answer or numerical value with units (e.g., '-37.5 cm' or 'Concave mirror')",
      "answer_format": "descriptive|numerical|diagram",
      "solution": "full explanation text with \\(...\\) math",
      "visual_content": {
        "needed": false,
        "source_image_ref": null,
        "image_generation_needed": false,
        "generation_description": null
      }
    }
  ]
}

IMPORTANT:
- "answer" = the SHORT answer a student would write (1-2 sentences or a value with units)
- "answer_format" = classify as "descriptive" (text answer), "numerical" (calculated value), or "diagram" (requires drawing)
- "solution" = the FULL worked explanation showing how to arrive at the answer
"""


def build_solution_prompt(subconcept_id, subconcept_name, line_start, line_end, questions, image_codes=None):
    """Build prompt for generating solutions for a batch of questions."""
    prompt = f"""## GENERATE SOLUTIONS FOR SUBCONCEPT {subconcept_id}

Subconcept: {subconcept_name}
Source content: Lines {line_start}-{line_end} of the chapter.
Read these lines to understand the concepts before writing solutions.

### QUESTIONS NEEDING SOLUTIONS:

"""
    for q in questions:
        qid = q['id']
        qtype = q.get('type', 'subjective')
        answer = q.get('answer', 'Not provided')
        qtext = q.get('question_text', '')
        opts = q.get('options', {})

        prompt += f"--- {qid} [type: {qtype}] ---\n"
        prompt += f"Question: {qtext}\n"
        if opts:
            for letter, text in opts.items():
                prompt += f"  ({letter}) {text}\n"
        prompt += f"Correct Answer: {answer}\n\n"

    if image_codes:
        prompt += "### AVAILABLE IMAGES:\n"
        for img in image_codes:
            prompt += f"  {img['code']} — {img.get('caption','')}\n"

    prompt += "\nGenerate a solution for EACH question above. Follow the rules for each question type.\n"
    return prompt


def main():
    api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        print("ERROR: Set GEMINI_API_KEY")
        sys.exit(1)

    # Load data
    with open(os.path.join(BASE, 'experiments/01_ocr_benchmarks/mathpix/ch09_light/ch09_mathpix.mmd'), 'r', encoding='utf-8') as f:
        mmd = f.read()
    with open(os.path.join(BASE, 'experiments/03_topology_generation/ch09_line_ranges.json'), 'r') as f:
        lr = json.load(f)
    with open(os.path.join(BASE, 'experiments/03_topology_generation/ch09_unified_mapping.json'), 'r') as f:
        unified = json.load(f)
    with open(os.path.join(BASE, 'experiments/03_topology_generation/ch09_image_codes.json'), 'r') as f:
        img_codes = json.load(f)

    client = genai.Client(api_key=api_key)

    # Create cache
    print(f"Creating cache for solution generation...")
    cache = client.caches.create(
        model=MODEL,
        config=types.CreateCachedContentConfig(
            system_instruction=SOLUTION_SYSTEM_PROMPT,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=mmd)])],
            ttl=f"{3600}s",
        ),
    )
    print(f"Cache: {cache.name}\n")

    # Collect questions needing solutions, grouped by subconcept
    questions_by_sub = {}
    for sid, data in unified.items():
        questions = []
        for q in data.get('back_exercises', []) + data.get('intext_questions', []):
            # Check if solution is missing
            if not q.get('solution') or q.get('solution') == '':
                questions.append(q)
        if questions:
            questions_by_sub[sid] = questions

    total_questions = sum(len(qs) for qs in questions_by_sub.values())
    print(f"Questions needing solutions: {total_questions} across {len(questions_by_sub)} subconcepts\n")

    # Generate solutions per subconcept
    out_dir = os.path.join(BASE, 'experiments/05_content_generation/ch09_solutions')
    os.makedirs(out_dir, exist_ok=True)

    total_cost = 0
    total_solved = 0
    all_solutions = {}

    for sid, questions in questions_by_sub.items():
        sub_data = lr[sid]
        name = sub_data['name']

        # Image codes for this subconcept
        sub_images = [
            {'code': code, 'caption': info.get('caption', info.get('derived_caption', ''))}
            for code, info in img_codes.items() if info['subconcept_id'] == sid
        ]

        prompt = build_solution_prompt(
            sid, name, sub_data['line_start'], sub_data['line_end'],
            questions, sub_images
        )

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.3,
            max_output_tokens=16000,
            thinking_config=types.ThinkingConfig(thinking_level=THINKING),
            cached_content=cache.name,
        )

        print(f"{sid}: {name} — {len(questions)} questions...")
        start = time.time()

        try:
            resp = client.models.generate_content(
                model=MODEL, contents=prompt, config=config,
            )
        except Exception as e:
            print(f"  ERROR: {str(e)[:100]}")
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
        total_cost += cost

        print(f"  Tokens: out={tokens['output']}, think={tokens['thinking']} | Rs {cost * 85:.2f} | {elapsed:.1f}s")

        # Parse
        raw = ''
        for part in resp.candidates[0].content.parts:
            if hasattr(part, 'thought') and part.thought:
                continue
            if hasattr(part, 'text') and part.text:
                raw += part.text

        try:
            result = json.loads(raw.strip())
        except json.JSONDecodeError:
            brace = re.search(r'\{.*', raw, re.DOTALL)
            if brace:
                js = brace.group()
                while js.count('{') > js.count('}'):
                    js += '}'
                while js.count('[') > js.count(']'):
                    js += ']'
                try:
                    result = json.loads(js)
                except:
                    result = {'error': 'parse_failed'}
            else:
                result = {'error': 'no_json'}

        solutions = result.get('solutions', [])
        total_solved += len(solutions)
        all_solutions[sid] = solutions

        for sol in solutions:
            print(f"  {sol.get('question_id', '?')}: {len(sol.get('solution', ''))} chars")

        # Save per-subconcept
        with open(os.path.join(out_dir, f'{sid}_solutions.json'), 'w', encoding='utf-8') as f:
            json.dump({'solutions': solutions, 'cost': {'tokens': tokens, 'cost_usd': cost, 'cost_inr': cost * 85}}, f, indent=2, ensure_ascii=False)

    # Delete cache
    try:
        client.caches.delete(name=cache.name)
        print(f"\nCache deleted: {cache.name}")
    except:
        pass

    # Save combined
    with open(os.path.join(out_dir, 'all_solutions.json'), 'w', encoding='utf-8') as f:
        json.dump(all_solutions, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 80}")
    print(f"SOLUTION GENERATION COMPLETE")
    print(f"  Questions solved: {total_solved}/{total_questions}")
    print(f"  Total cost: ${total_cost:.4f} | Rs {total_cost * 85:.2f}")
    print(f"  Results: {out_dir}/")


if __name__ == '__main__':
    main()
