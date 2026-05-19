"""
Capacity Computation Formula v2

LOCKED PARAMETERS:
- Total question cap (SCQ + Subjective combined, NOT including solved examples):
    Rich: 8, Medium: 6, Thin: 4
- Solved example cap (SEPARATE from questions):
    Rich: 3, Medium: 2, Thin: 1
- If existing questions >= cap → generate 0 for that subconcept
- Question TYPE split → decided by research classification (Task #6), NOT by this formula
- Difficulty split → decided by research classification, NOT by this formula
- This formula ONLY computes: total_to_generate = cap - existing

Input: line_ranges.json + mapped exercises + solved examples
Output: per-subconcept generation budget
"""

import json
import sys
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════
# LOCKED CAPS
# ═══════════════════════════════════════════════════════════════════════

QUESTION_CAPS = {  # SCQ + Subjective COMBINED
    'rich': 8,
    'medium': 6,
    'thin': 4,
}

EXAMPLE_CAPS = {  # Solved examples SEPARATE
    'rich': 3,
    'medium': 2,
    'thin': 1,
}


# ═══════════════════════════════════════════════════════════════════════
# TIER DETERMINATION
# ═══════════════════════════════════════════════════════════════════════

def determine_tier(density: dict) -> str:
    """Determine subconcept tier from content density."""
    lines = density.get('line_count', 0)
    figures = density.get('figures', 0)
    formulas = density.get('formulas', 0)

    if lines >= 40 or (figures >= 3 and lines >= 25) or formulas >= 10:
        return 'rich'
    elif lines >= 15:
        return 'medium'
    else:
        return 'thin'


# ═══════════════════════════════════════════════════════════════════════
# MAIN FORMULA
# ═══════════════════════════════════════════════════════════════════════

def compute_budget(
    subconcept_id: str,
    density: dict,
    existing_questions: list,
    existing_solved_examples: int,
) -> dict:
    """
    Compute generation budget for a subconcept.

    existing_questions: list of mapped back exercises + in-text questions
    existing_solved_examples: count of NCERT solved examples in this subconcept

    Returns:
        questions_to_generate: int (0 if existing >= cap)
        examples_to_generate: int (0 if existing >= cap)
        tier: str
        question_cap: int
        example_cap: int
    """
    tier = determine_tier(density)
    question_cap = QUESTION_CAPS[tier]
    example_cap = EXAMPLE_CAPS[tier]

    # Questions: cap - existing (floor at 0)
    questions_to_generate = max(0, question_cap - len(existing_questions))

    # Examples: cap - existing (floor at 0)
    examples_to_generate = max(0, example_cap - existing_solved_examples)

    return {
        'subconcept_id': subconcept_id,
        'tier': tier,
        'question_cap': question_cap,
        'example_cap': example_cap,
        'existing_questions': len(existing_questions),
        'existing_examples': existing_solved_examples,
        'questions_to_generate': questions_to_generate,
        'examples_to_generate': examples_to_generate,
        '_note': 'Question TYPE split and DIFFICULTY split are decided by research classification, not this formula.',
    }


# ═══════════════════════════════════════════════════════════════════════
# RUN ON CH9
# ═══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(PROJECT_ROOT))
    from src.common import chapter_config
    from src.common.backup import safe_write_json

    parser = argparse.ArgumentParser(description='Capacity formula (FREE)')
    parser.add_argument('--chapter', help='Chapter key from chapter_config registry')
    args = parser.parse_args()

    if args.chapter:
        cfg = chapter_config.load(args.chapter)
        lr_path = cfg.line_ranges_path
        mapped_path = cfg.mapped_path
        exercises_path = cfg.exercises_path
        budget_path = cfg.budget_path
    else:
        lr_path = Path('experiments/03_topology_generation/ch09_line_ranges.json')
        mapped_path = Path('experiments/03_topology_generation/ch09_mapped_B.json')
        exercises_path = Path('experiments/03_topology_generation/ch09_exercises.json')
        budget_path = Path('experiments/03_topology_generation/ch09_generation_budget.json')

    with open(lr_path, 'r', encoding='utf-8') as f:
        lr = json.load(f)
    with open(mapped_path, 'r', encoding='utf-8') as f:
        mapped = json.load(f)
    with open(exercises_path, 'r', encoding='utf-8') as f:
        exercises = json.load(f)

    # Build per-subconcept inventory
    mappings = mapped.get('mappings', [])
    sub_questions = {data['name']: [] for sid, data in lr.items()}

    for m in mappings:
        name = m['subconcept']
        for sname in sub_questions:
            if name[:30] in sname[:30] or sname[:30] in name[:30]:
                sub_questions[sname].append({
                    'id': m['id'],
                    'difficulty': m['difficulty'],
                    'type': m.get('type', 'subjective'),
                })
                break

    # Map solved examples by line range
    sub_examples = {data['name']: 0 for sid, data in lr.items()}
    for ex in exercises.get('solved_examples', []):
        for sid, data in lr.items():
            if data['line_start'] <= ex['line_start'] < data['line_end']:
                sub_examples[data['name']] += 1
                break

    # Compute budgets
    print(f"{'ID':<7} {'SUBCONCEPT':<50} {'TIER':<7} {'Q_CAP':>5} {'EXIST':>5} {'Q_GEN':>5} {'E_CAP':>5} {'E_EX':>4} {'E_GEN':>5}")
    print("=" * 150)

    total_q_gen = 0
    total_e_gen = 0
    results = {}

    for sid, data in lr.items():
        name = data['name']
        density = data['density']
        existing_q = sub_questions.get(name, [])
        existing_e = sub_examples.get(name, 0)

        budget = compute_budget(sid, density, existing_q, existing_e)
        results[sid] = budget

        total_q_gen += budget['questions_to_generate']
        total_e_gen += budget['examples_to_generate']

        print(f"{sid:<7} {name[:50]:<50} {budget['tier']:<7} {budget['question_cap']:>5} {budget['existing_questions']:>5} {budget['questions_to_generate']:>5} {budget['example_cap']:>5} {budget['existing_examples']:>4} {budget['examples_to_generate']:>5}")

    print(f"\n{'='*150}")
    print(f"TOTAL: {total_q_gen} questions + {total_e_gen} examples = {total_q_gen + total_e_gen} items to generate")
    print(f"\nNOTE: Question type split (SCQ vs Subjective) and difficulty split (Easy/Medium/Hard)")
    print(f"      will be determined by Task #6 (research classification), not by this formula.")

    safe_write_json(budget_path, results)
    print(f"\nSaved: {budget_path}")
