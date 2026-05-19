"""
stage11_assemble.py - Final dual-format assembly for one mode of one chapter.

Reads:
  cfg.schema_path                 (topology with chapter -> concepts -> subs)
  cfg.line_ranges_path            (sub names + parent_concept)
  cfg.content_per_sub_dir/*.json  (generated content per sub from Stage 7)
  cfg.solutions_dir/*_solutions.json (Stage 9 solutions for SOURCE questions)
  cfg.unified_mapping_path        (source questions per sub)
  cfg.content_dir/images/_manifest.json (rendered/copied image paths)

Writes (sealed dual-format per memory/decision_dual_independent_schemas.md):
  cfg.topology_path  -> {<Chapter>: {<Concept>: [<sub name>...]}}
  cfg.content_path   -> {<Chapter>: {<Concept>: {<Sub>: {Summary, SCQs, SubjectiveTypes, Examples}}}}

Both files use BARE names (no "Concept:"/"Subconcept:" prefix labels).
All validators run at the end; fails block any caller that gates on stage11 output.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.common import chapter_config
from src.common.backup import safe_write_json
from src.common.stage_validators import validate_dual_content, validate_dual_topology


def _difficulty_titlecase(v) -> str:
    if not v:
        return "Medium"
    return str(v).strip().capitalize()


def _extract_options_from_text(qtext: str) -> dict[str, str]:
    """If the SCQ has options embedded as (A) ... (B) ... (C) ... (D) ..., split them out.
    Returns empty dict if no options found (statement_selection / assertion_reason keep
    options inline in the question text; we don't try to over-parse them)."""
    # split on letter markers (A) (B) (C) (D)
    parts = re.split(r"\(([A-D])\)\s*", qtext)
    if len(parts) < 5:  # need at least head + 4 splits
        return {}
    options = {}
    # parts = [head, "A", textA, "B", textB, "C", textC, "D", textD]
    for i in range(1, len(parts) - 1, 2):
        letter = parts[i]
        text = parts[i + 1].strip()
        # Trim trailing whitespace + next-option markers if leaked
        text = re.split(r"\n\s*\(?[A-D]\)?\s+", text)[0].strip()
        if text:
            options[letter] = text
    return options if len(options) >= 2 else {}


def _question_visual_content(item: dict, image_manifest: dict, sid: str) -> dict:
    """Combine question_visual_content / solution_visual_content blocks into the
    front-end Summary.VisualContent / VisualContent shape: {Needed, Content: {code: desc}}.

    Looks up matching images in the manifest by sid + scope."""
    needed = False
    content_map = {}
    for vc_key in ("question_visual_content", "solution_visual_content", "visual_content"):
        vc = item.get(vc_key)
        if not vc:
            continue
        if vc.get("needed") or vc.get("image_generation_needed"):
            needed = True
        # Find matching manifest entries for this sub
        for ref_key, entry in image_manifest.items():
            if not entry or entry.get("status") != "ok":
                continue
            # ref_key like "content:C1.S1:1:solution_visual_content" or "solution:C1.S1:2:solution"
            tag_parts = ref_key.split(":")
            if len(tag_parts) >= 2 and tag_parts[1] == sid:
                desc = vc.get("generation_description") or vc.get("image_description") or ""
                if entry.get("image_code"):
                    content_map[entry["image_code"]] = desc
    out = {"Needed": needed}
    if content_map:
        out["Content"] = content_map
    return out


def _theory_visual_content(content: dict, image_manifest: dict, sid: str) -> dict:
    tvc = content.get("theory_visual_content") or {}
    needed = bool(tvc.get("needed") or tvc.get("image_generation_needed"))
    content_map = {}
    # find any manifest entry with scope=theory under this sid
    for ref_key, entry in image_manifest.items():
        if not entry or entry.get("status") != "ok":
            continue
        tag_parts = ref_key.split(":")
        if len(tag_parts) >= 4 and tag_parts[1] == sid and tag_parts[3] == "theory":
            desc = tvc.get("generation_description") or tvc.get("image_description") or ""
            if entry.get("image_code"):
                content_map[entry["image_code"]] = desc
    out = {"Needed": needed}
    if content_map:
        out["Content"] = content_map
    return out


def _build_scq_record(scq: dict, is_back: bool, image_manifest: dict, sid: str) -> dict:
    """Map our internal SCQ shape to the front-end SCQ record shape."""
    qtext = scq.get("question", "")
    opts = _extract_options_from_text(qtext)
    return {
        "isBackExercise": is_back,
        "Difficulty": _difficulty_titlecase(scq.get("difficulty")),
        "scqFormat": scq.get("scq_format", "standard"),
        "Question": qtext,
        "Options": opts,
        "Correct Option": scq.get("answer", ""),
        "Solution": scq.get("solution", ""),
        "VisualContent": _question_visual_content(scq, image_manifest, sid),
    }


def _build_subjective_record(subj: dict, is_back: bool, image_manifest: dict, sid: str) -> dict:
    return {
        "isBackExercise": is_back,
        "Difficulty": _difficulty_titlecase(subj.get("difficulty")),
        "answerFormat": subj.get("answer_format", "descriptive"),
        "Question": subj.get("question", ""),
        "Answer": subj.get("answer", ""),
        "Solution": subj.get("solution", ""),
        "VisualContent": _question_visual_content(subj, image_manifest, sid),
    }


def _build_example_record(ex: dict, is_solved: bool, image_manifest: dict, sid: str) -> dict:
    return {
        "isSolvedExample": is_solved,
        "Question": ex.get("question", ""),
        "Solution": ex.get("solution", ""),
        "VisualContent": _question_visual_content(ex, image_manifest, sid),
    }


def _classify_source_to_bucket(source_q: dict, source_sol: dict | None) -> str:
    """Given a source NCERT question + its generated solution, decide which front-end
    bucket it belongs in: 'scq' (has 4 options), 'subjective', or 'example'."""
    # If options dict is populated from the source extractor, it's an SCQ
    if source_q.get("options") and len(source_q.get("options", {})) >= 2:
        return "scq"
    # The solution generator marked answer_format; respect that
    if source_sol and source_sol.get("answer_format") in ("numerical", "diagram", "descriptive"):
        return "subjective"
    # Default for back exercises + intext questions: subjective
    return "subjective"


def assemble_chapter(cfg) -> tuple[dict, dict, list[str]]:
    """Returns (topology_dict, content_dict, warnings)."""
    warnings: list[str] = []

    schema = json.loads(cfg.schema_path.read_text(encoding="utf-8"))
    line_ranges = json.loads(cfg.line_ranges_path.read_text(encoding="utf-8"))
    unified = json.loads(cfg.unified_mapping_path.read_text(encoding="utf-8"))

    image_manifest = {}
    manifest_path = cfg.content_dir / "images" / "_manifest.json"
    if manifest_path.exists():
        image_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Load all per-sub content
    per_sub_content = {}
    for f in sorted(cfg.content_per_sub_dir.glob("*.json")):
        sid = f.stem
        d = json.loads(f.read_text(encoding="utf-8"))
        per_sub_content[sid] = d.get("content", d)

    # Load all solutions for source questions
    source_solutions: dict[str, dict[str, dict]] = {}  # sid -> qid -> solution_obj
    for f in sorted(cfg.solutions_dir.glob("*_solutions.json")):
        sid = f.stem.replace("_solutions", "")
        d = json.loads(f.read_text(encoding="utf-8"))
        sols_by_qid = {}
        for s in d.get("solutions", []):
            qid = s.get("question_id") or s.get("qid")
            if qid:
                sols_by_qid[qid] = s
        source_solutions[sid] = sols_by_qid

    # --- topology.json (bare-names) ---
    # schema is already in shape {chapter: {concept: [sub names]}} from the regex extractor
    topology = schema

    # --- content.json (bare-names with full payload) ---
    chapter_name = next(iter(topology))
    content_root: dict = {chapter_name: {}}

    for concept_name, sub_names in topology[chapter_name].items():
        concept_block = {}
        for sub_name in sub_names:
            # Find the sid for this sub_name
            sid = None
            for s_id, lr_data in line_ranges.items():
                if lr_data.get("name") == sub_name:
                    sid = s_id
                    break
            if not sid:
                warnings.append(f"no sid found for sub '{sub_name}' under concept '{concept_name}'")
                concept_block[sub_name] = {"_error": "no content for this sub"}
                continue

            content = per_sub_content.get(sid, {})
            if not content:
                warnings.append(f"no per-sub content for {sid}")

            unified_sub = unified.get(sid, {})

            # SCQs: generated (from content.scqs) + source SCQs from unified
            scqs_dict = {}
            n = 1
            for q in content.get("scqs", []):
                scqs_dict[f"Question {n}"] = _build_scq_record(q, is_back=False, image_manifest=image_manifest, sid=sid)
                n += 1
            # Source SCQs from unified back_exercises and intext_questions
            for src in unified_sub.get("back_exercises", []) + unified_sub.get("intext_questions", []):
                bucket = _classify_source_to_bucket(src, source_solutions.get(sid, {}).get(src.get("id")))
                if bucket != "scq":
                    continue
                sol = source_solutions.get(sid, {}).get(src.get("id"), {})
                merged = {
                    "scq_format": "standard",
                    "difficulty": src.get("difficulty", sol.get("difficulty", "Medium")),
                    "question": src.get("question_text", ""),
                    "answer": src.get("answer", ""),
                    "solution": sol.get("solution", ""),
                    "question_visual_content": sol.get("visual_content", {}),
                }
                # Re-glue options into question text if they're separate
                opts = src.get("options", {})
                if opts and not re.search(r"\([A-D]\)", merged["question"]):
                    merged["question"] += "\n" + "\n".join(f"({k}) {v}" for k, v in sorted(opts.items()))
                scqs_dict[f"Question {n}"] = _build_scq_record(merged, is_back=src.get("isBackExercise", True),
                                                               image_manifest=image_manifest, sid=sid)
                n += 1

            # Subjective: generated + source-subjective
            subj_dict = {}
            n = 1
            for q in content.get("subjective", []):
                subj_dict[f"Question {n}"] = _build_subjective_record(q, is_back=False, image_manifest=image_manifest, sid=sid)
                n += 1
            for src in unified_sub.get("back_exercises", []) + unified_sub.get("intext_questions", []):
                bucket = _classify_source_to_bucket(src, source_solutions.get(sid, {}).get(src.get("id")))
                if bucket != "subjective":
                    continue
                sol = source_solutions.get(sid, {}).get(src.get("id"), {})
                merged = {
                    "answer_format": sol.get("answer_format", "descriptive"),
                    "difficulty": src.get("difficulty", "Medium"),
                    "question": src.get("question_text", ""),
                    "answer": sol.get("answer", src.get("answer", "")),
                    "solution": sol.get("solution", ""),
                    "solution_visual_content": sol.get("visual_content", {}),
                }
                subj_dict[f"Question {n}"] = _build_subjective_record(merged, is_back=src.get("isBackExercise", True),
                                                                      image_manifest=image_manifest, sid=sid)
                n += 1

            # Examples: generated + source solved examples
            examples_dict = {}
            n = 1
            for ex in content.get("examples", []):
                examples_dict[f"Example {n}"] = _build_example_record(ex, is_solved=False, image_manifest=image_manifest, sid=sid)
                n += 1
            for ex in unified_sub.get("solved_examples", []):
                merged = {
                    "question": ex.get("question", ""),
                    "solution": "",  # NCERT solved examples - solution carried in the source content
                    "visual_content": {},
                }
                examples_dict[f"Example {n}"] = _build_example_record(merged, is_solved=True, image_manifest=image_manifest, sid=sid)
                n += 1

            sub_payload = {
                "Summary": {
                    "Theory": content.get("theory", ""),
                    "VisualContent": _theory_visual_content(content, image_manifest, sid),
                },
                "SCQs": scqs_dict,
                "SubjectiveTypes": subj_dict,
                "Examples": examples_dict,
            }
            concept_block[sub_name] = sub_payload

        content_root[chapter_name][concept_name] = concept_block

    return topology, content_root, warnings


def main():
    p = argparse.ArgumentParser(description="Stage 11 - final dual-format assembly (FREE)")
    p.add_argument("--chapter", required=True, help="Chapter key from chapter_config")
    args = p.parse_args()

    cfg = chapter_config.load(args.chapter)

    print(f"\n=== Stage 11 assembly for {args.chapter} ===")
    print(f"  topology output : {cfg.topology_path}")
    print(f"  content output  : {cfg.content_path}")

    topology, content_root, warnings = assemble_chapter(cfg)

    safe_write_json(cfg.topology_path, topology)
    safe_write_json(cfg.content_path, content_root)

    # Summary stats
    chapter = next(iter(content_root))
    n_concepts = len(content_root[chapter])
    n_subs = sum(len(c) for c in content_root[chapter].values())
    n_scqs = 0
    n_subj = 0
    n_ex = 0
    for concept in content_root[chapter].values():
        for sub in concept.values():
            n_scqs += len(sub.get("SCQs", {}))
            n_subj += len(sub.get("SubjectiveTypes", {}))
            n_ex += len(sub.get("Examples", {}))

    print(f"\n  Assembly stats:")
    print(f"    chapter      : {chapter}")
    print(f"    concepts     : {n_concepts}")
    print(f"    subconcepts  : {n_subs}")
    print(f"    SCQs         : {n_scqs}")
    print(f"    Subjective   : {n_subj}")
    print(f"    Examples     : {n_ex}")
    print(f"    total items  : {n_scqs + n_subj + n_ex}")
    if warnings:
        print(f"  warnings ({len(warnings)}):")
        for w in warnings:
            print(f"    - {w}")

    # Run validators
    print(f"\n--- VALIDATORS ---")
    v1 = validate_dual_topology(cfg.topology_path, expected_chapter_name=chapter)
    print(v1.report())
    v2 = validate_dual_content(cfg.content_path, expected_chapter_name=chapter, require_subjectivetypes=False)
    print(v2.report())

    if not v1.ok or not v2.ok:
        print("\nVALIDATOR FAIL - downstream is blocked until output is fixed")
        return 1

    print(f"\nSAVED:")
    print(f"  {cfg.topology_path}")
    print(f"  {cfg.content_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
