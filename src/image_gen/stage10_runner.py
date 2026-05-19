"""
stage10_runner.py - Chapter-level image generation orchestrator.

For each item flagged with visual_content needs:
  - source_image_ref set  -> COPY existing MathPix-extracted image to chapter images dir
  - image_generation_needed -> LLM-codegen matplotlib code -> sandbox validate -> render PNG
  - retry once on failure (with the error fed back to LLM), then flag for proofread

Outputs:
  cfg.content_dir / images / IMG_<sub>_<seq>.png    (the rendered/copied images)
  cfg.content_dir / images / _manifest.json          (per-image audit: route, status, retries, errors)

Resume-safe: skips images already present in the manifest with status=ok.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.common import chapter_config, llm_client  # noqa: F401
from src.common.backup import safe_write_json
from src.common.cost_gate import CostEstimate, confirm_spend, log_spend
from src.common.llm_client import is_permission_error, make_gemini_client
from src.image_gen.svg_codegen import (
    SVG_SYSTEM_PROMPT,
    build_user_prompt as build_svg_user_prompt,
    codegen_svg_and_render,
)

CODEGEN_MODEL = "gemini-3-flash-preview"
THINKING = "LOW"


def _llm_codegen_svg(description: str, image_code: str, chapter_name: str = "", subconcept_name: str = "", prev_error: str = "") -> tuple[str, str]:
    """Call LLM to generate SVG markup. Returns (raw_svg, provider_used)."""
    from google.genai import types

    user_prompt = build_svg_user_prompt(
        description, image_code,
        chapter_name=chapter_name, subconcept_name=subconcept_name,
        prev_error=prev_error,
    )

    def _call(client):
        config = types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=4000,
            thinking_config=types.ThinkingConfig(thinking_level=THINKING),
            system_instruction=SVG_SYSTEM_PROMPT,
        )
        resp = client.models.generate_content(model=CODEGEN_MODEL, contents=user_prompt, config=config)
        text = ""
        for part in resp.candidates[0].content.parts:
            if hasattr(part, "thought") and part.thought:
                continue
            if hasattr(part, "text") and part.text:
                text += part.text
        return text

    try:
        client = make_gemini_client(prefer_vertex=False)
        return _call(client), "gemini_aistudio"
    except Exception as e:
        if not is_permission_error(e):
            raise
        client = make_gemini_client(prefer_vertex=True)
        return _call(client), "gemini_vertex"


def _walk_for_visual_items(per_sub_dir: Path, solutions_dir: Path):
    """Yield (file_kind, sid, item_idx, scope, vc_block) for every visual_content
    block in the chapter's generated content and solutions."""
    for f in sorted(per_sub_dir.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        c = d.get("content", {})
        sid = f.stem  # e.g. "C1.S1"
        tvc = c.get("theory_visual_content")
        if tvc and (tvc.get("needed") or tvc.get("image_generation_needed")):
            yield ("content", sid, -1, "theory", tvc)
        for idx, q in enumerate(c.get("scqs", []) + c.get("subjective", []) + c.get("examples", [])):
            for scope in ("question_visual_content", "solution_visual_content", "visual_content"):
                vc = q.get(scope)
                if not vc:
                    continue
                if vc.get("needed") or vc.get("image_generation_needed"):
                    yield ("content", sid, idx, scope, vc)
    for f in sorted(solutions_dir.glob("*_solutions.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        sid = f.stem.replace("_solutions", "")
        for idx, s in enumerate(d.get("solutions", [])):
            vc = s.get("visual_content")
            if vc and (vc.get("needed") or vc.get("image_generation_needed")):
                yield ("solution", sid, idx, "solution", vc)


def _img_code(sid: str, seq: int) -> str:
    """e.g. C1.S1 + seq=2 -> IMG_C1.S1_2"""
    return f"IMG_{sid}_{seq}"


def _copy_source_image(ref: str, mathpix_dir: Path, dest: Path) -> tuple[bool, str]:
    """Look up the MathPix-extracted image whose filename starts with `ref` (or matches the basename),
    copy it to dest. Returns (success, error_message)."""
    # The source_image_ref is typically the full filename e.g. "<pdfid>-NN_X_Y_W_H.jpg"
    # Search the mmd_extracted dir recursively
    base = Path(ref).name
    matches = list(mathpix_dir.rglob(base))
    if not matches:
        # Try a partial match (without extension or with stem)
        stem = Path(ref).stem
        matches = list(mathpix_dir.rglob(f"{stem}*"))
    if not matches:
        return False, f"source image not found: {ref}"
    shutil.copy2(matches[0], dest)
    return True, ""


def main():
    p = argparse.ArgumentParser(description="Stage 10 image generation orchestrator")
    p.add_argument("--chapter", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--force", action="store_true", help="Re-render images already in manifest")
    args = p.parse_args()

    cfg = chapter_config.load(args.chapter)
    per_sub_dir = cfg.content_per_sub_dir
    solutions_dir = cfg.solutions_dir
    images_dir = cfg.content_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = images_dir / "_manifest.json"

    # MathPix extracted image dir for source_image_ref lookups
    mathpix_extracted = cfg.ocr_dir / "mmd_extracted"

    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Walk all visual_content blocks
    todo = []
    for kind, sid, idx, scope, vc in _walk_for_visual_items(per_sub_dir, solutions_dir):
        ref_key = f"{kind}:{sid}:{idx}:{scope}"
        if not args.force and manifest.get(ref_key, {}).get("status") == "ok":
            continue
        todo.append((ref_key, kind, sid, idx, scope, vc))

    if not todo:
        print("Nothing to do (all images already in manifest with status=ok). Use --force to redo.")
        return 0

    # Classify by route
    copy_jobs = [x for x in todo if x[5].get("source_image_ref")]
    gen_jobs = [x for x in todo if x[5].get("image_generation_needed") and not x[5].get("source_image_ref")]
    # An item with BOTH source_image_ref AND image_generation_needed gets the source copy (existing wins)

    print(f"Stage 10 plan:")
    print(f"  copy from MathPix     : {len(copy_jobs)} items")
    print(f"  generate via codegen  : {len(gen_jobs)} items")
    print(f"  manifest path         : {manifest_path}")

    # Cost gate (codegen is the paid part)
    if gen_jobs:
        est = CostEstimate(
            stage="image_codegen_svg",
            chapter_key=args.chapter,
            item_count=len(gen_jobs),
            inr_estimate=round(len(gen_jobs) * 2.5, 2),
            model=CODEGEN_MODEL,
            thinking_level=THINKING,
            notes=f"LLM SVG codegen for {len(gen_jobs)} diagrams (sanitizer + cairosvg render + 1 retry)",
        )
        proceed = confirm_spend(est, yes=args.yes, dry_run=args.dry_run)
        if args.dry_run:
            print("\n[dry-run] would generate:")
            for ref_key, _, sid, idx, scope, vc in gen_jobs:
                print(f"  {ref_key}")
                print(f"    desc: {(vc.get('generation_description') or '')[:140]}")
            print("\n[dry-run] would copy:")
            for ref_key, _, sid, idx, scope, vc in copy_jobs:
                print(f"  {ref_key}  <- {vc.get('source_image_ref')}")
            return 0
        if not proceed:
            print("Aborted at cost gate.")
            return 1

    # --- Copy jobs (free, deduplicated by source_image_ref) ---
    seq_per_sub: dict[str, int] = {}
    seen_source_refs: dict[str, dict] = {}  # source_ref -> {"image_code": ..., "local_path": ...}
    for ref_key, kind, sid, idx, scope, vc in copy_jobs:
        src_ref = vc["source_image_ref"]
        # Dedupe: if we've already copied this source, reuse the existing image_code
        if src_ref in seen_source_refs:
            existing = seen_source_refs[src_ref]
            entry = {
                "status": "ok",
                "route": "source_copy_reuse",
                "image_code": existing["image_code"],
                "source_ref": src_ref,
                "local_path": existing["local_path"],
                "error": None,
            }
            manifest[ref_key] = entry
            safe_write_json(manifest_path, manifest)
            print(f"  reuse  {ref_key:<55}  -> {existing['image_code']} (same source as earlier)")
            continue

        seq = seq_per_sub.get(sid, 0) + 1
        seq_per_sub[sid] = seq
        img_code = _img_code(sid, seq)
        dest = images_dir / f"{img_code}.jpg"
        ok, err = _copy_source_image(src_ref, mathpix_extracted, dest)
        entry = {
            "status": "ok" if ok else "fail",
            "route": "source_copy",
            "image_code": img_code,
            "source_ref": src_ref,
            "local_path": str(dest) if ok else None,
            "error": err if not ok else None,
        }
        manifest[ref_key] = entry
        safe_write_json(manifest_path, manifest)
        if ok:
            seen_source_refs[src_ref] = {"image_code": img_code, "local_path": str(dest)}
        print(f"  copy   {ref_key:<55}  -> {dest.name}  {'OK' if ok else 'FAIL: '+err}")

    # --- Codegen jobs (paid) ---
    # Load line_ranges to get sub names for context grounding
    line_ranges = {}
    if cfg.line_ranges_path.exists():
        line_ranges = json.loads(cfg.line_ranges_path.read_text(encoding="utf-8"))

    total_cost_inr = 0.0
    for ref_key, kind, sid, idx, scope, vc in gen_jobs:
        seq = seq_per_sub.get(sid, 0) + 1
        seq_per_sub[sid] = seq
        img_code = _img_code(sid, seq)
        dest = images_dir / f"{img_code}.png"
        description = vc.get("generation_description") or vc.get("image_description") or ""
        subconcept_name = line_ranges.get(sid, {}).get("name", "")

        attempt_log = []
        success = False
        last_errors = []

        # SVG path emits .svg + .png; switch dest extension
        svg_dest = dest.with_suffix(".svg")
        png_dest = dest.with_suffix(".png")
        for attempt in range(2):
            try:
                svg_raw, provider = _llm_codegen_svg(
                    description, img_code,
                    chapter_name=cfg.chapter_name,
                    subconcept_name=subconcept_name,
                    prev_error="\n".join(last_errors) if attempt > 0 else "",
                )
            except Exception as e:
                attempt_log.append({"attempt": attempt + 1, "stage": "codegen_call", "error": str(e)[:300]})
                last_errors = [f"codegen call failed: {str(e)[:200]}"]
                continue

            ok, errs, sanitized_svg = codegen_svg_and_render(svg_raw, png_dest)
            attempt_log.append({
                "attempt": attempt + 1,
                "provider": provider,
                "svg_snippet": sanitized_svg[:200] + ("..." if len(sanitized_svg) > 200 else ""),
                "errors": errs,
                "ok": ok,
            })
            if ok:
                # Save the SVG source too for inspectability
                svg_dest.write_text(sanitized_svg, encoding="utf-8")
                success = True
                log_spend(
                    CostEstimate(stage="image_codegen_per_item", chapter_key=args.chapter,
                                 item_count=1, inr_estimate=2.5, model=CODEGEN_MODEL,
                                 thinking_level=THINKING, notes=f"svg img {img_code} attempt {attempt+1}"),
                    actual_inr=2.5, status="ok",
                )
                total_cost_inr += 2.5
                break
            last_errors = errs

        dest = png_dest  # keep manifest consistent: always points to PNG
        entry = {
            "status": "ok" if success else "fail",
            "route": "svg_codegen",
            "image_code": img_code,
            "description": description[:300],
            "local_path": str(dest) if success else None,
            "svg_source": str(svg_dest) if success else None,
            "attempts": attempt_log,
            "flag_for_proofread": not success,
        }
        manifest[ref_key] = entry
        safe_write_json(manifest_path, manifest)
        status_str = "OK" if success else "FAIL (flagged for proofread)"
        print(f"  codegen {ref_key:<55} -> {dest.name}  {status_str}")
        if not success:
            print(f"    last errors: {last_errors}")

    # Summary
    ok_count = sum(1 for v in manifest.values() if v.get("status") == "ok")
    fail_count = sum(1 for v in manifest.values() if v.get("status") == "fail")
    print(f"\n{'='*80}")
    print(f"STAGE 10 COMPLETE")
    print(f"  images ok    : {ok_count}")
    print(f"  images fail  : {fail_count} (flagged for proofread phase)")
    print(f"  codegen cost : Rs {total_cost_inr:.2f}")
    print(f"  images dir   : {images_dir}")
    return 0 if fail_count == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
