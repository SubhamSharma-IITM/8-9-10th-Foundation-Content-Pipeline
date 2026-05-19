"""
generate_solutions_v2.py - Solution generation for SOURCE questions (those without solutions in MMD).

Inputs:
  - cfg.mmd_path
  - cfg.line_ranges_path
  - cfg.unified_mapping_path
  - cfg.image_codes_path (optional)

Outputs (per sub, immediately saved for resume-safety):
  cfg.solutions_dir / {sid}_solutions.json

Resume-safe: skip subs whose solutions file already exists. Use --force to regenerate.
LLM cascade: AI Studio Gemini -> Vertex AI Gemini (via src/common/llm_client).
Cost gate fires once at start; per-sub cost is logged.

NOTE: Gemini 3.1 Pro pricing constants ($2/$1/$12 per Mtok) inherited from
generate_solutions.py — not externally re-verified against current Google pricing.
See feedback_no_fabricated_metadata.md. Calls still work; only the cost-log
bookkeeping is affected if Google changed rates.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "content_gen"))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.common import chapter_config, llm_client  # noqa: F401
from src.common.backup import safe_write_json
from src.common.cost_gate import CostEstimate, confirm_spend, log_spend
from src.common.llm_client import is_permission_error, make_gemini_client

from generate_solutions import SOLUTION_SYSTEM_PROMPT, build_solution_prompt
from post_process import post_process_content

MODEL = "gemini-3.1-pro-preview"
THINKING = "HIGH"

# Pricing (unverified - copied from generate_solutions.py, vintage Mar 2026)
INPUT_UNCACHED_RATE = 2.00
INPUT_CACHED_RATE = 1.00
OUTPUT_RATE = 12.00
INR_PER_USD = 85


def _is_completed_solutions_file(p: Path, expected_qs: int) -> bool:
    if not p.exists():
        return False
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        sols = d.get("solutions", [])
        return len(sols) >= expected_qs * 0.9  # tolerate one missing
    except Exception:
        return False


def _build_client_and_cache(prefer_vertex: bool, mmd: str):
    """Build genai client + optional AI Studio cache handle."""
    from google.genai import types

    client = make_gemini_client(prefer_vertex=prefer_vertex)
    cache_handle = None
    if not prefer_vertex:
        try:
            cache = client.caches.create(
                model=MODEL,
                config=types.CreateCachedContentConfig(
                    system_instruction=SOLUTION_SYSTEM_PROMPT,
                    contents=[types.Content(role="user", parts=[types.Part.from_text(text=mmd)])],
                    ttl="3600s",
                ),
            )
            cache_handle = cache.name
            print(f"  Cache created: {cache_handle}")
        except Exception as e:
            print(f"  Cache create failed: {str(e)[:120]}")
    return client, cache_handle


def _generate_solutions_for_sub(client, cache_handle, on_vertex, mmd, sid, name, line_start, line_end, questions, image_codes):
    from google.genai import types

    prompt = build_solution_prompt(sid, name, line_start, line_end, questions, image_codes)

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.3,
        max_output_tokens=16000,
        thinking_config=types.ThinkingConfig(thinking_level=THINKING),
    )
    if cache_handle:
        config.cached_content = cache_handle
        contents = prompt
    else:
        config.system_instruction = SOLUTION_SYSTEM_PROMPT
        contents = f"DOCUMENT (chapter MMD):\n{mmd}\n\n{prompt}"

    resp = client.models.generate_content(model=MODEL, contents=contents, config=config)
    raw = ""
    for part in resp.candidates[0].content.parts:
        if hasattr(part, "thought") and part.thought:
            continue
        if hasattr(part, "text") and part.text:
            raw += part.text
    um = resp.usage_metadata
    tokens = {
        "input": getattr(um, "prompt_token_count", 0) or 0,
        "output": getattr(um, "candidates_token_count", 0) or 0,
        "cached": getattr(um, "cached_content_token_count", 0) or 0,
        "thinking": getattr(um, "thoughts_token_count", 0) or 0,
    }
    uncached = tokens["input"] - tokens["cached"]
    cost_usd = (
        uncached / 1e6 * INPUT_UNCACHED_RATE
        + tokens["cached"] / 1e6 * INPUT_CACHED_RATE
        + (tokens["output"] + tokens["thinking"]) / 1e6 * OUTPUT_RATE
    )

    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        brace = re.search(r"\{.*", text, re.DOTALL)
        if not brace:
            result = {"error": "no_json", "raw": text[:1000]}
        else:
            js = brace.group()
            while js.count("{") > js.count("}"):
                js += "}"
            while js.count("[") > js.count("]"):
                js += "]"
            try:
                result = json.loads(js)
            except Exception:
                result = {"error": "json_parse_failed", "raw": text[:1000]}

    # Post-process solutions through the same cleaner
    if "error" not in result:
        cleaned = post_process_content(result)
        result = cleaned

    provider = "gemini_vertex" if on_vertex else "gemini_aistudio"
    return result, tokens, cost_usd, provider


def main():
    p = argparse.ArgumentParser(description="Solution generation for SOURCE questions (PAID, Gemini Pro HIGH)")
    p.add_argument("--chapter", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--only-sub", help="Restrict to one sid")
    args = p.parse_args()

    cfg = chapter_config.load(args.chapter)
    mmd = cfg.mmd_path.read_text(encoding="utf-8")
    lr = json.loads(cfg.line_ranges_path.read_text(encoding="utf-8"))
    unified = json.loads(cfg.unified_mapping_path.read_text(encoding="utf-8"))

    img_codes: dict = {}
    if cfg.image_codes_path.exists():
        img_codes = json.loads(cfg.image_codes_path.read_text(encoding="utf-8"))

    cfg.solutions_dir.mkdir(parents=True, exist_ok=True)

    # Build queue: subs with source questions missing solutions
    queue: dict[str, list] = {}
    for sid, data in unified.items():
        if args.only_sub and sid != args.only_sub:
            continue
        qs = []
        for q in data.get("back_exercises", []) + data.get("intext_questions", []):
            if not q.get("solution"):
                qs.append(q)
        if qs:
            queue[sid] = qs

    if not queue:
        print("No source questions need solutions. Nothing to do.")
        return 0

    # Resume-safe filter
    todo = {}
    skipped = []
    for sid, qs in queue.items():
        f = cfg.solutions_dir / f"{sid}_solutions.json"
        if not args.force and _is_completed_solutions_file(f, len(qs)):
            skipped.append(sid)
        else:
            todo[sid] = qs

    total_qs_todo = sum(len(qs) for qs in todo.values())
    print(f"Resume: {len(skipped)} subs skipped (already complete), {len(todo)} subs to run ({total_qs_todo} questions)")
    if not todo:
        print("Everything already done. Use --force to regenerate.")
        return 0

    # Cost gate (empirical: ~Rs 1.5-2 per question for Gemini Pro HIGH solutions)
    est_inr = round(total_qs_todo * 1.8, 2)
    est = CostEstimate(
        stage="solution_gen_gemini_pro_high",
        chapter_key=args.chapter,
        item_count=total_qs_todo,
        inr_estimate=est_inr,
        model=MODEL,
        thinking_level=THINKING,
        notes=f"generate solutions for {total_qs_todo} source questions across {len(todo)} subs",
    )
    proceed = confirm_spend(est, yes=args.yes, dry_run=args.dry_run)
    if args.dry_run:
        for sid, qs in todo.items():
            print(f"  {sid}: {len(qs)} questions")
        return 0
    if not proceed:
        print("Aborted at cost gate.")
        return 1

    # Build client (try AI Studio first; fall back to Vertex on first 403)
    on_vertex = False
    try:
        client, cache_handle = _build_client_and_cache(False, mmd)
    except Exception as e:
        if not is_permission_error(e):
            raise
        print("  AI Studio rejected at init -> Vertex")
        client, cache_handle = _build_client_and_cache(True, mmd)
        on_vertex = True

    summary_path = cfg.content_dir / "_solutions_run_summary.json"
    summary = {
        "chapter_key": args.chapter,
        "model": MODEL,
        "thinking": THINKING,
        "subs_total": len(todo) + len(skipped),
        "subs_skipped_resume": skipped,
        "subs_completed_this_run": [],
        "subs_failed_this_run": [],
        "total_cost_usd": 0.0,
        "total_cost_inr": 0.0,
        "total_time_sec": 0.0,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    for sid, questions in todo.items():
        sub_data = lr[sid]
        sub_images = [
            {"code": c, "caption": info.get("caption", info.get("derived_caption", ""))}
            for c, info in img_codes.items()
            if info.get("subconcept_id") == sid
        ]
        print(f"\n{'='*80}\n{sid}: {sub_data['name']} — {len(questions)} questions...")

        start = time.time()
        try:
            result, tokens, cost_usd, provider = _generate_solutions_for_sub(
                client, cache_handle, on_vertex, mmd,
                sid, sub_data["name"], sub_data["line_start"], sub_data["line_end"],
                questions, sub_images,
            )
        except Exception as e1:
            if is_permission_error(e1) and not on_vertex:
                print("  AI Studio denied -> Vertex")
                client, cache_handle = _build_client_and_cache(True, mmd)
                on_vertex = True
                try:
                    result, tokens, cost_usd, provider = _generate_solutions_for_sub(
                        client, cache_handle, on_vertex, mmd,
                        sid, sub_data["name"], sub_data["line_start"], sub_data["line_end"],
                        questions, sub_images,
                    )
                except Exception as e2:
                    print(f"  Vertex also failed: {str(e2)[:200]}")
                    summary["subs_failed_this_run"].append({"sid": sid, "error": str(e2)[:200]})
                    safe_write_json(summary_path, summary)
                    continue
            else:
                print(f"  ERROR: {str(e1)[:200]}")
                summary["subs_failed_this_run"].append({"sid": sid, "error": str(e1)[:200]})
                safe_write_json(summary_path, summary)
                continue

        elapsed = time.time() - start
        cost_inr = round(cost_usd * INR_PER_USD, 4)
        sols = result.get("solutions", []) if "error" not in result else []
        print(f"  [{provider}] tokens={tokens} | Rs {cost_inr} | {elapsed:.1f}s | solved {len(sols)}/{len(questions)}")

        # Persist immediately
        out = {
            "solutions": sols,
            "cost": {"tokens": tokens, "cost_usd": cost_usd, "cost_inr": cost_inr, "elapsed": round(elapsed, 1), "provider": provider},
        }
        if "error" in result:
            out["error"] = result.get("error")
            out["raw"] = result.get("raw")
        safe_write_json(cfg.solutions_dir / f"{sid}_solutions.json", out)

        # Cost log
        log_spend(
            CostEstimate(stage="solution_gen_per_sub", chapter_key=args.chapter,
                         item_count=len(questions), inr_estimate=cost_inr,
                         model=MODEL, thinking_level=THINKING, notes=f"sub {sid}"),
            actual_inr=cost_inr, status="ok" if "error" not in result else "partial_error",
        )

        summary["subs_completed_this_run"].append(sid)
        summary["total_cost_usd"] = round(summary["total_cost_usd"] + cost_usd, 4)
        summary["total_cost_inr"] = round(summary["total_cost_inr"] + cost_inr, 4)
        summary["total_time_sec"] = round(summary["total_time_sec"] + elapsed, 1)
        safe_write_json(summary_path, summary)

    summary["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    safe_write_json(summary_path, summary)

    print(f"\n{'='*80}\nSOLUTION GENERATION COMPLETE")
    print(f"  this run: {len(summary['subs_completed_this_run'])} subs ({total_qs_todo} questions)")
    print(f"  failed: {len(summary['subs_failed_this_run'])}")
    print(f"  total cost this run: Rs {summary['total_cost_inr']}")
    return 0 if not summary["subs_failed_this_run"] else 3


if __name__ == "__main__":
    sys.exit(main())
