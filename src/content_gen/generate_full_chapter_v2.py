"""
generate_full_chapter_v2.py - Content generation per subconcept (Gemini 3.1 Pro HIGH).

Reads:
  - cfg.mmd_path                              (chapter MMD for grounding)
  - cfg.line_ranges_path                      (per-sub line range + density)
  - cfg.unified_mapping_path                  (existing source questions per sub)
  - cfg.classified_budget_path                (category + type_split per sub)
  - cfg.image_codes_path                      (optional; per-sub image attachments)

Writes one JSON PER subconcept (immediately after LLM returns) to:
  cfg.content_per_sub_dir / {sid}.json

Resume-safe:
  - on re-run, scans content_per_sub_dir for already-completed subs and SKIPS them
  - each LLM response is persisted before the next sub is invoked
  - a per-run summary file `_run_summary.json` is updated after every sub
    so a crash mid-loop never loses cumulative state

Cost gate:
  - per-chapter cost gate fires once before any LLM call
  - each sub's actual cost is added to experiments/_cost_log.jsonl

LLM cascade:
  - AI Studio Gemini -> Vertex AI Gemini -> Anthropic Claude (via src.common.llm_client)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "content_gen"))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.common import chapter_config, llm_client  # noqa: F401 (.env load via dotenv)
from src.common.backup import safe_write_json
from src.common.cost_gate import CostEstimate, confirm_spend, log_spend
from src.common.llm_client import (
    is_permission_error,
    make_anthropic_client,
    make_gemini_client,
)

from prompt_templates_v2 import SYSTEM_PROMPT, build_full_prompt
from post_process import post_process_content, validate_latex

MODEL = "gemini-3.1-pro-preview"
THINKING = "HIGH"

# pricing (Gemini 3.1 Pro)
INPUT_UNCACHED_RATE = 2.00
INPUT_CACHED_RATE = 1.00
OUTPUT_RATE = 12.00  # includes thinking
INR_PER_USD = 85

# pattern map per category (drives Stage 7 question subtype hints)
PATTERN_MAP = {
    "NUMERICAL":  {"scq": ["N-SCQ-1", "N-SCQ-2"], "subj_numerical": ["N-SUBJ-1", "N-SUBJ-2"], "subj_descriptive": ["N-SUBJ-4"]},
    "CONCEPTUAL": {"scq": ["C-SCQ-1", "C-SCQ-2", "C-SCQ-3"], "subj_descriptive": ["C-SUBJ-1", "C-SUBJ-2", "C-SUBJ-3"], "subj_numerical": ["N-SUBJ-1"]},
    "DIAGRAM":    {"scq": ["D-SCQ-1", "D-SCQ-2"], "subj_diagram": ["D-SUBJ-1", "D-SUBJ-2", "D-SUBJ-3"], "subj_descriptive": ["C-SUBJ-1"]},
    "FACTUAL":    {"scq": ["F-SCQ-1", "F-SCQ-2"], "subj_descriptive": ["F-SUBJ-1", "F-SUBJ-2"]},
}


def _is_completed_sub_file(p: Path) -> bool:
    """A sub's JSON is considered complete if it parses and has non-error content."""
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        content = data.get("content", data)
        if "error" in content:
            return False
        n_items = (
            len(content.get("scqs", []))
            + len(content.get("subjective", []))
            + len(content.get("examples", []))
        )
        return n_items > 0 or bool(content.get("theory"))
    except Exception:
        return False


def _parse_json_with_recovery(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        brace = re.search(r"\{.*", raw, re.DOTALL)
        if not brace:
            return {"error": "no_json", "raw": raw[:2000]}
        js = brace.group()
        while js.count("{") > js.count("}"):
            js += "}"
        while js.count("[") > js.count("]"):
            js += "]"
        try:
            return json.loads(js)
        except json.JSONDecodeError:
            return {"error": "json_parse_failed", "raw": raw[:2000]}


def _build_gemini_client_with_cache(prefer_vertex: bool, system_prompt: str, mmd: str):
    """Build client + optional cache handle. Vertex doesn't share AI Studio's cache API,
    so on Vertex we return cache_handle=None and inline the MMD per request."""
    from google.genai import types

    client = make_gemini_client(prefer_vertex=prefer_vertex)
    cache_handle = None
    if not prefer_vertex:
        try:
            cache = client.caches.create(
                model=MODEL,
                config=types.CreateCachedContentConfig(
                    system_instruction=system_prompt,
                    contents=[types.Content(role="user", parts=[types.Part.from_text(text=mmd)])],
                    ttl="3600s",
                ),
            )
            cache_handle = cache.name
            print(f"  Cache created: {cache_handle}")
        except Exception as e:
            print(f"  Cache create failed (continuing without cache): {str(e)[:120]}")
            cache_handle = None
    return client, cache_handle


def _generate_one_sub(
    client, cache_handle, on_vertex: bool,
    system_prompt: str, mmd: str,
    sub_info: dict, sub_images: list,
) -> tuple[dict, dict, float, str]:
    """Make one Gemini call for one sub. Returns (content, tokens, cost_usd, provider_label)."""
    from google.genai import types

    _, user_prompt = build_full_prompt(
        sub_info["subconcept_id"],
        sub_info["subconcept_name"],
        sub_info["line_start"],
        sub_info["line_end"],
        sub_info["category"],
        sub_info["type_split"],
        sub_info["examples_to_generate"],
        PATTERN_MAP[sub_info["category"]],
        sub_info["existing_questions"],
        sub_info["existing_examples"],
        sub_images,
    )

    parts = []
    if cache_handle is None:
        # Vertex path: inline MMD in user content
        parts.append(types.Part.from_text(text=f"DOCUMENT (chapter MMD):\n{mmd}\n\n{user_prompt}"))
    else:
        parts.append(types.Part.from_text(text=user_prompt))

    for img in sub_images:
        local = img.get("local_file")
        if local and Path(local).exists():
            parts.append(types.Part.from_text(text=f"\n[Image: {img['code']}]"))
            parts.append(types.Part.from_bytes(data=Path(local).read_bytes(), mime_type="image/jpeg"))

    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.3,
        max_output_tokens=16000,
        thinking_config=types.ThinkingConfig(thinking_level=THINKING),
    )
    if cache_handle:
        cfg.cached_content = cache_handle
    else:
        cfg.system_instruction = system_prompt

    resp = client.models.generate_content(
        model=MODEL,
        contents=types.Content(role="user", parts=parts),
        config=cfg,
    )

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
    cost = (
        (uncached / 1e6) * INPUT_UNCACHED_RATE
        + (tokens["cached"] / 1e6) * INPUT_CACHED_RATE
        + ((tokens["output"] + tokens["thinking"]) / 1e6) * OUTPUT_RATE
    )

    content = _parse_json_with_recovery(raw)
    if "error" not in content:
        content = post_process_content(content)

    provider = "gemini_vertex" if on_vertex else "gemini_aistudio"
    return content, tokens, cost, provider


def main():
    parser = argparse.ArgumentParser(description="Per-subconcept content generation (PAID, Gemini Pro HIGH)")
    parser.add_argument("--chapter", required=True, help="Chapter key")
    parser.add_argument("--only-sub", help="Restrict to a single subconcept id (e.g. C1.S1) for dry-test")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-generate even if sub output already exists")
    args = parser.parse_args()

    cfg = chapter_config.load(args.chapter)

    # Inputs
    mmd = cfg.mmd_path.read_text(encoding="utf-8")
    line_ranges = json.loads(cfg.line_ranges_path.read_text(encoding="utf-8"))
    unified = json.loads(cfg.unified_mapping_path.read_text(encoding="utf-8"))
    classified = json.loads(cfg.classified_budget_path.read_text(encoding="utf-8"))

    img_codes: dict = {}
    if cfg.image_codes_path.exists():
        img_codes = json.loads(cfg.image_codes_path.read_text(encoding="utf-8"))
        print(f"Loaded {len(img_codes)} image codes for grounding")
    else:
        print(f"NOTE: {cfg.image_codes_path.name} not present - generating without image attachments")

    # Outputs
    cfg.content_per_sub_dir.mkdir(parents=True, exist_ok=True)
    cfg.content_dir.mkdir(parents=True, exist_ok=True)
    summary_path = cfg.content_dir / "_run_summary.json"

    # Decide which subs to process (resume-safe)
    target_sids = sorted(line_ranges.keys())
    if args.only_sub:
        target_sids = [args.only_sub]
        if args.only_sub not in line_ranges:
            print(f"ERROR: --only-sub {args.only_sub} not in line_ranges")
            sys.exit(2)

    todo = []
    skipped = []
    for sid in target_sids:
        per_sub_file = cfg.content_per_sub_dir / f"{sid}.json"
        if not args.force and _is_completed_sub_file(per_sub_file):
            skipped.append(sid)
        else:
            todo.append(sid)

    print(f"\nResume status: {len(skipped)} already complete, {len(todo)} to generate")
    if skipped:
        print(f"  SKIP (use --force to regenerate): {', '.join(skipped)}")
    if not todo:
        print("Nothing to do. All subs already complete. Use --force to override.")
        return 0

    # Cost gate
    n_total_items = sum(
        classified[sid]["questions_to_generate"] + classified[sid]["examples_to_generate"]
        for sid in todo
    )
    est_inr_per_sub = 10.0  # empirical for Gemini 3.1 Pro HIGH ~8-12 Rs/sub at this MMD size
    est = CostEstimate(
        stage="content_gen_gemini_pro_high",
        chapter_key=args.chapter,
        item_count=len(todo),
        inr_estimate=round(len(todo) * est_inr_per_sub, 2),
        model=MODEL,
        thinking_level=THINKING,
        notes=f"generate {n_total_items} items across {len(todo)} subs (resume-safe)",
    )
    proceed = confirm_spend(est, yes=args.yes, dry_run=args.dry_run)

    if args.dry_run:
        print("\n[dry-run] would generate:")
        for sid in todo:
            c = classified[sid]
            print(f"  {sid}  [{c['category']:<11} tier={c['tier']:<6}] "
                  f"Q={c['questions_to_generate']}, EX={c['examples_to_generate']}, "
                  f"split={c['type_split']}")
        return 0
    if not proceed:
        print("Aborted at cost gate.")
        return 1

    # Build client with cascade-aware cache. Try AI Studio first; on permission error, Vertex.
    print(f"\nBuilding Gemini client (preferred path: AI Studio with cached MMD)...")
    on_vertex = False
    try:
        client, cache_handle = _build_gemini_client_with_cache(False, SYSTEM_PROMPT, mmd)
        # cheap probe: list models or skip — Gemini caches.create may already 200 even
        # when generate_content will 403, so we test on the first real sub and switch then
    except Exception as e:
        if not is_permission_error(e):
            raise
        print(f"  AI Studio rejected at client init -> using Vertex AI")
        client, cache_handle = _build_gemini_client_with_cache(True, SYSTEM_PROMPT, mmd)
        on_vertex = True

    # Per-sub generation loop
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

    for sid in todo:
        c = classified[sid]
        lr = line_ranges[sid]
        u = unified.get(sid, {})

        sub_info = {
            "subconcept_id": sid,
            "subconcept_name": lr["name"],
            "line_start": lr["line_start"],
            "line_end": lr["line_end"],
            "category": c["category"],
            "type_split": c["type_split"],
            "examples_to_generate": c["examples_to_generate"],
            "existing_questions": u.get("back_exercises", []) + u.get("intext_questions", []),
            "existing_examples": u.get("solved_examples", []),
        }

        sub_images = [
            {"code": code, "caption": info.get("caption", info.get("derived_caption", "")), "local_file": info.get("local_file")}
            for code, info in img_codes.items()
            if info.get("subconcept_id") == sid
        ]

        print(f"\n{'='*80}\n{sid}: {sub_info['subconcept_name']} [{c['category']}, tier={c['tier']}]")
        print(f"  Generate: {c['questions_to_generate']} Qs ({c['type_split']}) + {c['examples_to_generate']} examples")
        print(f"  Images attached: {len(sub_images)}")

        start = time.time()
        try:
            content, tokens, cost_usd, provider = _generate_one_sub(
                client, cache_handle, on_vertex, SYSTEM_PROMPT, mmd, sub_info, sub_images,
            )
        except Exception as e1:
            if is_permission_error(e1) and not on_vertex:
                print(f"  AI Studio denied mid-loop -> switching to Vertex AI")
                client, cache_handle = _build_gemini_client_with_cache(True, SYSTEM_PROMPT, mmd)
                on_vertex = True
                try:
                    content, tokens, cost_usd, provider = _generate_one_sub(
                        client, cache_handle, on_vertex, SYSTEM_PROMPT, mmd, sub_info, sub_images,
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

        # Validate
        if "error" not in content:
            checks = validate_latex(content)
            print(f"  Tokens: in={tokens['input']} (cached={tokens['cached']}), out={tokens['output']}, think={tokens['thinking']}")
            print(f"  Cost: ${cost_usd:.4f} / Rs {cost_inr} | Time: {elapsed:.1f}s | Provider: {provider}")
            print(f"  Generated: {len(content.get('scqs', []))} SCQs + {len(content.get('subjective', []))} subj + {len(content.get('examples', []))} ex")
            print(f"  Validation: LaTeX={'OK' if checks['latex_compliant'] else 'FAIL'} | imgClean={'OK' if checks['image_codes_clean'] else 'FAIL'} | NCERTclean={'OK' if checks['ncert_refs_clean'] else 'FAIL'}")
        else:
            print(f"  CONTENT ERROR: {content.get('error')}")

        # Persist IMMEDIATELY (resume-safe)
        result_data = {
            "content": content,
            "cost": {
                "tokens": tokens,
                "uncached": tokens["input"] - tokens["cached"],
                "cost_usd": cost_usd,
                "cost_inr": cost_inr,
                "elapsed": round(elapsed, 1),
                "provider": provider,
            },
        }
        per_sub_file = cfg.content_per_sub_dir / f"{sid}.json"
        safe_write_json(per_sub_file, result_data)
        print(f"  Saved: {per_sub_file.name}")

        # Log spend per sub
        per_sub_est = CostEstimate(
            stage="content_gen_per_sub",
            chapter_key=args.chapter,
            item_count=1,
            inr_estimate=cost_inr,
            model=MODEL,
            thinking_level=THINKING,
            notes=f"sub {sid}",
        )
        log_spend(per_sub_est, actual_inr=cost_inr, status="ok")

        # Update summary after every sub
        summary["subs_completed_this_run"].append(sid)
        summary["total_cost_usd"] = round(summary["total_cost_usd"] + cost_usd, 4)
        summary["total_cost_inr"] = round(summary["total_cost_inr"] + cost_inr, 4)
        summary["total_time_sec"] = round(summary["total_time_sec"] + elapsed, 1)
        safe_write_json(summary_path, summary)

    # Final report
    summary["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    safe_write_json(summary_path, summary)

    print(f"\n{'='*80}\nCONTENT GENERATION COMPLETE")
    print(f"  this run: {len(summary['subs_completed_this_run'])} subs generated, {len(summary['subs_failed_this_run'])} failed")
    print(f"  resumed-skipped: {len(skipped)} (already complete from prior run)")
    print(f"  total cost this run: Rs {summary['total_cost_inr']}")
    print(f"  total time: {summary['total_time_sec']:.0f}s")
    print(f"  per-sub outputs: {cfg.content_per_sub_dir}")
    return 0 if not summary["subs_failed_this_run"] else 3


if __name__ == "__main__":
    sys.exit(main())
