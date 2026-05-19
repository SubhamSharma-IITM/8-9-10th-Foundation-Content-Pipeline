"""
classify_subconcepts.py - Per-subconcept category tagging (NUMERICAL / CONCEPTUAL / DIAGRAM / FACTUAL).

For each subconcept in the chapter, decide one category. Apply the hardcoded
type-split formula to compute how many of each question subtype to generate.

Output shape matches experiments/04_subconcept_classification/<sub>_classified_budget.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.common import chapter_config, llm_client  # noqa: F401  (load .env via dotenv on import)
from src.common.backup import safe_write_json
from src.common.cost_gate import CostEstimate, confirm_spend, log_spend
from src.common.llm_client import is_permission_error, make_anthropic_client, make_gemini_client


# Hardcoded type-split per category (from experiments/04_subconcept_classification/category_definitions.md)
TYPE_SPLITS = {
    'NUMERICAL':  {'scq': 0.40, 'subj_numerical': 0.40, 'subj_descriptive': 0.20},
    'CONCEPTUAL': {'scq': 0.50, 'subj_descriptive': 0.40, 'subj_numerical': 0.10},
    'DIAGRAM':    {'scq': 0.40, 'subj_diagram': 0.40, 'subj_descriptive': 0.20},
    'FACTUAL':    {'scq': 0.60, 'subj_descriptive': 0.40},
}


def compute_type_split(N: int, category: str) -> dict[str, int]:
    """Apply category split proportions to N total questions, rounding to int."""
    split = TYPE_SPLITS[category]
    result: dict[str, int] = {}
    remaining = N
    for stype, proportion in split.items():
        count = round(N * proportion)
        result[stype] = count
        remaining -= count
    if remaining != 0 and result:
        largest = max(result, key=result.get)
        result[largest] += remaining
    return result


SYSTEM_PROMPT = """You are an expert CBSE Class 10 Science teacher.

For each subconcept of the given chapter, classify it into EXACTLY ONE of these 4 categories:

NUMERICAL: involves formulas, calculations, sign conventions. Student computes values.
CONCEPTUAL: understanding principles, relationships, comparisons. No heavy calculation.
DIAGRAM: heavily visual - ray diagrams, field-line diagrams, figure-based reasoning, tables of cases.
FACTUAL: definitions, terminology, applications. Memory-based recall.

Output STRICT JSON:
{
  "classifications": [
    {"id": "C1.S1", "name": "...", "category": "CONCEPTUAL", "rationale": "one sentence"},
    ...
  ]
}

Pick the SINGLE dominant character. If a sub mixes (e.g. numerical AND diagram), pick the one that drives the question style the most."""


def build_prompt(schema: dict, line_ranges: dict, chapter_name: str) -> str:
    """Build the per-chapter classification prompt."""
    lines = [f"CHAPTER: {chapter_name}\n\nSUBCONCEPTS TO CLASSIFY:"]
    for sid, data in line_ranges.items():
        sub_name = data['name']
        density = data.get('density', {})
        lines.append(f"\n[{sid}] {sub_name}")
        lines.append(f"  lines: {density.get('line_count', '?')}, figures: {density.get('figures', '?')}, "
                     f"formulas: {density.get('formulas', '?')}, activities: {density.get('activities', '?')}, "
                     f"examples: {density.get('examples', '?')}")
        lines.append(f"  parent_concept: {data.get('parent_concept', '?')}")
    lines.append("\n\nReturn the JSON classifications.")
    return "\n".join(lines)


def call_llm_for_classification(system_prompt: str, user_prompt: str) -> tuple[dict, str, dict]:
    """LLM call with the same Gemini-AIStudio -> Vertex -> Anthropic cascade."""
    from google import genai
    from google.genai import types

    MODEL = "gemini-3-flash-preview"

    provider_used = "gemini_aistudio"
    raw_text = ""
    tokens = {"input": 0, "output": 0, "cached": 0, "thinking": 0}

    def _call_gemini(client):
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
            max_output_tokens=4000,
            thinking_config=types.ThinkingConfig(thinking_level="LOW"),
            system_instruction=system_prompt,
        )
        resp = client.models.generate_content(model=MODEL, contents=user_prompt, config=config)
        text = ""
        for part in resp.candidates[0].content.parts:
            if hasattr(part, 'thought') and part.thought:
                continue
            if hasattr(part, 'text') and part.text:
                text += part.text
        um = resp.usage_metadata
        return text, {
            "input": getattr(um, 'prompt_token_count', 0) or 0,
            "output": getattr(um, 'candidates_token_count', 0) or 0,
            "cached": getattr(um, 'cached_content_token_count', 0) or 0,
            "thinking": getattr(um, 'thoughts_token_count', 0) or 0,
        }

    try:
        client = make_gemini_client(prefer_vertex=False)
        raw_text, tokens = _call_gemini(client)
    except Exception as e1:
        if not is_permission_error(e1):
            raise
        print("  AI Studio denied -> Vertex...")
        try:
            client = make_gemini_client(prefer_vertex=True)
            provider_used = "gemini_vertex"
            raw_text, tokens = _call_gemini(client)
        except Exception as e2:
            if not is_permission_error(e2):
                raise
            print("  Vertex failed -> Anthropic...")
            provider_used = "anthropic"
            ac = make_anthropic_client()
            resp = ac.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4000,
                system=[{"type": "text", "text": system_prompt}],
                messages=[{"role": "user", "content": user_prompt}],
                timeout=120,
            )
            raw_text = resp.content[0].text
            tokens = {
                "input": resp.usage.input_tokens, "output": resp.usage.output_tokens,
                "cached": 0, "thinking": 0,
            }

    # parse JSON
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    data = json.loads(text)
    return data, provider_used, tokens


def main():
    parser = argparse.ArgumentParser(description="Subconcept classification (PAID LLM, ~Rs 2-5)")
    parser.add_argument("--chapter", required=True, help="Chapter key from chapter_config")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    cfg = chapter_config.load(args.chapter)
    schema = json.loads(cfg.schema_path.read_text(encoding="utf-8"))
    line_ranges = json.loads(cfg.line_ranges_path.read_text(encoding="utf-8"))
    budget = json.loads(cfg.budget_path.read_text(encoding="utf-8"))

    chapter_name = next(iter(schema))
    n_subs = len(line_ranges)
    user_prompt = build_prompt(schema, line_ranges, chapter_name)

    est = CostEstimate(
        stage="classify_subconcepts",
        chapter_key=args.chapter,
        item_count=n_subs,
        inr_estimate=round(max(2.0, n_subs * 0.5), 2),
        model="gemini-3-flash-preview",
        thinking_level="LOW",
        notes=f"classify {n_subs} subconcepts of '{chapter_name}'",
    )
    proceed = confirm_spend(est, yes=args.yes, dry_run=args.dry_run)

    if args.dry_run:
        print("[dry-run] no LLM call. Would classify:")
        for sid, data in line_ranges.items():
            print(f"  {sid}: {data['name']}")
        return 0
    if not proceed:
        print("Aborted.")
        return 1

    print(f"\n=== Classifying {n_subs} subconcepts ===")
    result, provider, tokens = call_llm_for_classification(SYSTEM_PROMPT, user_prompt)
    classifications = result.get("classifications", [])

    if provider == "anthropic":
        cost_usd = (tokens['input']/1e6 * 3.00) + (tokens['output']/1e6 * 15.00)
    else:
        u = tokens['input'] - tokens['cached']
        cost_usd = (u/1e6 * 0.50) + (tokens['cached']/1e6 * 0.25) + ((tokens['output']+tokens['thinking'])/1e6 * 3.00)
    actual_inr = round(cost_usd * 85.0, 4)
    print(f"  Provider: {provider} | Tokens: {tokens} | Rs {actual_inr}")
    log_spend(est, actual_inr=actual_inr, status="ok")

    # Index by id for quick lookup
    cat_by_id = {c["id"]: c for c in classifications}

    classified_budget: dict = {}
    print(f"\n{'ID':<8} {'CATEGORY':<11} {'TIER':<7} {'N_Q':>4} {'SCQ':>4} {'SUBJ':>5}")
    print("-" * 60)
    for sid, b in budget.items():
        cls = cat_by_id.get(sid)
        if not cls:
            print(f"  WARN: no classification returned for {sid}; defaulting to CONCEPTUAL")
            category = "CONCEPTUAL"
            rationale = "default (LLM omitted)"
        else:
            category = cls["category"].upper()
            rationale = cls.get("rationale", "")
            if category not in TYPE_SPLITS:
                print(f"  WARN: invalid category '{category}' for {sid}; defaulting to CONCEPTUAL")
                category = "CONCEPTUAL"

        n_q = b["questions_to_generate"]
        type_split = compute_type_split(n_q, category)
        classified_budget[sid] = {
            "subconcept_name": b.get("subconcept_id") or "",  # downstream may want this
            "category": category,
            "rationale": rationale,
            "tier": b["tier"],
            "questions_to_generate": n_q,
            "examples_to_generate": b["examples_to_generate"],
            "type_split": type_split,
        }
        subj_total = sum(v for k, v in type_split.items() if k != "scq")
        print(f"{sid:<8} {category:<11} {b['tier']:<7} {n_q:>4} {type_split.get('scq', 0):>4} {subj_total:>5}")

    safe_write_json(cfg.classified_budget_path, classified_budget)
    print(f"\nSaved: {cfg.classified_budget_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
