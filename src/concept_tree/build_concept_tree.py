"""
build_concept_tree.py - Adds NCERT and Competitive nodes to acadza_concept_tree.

Reads:
  - data/reference/acadza_concept_tree_jee_neet_reference.json   (existing JEE/NEET reference)
  - experiments/03_topology_generation/competitive/master_schema_final.json

Writes:
  - experiments/06_concept_tree/acadza_concept_tree_extended.json
    The reference tree extended with two new top-level keys:
       "NCERT"      : { "Class 10": { "Physics": { <chapter>: { <concept>: [<subconcept>...] } } } }
       "Competitive": { "Class 10": { "Physics": { <chapter>: { <concept>: [<subconcept>...] } } } }

    Format mirrors the JEE/NEET shape (Subject -> Chapter -> Concept -> [subconcept names])
    with an extra Class layer because school content is class-stratified.

Composition rules:
  NCERT node:        only NCERT-source concepts. Subconcepts under each = overlap + ncert_only.
                     This is what a Class 10 board student sees.
  Competitive node:  ALL concepts (NCERT-source + competitive-only). Subconcepts under each =
                     overlap + ncert_only + competitive_only. Inclusive superset.

Names are taken verbatim from master_schema_final.json so the codes/titles match the
master + content schemas already in the platform.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(r"D:/ACADZA_WORK/8-9-10th PIPELINE")
REFERENCE = ROOT / "data/reference/acadza_concept_tree_jee_neet_reference.json"
MASTER = ROOT / "experiments/03_topology_generation/competitive/master_schema_final.json"
OUT = ROOT / "experiments/06_concept_tree/acadza_concept_tree_extended.json"

CLASS_LEVEL = "Class 10"
SUBJECT = "Physics"


def _safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


def build_chapter_tree(master: dict, mode: str) -> dict:
    """
    mode = 'ncert'       -> include only NCERT-source concepts; subs include overlap + ncert_only
    mode = 'competitive' -> include all concepts; subs include overlap + ncert_only + competitive_only.
                            Concepts with identical names (e.g. NCRT_C3 'Refraction Of Light' vs
                            COMP_C21 'Refraction Of Light') are merged - subs from the NCERT-source
                            concept come first, then unique comp subs are appended.
    """
    chapter_name = master["chapter_name"]
    concepts_out: dict[str, list[str]] = {}

    def _key(name: str) -> str:
        return name.strip().lower()

    # Track insertion order separately so we preserve the master schema's concept ordering
    order: list[str] = []
    seen_keys: dict[str, str] = {}  # normalized key -> canonical (first-seen) name

    for concept in master["concepts"]:
        if mode == "ncert" and concept["source"] != "ncert":
            continue

        subs_for_mode: list[str] = []
        for sub in concept["subconcepts"]:
            cat = sub.get("category")
            if mode == "ncert":
                if cat in ("overlap", "ncert_only"):
                    subs_for_mode.append(sub["name"])
            else:
                subs_for_mode.append(sub["name"])

        if not subs_for_mode:
            continue

        ckey = _key(concept["name"])
        if ckey in seen_keys:
            # Merge into the existing concept entry, preserving order, dropping duplicates
            canonical_name = seen_keys[ckey]
            existing = concepts_out[canonical_name]
            existing_keys = {_key(s) for s in existing}
            for s in subs_for_mode:
                if _key(s) not in existing_keys:
                    existing.append(s)
                    existing_keys.add(_key(s))
        else:
            seen_keys[ckey] = concept["name"]
            concepts_out[concept["name"]] = subs_for_mode
            order.append(concept["name"])

    return {chapter_name: concepts_out}


def main() -> None:
    if not REFERENCE.exists():
        raise SystemExit(f"Reference tree missing: {REFERENCE}")
    if not MASTER.exists():
        raise SystemExit(f"Master schema missing: {MASTER}")

    _safe_print("[concept_tree] loading reference + master")
    tree = json.loads(REFERENCE.read_text("utf-8"))
    master = json.loads(MASTER.read_text("utf-8"))

    ncert_chapters = build_chapter_tree(master, mode="ncert")
    comp_chapters = build_chapter_tree(master, mode="competitive")

    tree["NCERT"] = {
        CLASS_LEVEL: {
            SUBJECT: ncert_chapters,
        },
    }
    tree["Competitive"] = {
        CLASS_LEVEL: {
            SUBJECT: comp_chapters,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(tree, indent=2, ensure_ascii=False), "utf-8")

    # Quick stats
    def count(node: dict, depth: int = 0) -> tuple[int, int]:
        """returns (concepts, subconcepts) under one chapter dict"""
        c = len(node)
        s = sum(len(v) for v in node.values())
        return c, s

    for ch_name, ch_node in ncert_chapters.items():
        nc, ns = count(ch_node)
        _safe_print(f"[concept_tree] NCERT       {CLASS_LEVEL} > {SUBJECT} > '{ch_name}': {nc} concepts, {ns} subconcepts")
    for ch_name, ch_node in comp_chapters.items():
        cc, cs = count(ch_node)
        _safe_print(f"[concept_tree] Competitive {CLASS_LEVEL} > {SUBJECT} > '{ch_name}': {cc} concepts, {cs} subconcepts")

    _safe_print(f"[concept_tree] wrote {OUT}  ({OUT.stat().st_size/1024:.1f} KB)")
    _safe_print(f"[concept_tree] top-level keys now: {list(tree.keys())}")


if __name__ == "__main__":
    main()
