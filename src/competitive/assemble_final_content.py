"""
Step 12: Assemble final Content Schema for Ch1 Light (NCERT Ch9).

Produces: content_schema.json — full payload one level deeper than master_schema.
For overlap subconcepts, theory is a REFERENCE POINTER to NCERT theory (not copied).
This ensures future NCERT theory updates propagate to competitive view automatically.

Inputs (5 ingredients):
  1. ch09_final_content.json      → NCERT theory + 128 Q/Examples (complete)
  2. comp_schema_sealed.json       → Competitive topology
  3. comp_mapping_verified.json    → NCERT↔Comp overlap categorization
  4. comp_questions_mapped.json    → 323 questions with subconcept mapping
  5. comp_theory/COMP_*.json       → 12 competitive-only theory files

Outputs:
  - master_schema.json (updated with full stats)
  - content_schema.json (full production payload)

Per-question flag rules (memory):
  - Tier 1 (Master Boards):   isNCERT=true,  isFoundation=true
  - Tier 2 (Master NCERT):    isNCERT=true,  isFoundation=true
  - Tier 3 (Foundation):      isNCERT=false, isFoundation=true
  - Tier 4 (Foundation+):     isNCERT=false, isFoundation=true
  - NCERT extracted:          isNCERT=true,  isFoundation=false
  - NCERT generated:          isNCERT=true,  isFoundation=false
"""
import json, os, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')

NCERT_CONTENT_PATH = os.path.join(BASE, 'experiments/05_content_generation/ch09_final_content.json')
COMP_SCHEMA_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_schema_sealed.json')
COMP_MAPPING_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_mapping_verified.json')
COMP_QUESTIONS_MAPPED_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_questions_mapped.json')
COMP_QUESTIONS_CLEANED_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_questions_cleaned.json')
COMP_THEORY_DIR = os.path.join(BASE, 'experiments/05_content_generation/comp_theory')
MASTER_SCHEMA_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/master_schema.json')

OUT_MASTER_PATH = os.path.join(BASE, 'experiments/03_topology_generation/competitive/master_schema_final.json')
OUT_CONTENT_PATH = os.path.join(BASE, 'experiments/05_content_generation/content_schema_final.json')

# NCERT concept ordering (source of truth)
NCERT_CONCEPT_ORDER = [
    ('NCRT_C1', 'Basics of Light and Reflection'),
    ('NCRT_C2', 'Spherical Mirrors'),
    ('NCRT_C3', 'Refraction Of Light'),
]

# Order of 6 competitive-only concepts after NCERT
COMP_ONLY_CONCEPT_ORDER = [
    ('COMP_C19', "Newton'S Formula"),
    ('COMP_C20', 'Identification Of Mirror By The Size And Nature Of The Image'),
    ('COMP_C23', 'Refraction Through A Rectangular Glass Slab'),  # only comp_only subs (TIR, Critical Angle)
    ('COMP_C29', 'Magnification'),  # Lens family advanced
    ('COMP_C31', 'Interference, Diffraction And Polarisation Of Light'),
    ('COMP_C21', 'Refraction Of Light'),  # only Atmospheric Refraction comp_only
]


def tier_to_flags(tier: int) -> tuple:
    """Map exercise tier -> (isNCERT, isFoundation) per memory rule."""
    if tier in (1, 2):
        return True, True
    if tier in (3, 4):
        return False, True
    return True, False  # default NCERT


def tier_name(tier: int) -> str:
    return {1: 'Master Boards', 2: 'Master NCERT', 3: 'Foundation Builder', 4: 'Foundation Builder+'}.get(tier, 'Unknown')


def load_all():
    with open(NCERT_CONTENT_PATH, 'r', encoding='utf-8') as f:
        ncert_content = json.load(f)
    with open(COMP_SCHEMA_PATH, 'r', encoding='utf-8') as f:
        comp_schema = json.load(f)
    with open(COMP_MAPPING_PATH, 'r', encoding='utf-8') as f:
        comp_mapping = json.load(f)
    with open(COMP_QUESTIONS_MAPPED_PATH, 'r', encoding='utf-8') as f:
        q_mapped = json.load(f)
    with open(COMP_QUESTIONS_CLEANED_PATH, 'r', encoding='utf-8') as f:
        q_cleaned = json.load(f)

    # Load all competitive theory files
    comp_theories = {}
    if os.path.exists(COMP_THEORY_DIR):
        for fname in os.listdir(COMP_THEORY_DIR):
            if fname.startswith('COMP_') and fname.endswith('.json'):
                code = fname.replace('.json', '')
                with open(os.path.join(COMP_THEORY_DIR, fname), 'r', encoding='utf-8') as f:
                    comp_theories[code] = json.load(f)

    return ncert_content, comp_schema, comp_mapping, q_mapped, q_cleaned, comp_theories


def build_ncert_subconcept_index(ncert_content):
    """Return dict: NCERT subconcept name -> {concept_name, SCQs, SubjectiveTypes, Examples, Theory}"""
    idx = {}
    for ck, subs in ncert_content.items():
        concept_name = ck.replace('Concept: ', '')
        for sk, data in subs.items():
            sub_name = sk.replace('Subconcept: ', '')
            idx[sub_name] = {
                'concept_name': concept_name,
                'concept_key': ck,
                'sub_key': sk,
                'data': data,
            }
    return idx


def build_comp_subconcept_index(comp_schema):
    """Return dict: COMP_Cx.Sy -> {name, parent_name, parent_code, tier, is_connecting_topic}"""
    idx = {}
    for c in comp_schema['concepts']:
        for s in c['subconcepts']:
            idx[s['id']] = {
                'name': s['name'],
                'parent_name': c['name'],
                'parent_code': c['id'],
                'tier': s.get('tier', 'thin'),
                'is_connecting_topic': s.get('is_connecting_topic', False),
                'parent_is_connecting_topic': c.get('is_connecting_topic', False),
            }
    return idx


def build_ncert_to_comp_overlaps(comp_mapping, ncert_subconcept_idx):
    """Build map: NCERT subconcept name -> [list of COMP codes that overlap]"""
    overlaps = defaultdict(list)
    for m in comp_mapping['mappings']:
        if m['category'] == 'overlap':
            ncert_name = m['ncert_name']
            if ncert_name in ncert_subconcept_idx:
                overlaps[ncert_name].append(m['comp_code'])
    return overlaps


def build_question_sequence(q_mapped, q_cleaned):
    """Assign proper IDs and group questions by subconcept code.
    ID format: {comp_code}_EX{tier}_Q{seq}  e.g., COMP_C5.S1_EX1_Q3
    """
    grouped = defaultdict(list)
    seq_per_group = defaultdict(int)  # (code, tier) -> seq counter

    for m in q_mapped['mappings']:
        q_idx = m['q_index']
        if q_idx is None or q_idx >= len(q_cleaned):
            continue
        q = q_cleaned[q_idx]
        comp_code = m['comp_code']
        tier = q.get('exercise_tier') or m.get('exercise_tier')
        if tier is None:
            continue

        seq_key = (comp_code, tier)
        seq_per_group[seq_key] += 1
        seq = seq_per_group[seq_key]
        qid = f"{comp_code}_EX{tier}_Q{seq}"

        is_ncert, is_foundation = tier_to_flags(tier)

        if q.get('type') == 'passage':
            # Expand passage sub-questions as individual questions under the same subconcept
            sub_list = q.get('sub_questions', [])
            passage_text = q.get('passage_text', '')
            for sub_i, sq in enumerate(sub_list):
                seq_per_group[seq_key] += 1
                sub_seq = seq_per_group[seq_key] - 1  # already incremented above; correct sequence
                sub_qid = f"{comp_code}_EX{tier}_Q{seq + sub_i}"
                entry = {
                    'id': sub_qid,
                    'q_index': q_idx,
                    'sub_index': sub_i,
                    'is_passage_sub': True,
                    'passage_text': passage_text,
                    'type': sq.get('type'),
                    'scq_format': sq.get('scq_format'),
                    'answer_format': sq.get('answer_format'),
                    'question_text': sq.get('question_text'),
                    'options': sq.get('options'),
                    'answer_key': sq.get('answer_key'),
                    'solution_text': sq.get('solution_text'),
                    'exercise_tier': tier,
                    'exercise_name': tier_name(tier),
                    'foundation_type': q.get('foundation_type'),
                    'isNCERT': is_ncert,
                    'isFoundation': is_foundation,
                    'Difficulty': m.get('difficulty', 'Medium'),
                    'mapped_comp_code': comp_code,
                    'comp_code_match_category': m.get('master_schema_category'),
                }
                grouped[comp_code].append(entry)
            # Adjust sequence counter (we incremented once per sub_i explicitly)
            seq_per_group[seq_key] += len(sub_list) - 1
        else:
            entry = {
                'id': qid,
                'q_index': q_idx,
                'is_passage_sub': False,
                'type': q.get('type'),
                'scq_format': q.get('scq_format'),
                'answer_format': q.get('answer_format'),
                'question_text': q.get('question_text'),
                'options': q.get('options'),
                'answer_key': q.get('answer_key'),
                'solution_text': q.get('solution_text'),
                'exercise_tier': tier,
                'exercise_name': tier_name(tier),
                'foundation_type': q.get('foundation_type'),
                'isNCERT': is_ncert,
                'isFoundation': is_foundation,
                'Difficulty': m.get('difficulty', 'Medium'),
                'mapped_comp_code': comp_code,
                'comp_code_match_category': m.get('master_schema_category'),
            }
            grouped[comp_code].append(entry)
    return grouped


def extract_ncert_questions(ncert_sub_data, ncert_concept_code, ncert_sub_code):
    """Extract questions from NCERT subconcept data, assign IDs, tag flags."""
    questions = []
    examples = []

    seq = 0
    for section_key in ('SCQs', 'SubjectiveTypes'):
        for _, item in ncert_sub_data.get(section_key, {}).items():
            seq += 1
            qid = f"{ncert_sub_code}_NCRT_Q{seq}"
            is_back = bool(item.get('isBackExercise', False))
            is_intext = bool(item.get('isInTextQuestion', False))
            is_ncert_source = bool(item.get('isNCERT', True))
            is_foundation = bool(item.get('isFoundation', False))
            questions.append({
                'id': qid,
                'type': 'scq' if section_key == 'SCQs' else 'subjective',
                'scq_format': item.get('scq_format'),
                'answer_format': item.get('answer_format'),
                'isBackExercise': is_back,
                'isInTextQuestion': is_intext,
                'isNCERT': is_ncert_source,
                'isFoundation': is_foundation,
                'foundation_type': item.get('foundation_type'),
                'Difficulty': item.get('Difficulty', 'Medium'),
                'question_text': item.get('Question'),
                'answer_key': item.get('Answer'),
                'solution_text': item.get('Solution'),
                'VisualContent': item.get('VisualContent'),
                '_source': item.get('_source', 'ncert'),
            })

    seq = 0
    for _, item in ncert_sub_data.get('Examples', {}).items():
        seq += 1
        eid = f"{ncert_sub_code}_NCRT_EX{seq}"
        examples.append({
            'id': eid,
            'isSolvedExample': True,
            'isFromNCERT': item.get('isFromNCERT', False),
            'isNCERT': item.get('isNCERT', True),
            'isFoundation': item.get('isFoundation', False),
            'Difficulty': item.get('Difficulty', 'Medium'),
            'question_text': item.get('Question'),
            'solution_text': item.get('Solution'),
            'VisualContent': item.get('VisualContent'),
            '_source': item.get('_source', 'ncert'),
        })
    return questions, examples


def assemble():
    ncert_content, comp_schema, comp_mapping, q_mapped, q_cleaned_wrap, comp_theories = load_all()
    q_cleaned = q_cleaned_wrap['cleaned']

    ncert_sub_idx = build_ncert_subconcept_index(ncert_content)
    comp_sub_idx = build_comp_subconcept_index(comp_schema)
    overlaps_by_ncert_sub = build_ncert_to_comp_overlaps(comp_mapping, ncert_sub_idx)
    comp_questions_by_sub = build_question_sequence(q_mapped, q_cleaned)

    # ---------------- MASTER SCHEMA ----------------
    master = {
        '_description': 'Master schema — structural index for Ch1 Light (NCERT Ch9 + Competitive Ch1).',
        '_version': 'master_final_v1',
        'chapter_name': 'Light - Reflection and Refraction',
        'class_level': '10',
        'subject': 'Physics',
        'ncert_chapter_number': 9,
        'competitive_chapter_number': 1,
        'concepts': [],
        'stats': {},
    }

    # Build NCERT concepts first (with overlap mapping noted)
    for ncert_ck, ncert_concept_name in NCERT_CONCEPT_ORDER:
        concept_entry = {
            'code': ncert_ck,
            'name': ncert_concept_name,
            'source': 'ncert',
            'subconcepts': [],
        }
        # Get NCERT subs for this concept
        for sub_name, sub_meta in ncert_sub_idx.items():
            if sub_meta['concept_name'] != ncert_concept_name:
                continue
            # Determine NCERT sub code (NCRT_Cx.Sy)
            # NCERT subconcept codes aren't directly in content, derive from position
            pass  # will fix below via ordered iteration

        master['concepts'].append(concept_entry)

    # Rebuild with proper codes using comp_mapping's ncert_code references
    # The mapping file has NCRT_Cx.Sy codes — use them
    ncert_code_to_name = {}
    for m in comp_mapping['mappings']:
        if m.get('ncert_code') and m.get('ncert_name'):
            ncert_code_to_name[m['ncert_code']] = m['ncert_name']
    for n in comp_mapping.get('ncert_only', []):
        if n.get('ncert_code') and n.get('ncert_name'):
            ncert_code_to_name[n['ncert_code']] = n['ncert_name']

    # Rebuild master concepts cleanly
    master['concepts'] = []

    # Collect NCERT sub codes per concept by parsing the code structure NCRT_Cx.Sy
    ncert_subs_by_concept = defaultdict(list)
    for code, name in ncert_code_to_name.items():
        concept_part = code.split('.')[0]  # NCRT_C1
        ncert_subs_by_concept[concept_part].append((code, name))
    # Sort within each concept by subconcept number
    for k in ncert_subs_by_concept:
        ncert_subs_by_concept[k].sort(key=lambda x: int(x[0].split('.S')[-1]))

    # NCERT concept entries
    for ncert_ck, ncert_concept_name in NCERT_CONCEPT_ORDER:
        concept_entry = {
            'code': ncert_ck,
            'name': ncert_concept_name,
            'source': 'ncert',
            'subconcepts': [],
        }
        for sub_code, sub_name in ncert_subs_by_concept.get(ncert_ck, []):
            comp_overlaps = overlaps_by_ncert_sub.get(sub_name, [])
            is_ncert_only = any(n['ncert_code'] == sub_code for n in comp_mapping.get('ncert_only', []))

            sub_data = ncert_sub_idx.get(sub_name, {}).get('data', {})
            ncert_q_count = len(sub_data.get('SCQs', {})) + len(sub_data.get('SubjectiveTypes', {}))
            ncert_ex_count = len(sub_data.get('Examples', {}))
            # Count competitive questions that mapped here
            comp_q_count = sum(len(comp_questions_by_sub.get(cc, [])) for cc in comp_overlaps)

            concept_entry['subconcepts'].append({
                'code': sub_code,
                'name': sub_name,
                'source': 'ncert',
                'category': 'ncert_only' if is_ncert_only else ('overlap' if comp_overlaps else 'ncert_only'),
                'competitive_overlap_codes': comp_overlaps,
                'has_ncert_content': True,
                'has_competitive_content': bool(comp_overlaps),
                'stats': {
                    'ncert_questions': ncert_q_count,
                    'ncert_examples': ncert_ex_count,
                    'competitive_questions_inherited': comp_q_count,
                }
            })
        master['concepts'].append(concept_entry)

    # Competitive-only concepts (add after NCERT)
    comp_only_subs_by_parent = defaultdict(list)
    for m in comp_mapping['mappings']:
        if m['category'] == 'competitive_only':
            code = m['comp_code']
            sub_meta = comp_sub_idx.get(code, {})
            parent_code = sub_meta.get('parent_code')
            if parent_code:
                comp_only_subs_by_parent[parent_code].append(code)

    for parent_code, parent_name in COMP_ONLY_CONCEPT_ORDER:
        if parent_code not in comp_only_subs_by_parent:
            continue
        concept_entry = {
            'code': parent_code,
            'name': parent_name,
            'source': 'competitive_only',
            'is_connecting_topic': comp_sub_idx.get(comp_only_subs_by_parent[parent_code][0], {}).get('parent_is_connecting_topic', False),
            'subconcepts': [],
        }
        for code in comp_only_subs_by_parent[parent_code]:
            sub_meta = comp_sub_idx[code]
            comp_q_count = len(comp_questions_by_sub.get(code, []))
            has_theory = code in comp_theories
            concept_entry['subconcepts'].append({
                'code': code,
                'name': sub_meta['name'],
                'source': 'competitive_only',
                'category': 'competitive_only',
                'is_connecting_topic': sub_meta['is_connecting_topic'],
                'tier': sub_meta['tier'],
                'has_ncert_content': False,
                'has_competitive_content': True,
                'stats': {
                    'competitive_questions': comp_q_count,
                    'has_competitive_theory': has_theory,
                }
            })
        master['concepts'].append(concept_entry)

    # Master stats
    total_subs = sum(len(c['subconcepts']) for c in master['concepts'])
    total_ncert_q = sum(s['stats'].get('ncert_questions', 0) for c in master['concepts'] for s in c['subconcepts'])
    total_ncert_ex = sum(s['stats'].get('ncert_examples', 0) for c in master['concepts'] for s in c['subconcepts'])
    total_comp_q = sum(s['stats'].get('competitive_questions_inherited', 0) + s['stats'].get('competitive_questions', 0) for c in master['concepts'] for s in c['subconcepts'])
    master['stats'] = {
        'total_concepts': len(master['concepts']),
        'total_subconcepts': total_subs,
        'ncert_concepts': 3,
        'competitive_only_concepts': len(master['concepts']) - 3,
        'total_ncert_questions': total_ncert_q,
        'total_ncert_examples': total_ncert_ex,
        'total_competitive_questions': total_comp_q,
        'total_questions_all': total_ncert_q + total_comp_q,
    }

    with open(OUT_MASTER_PATH, 'w', encoding='utf-8') as f:
        json.dump(master, f, indent=2, ensure_ascii=False)

    # ---------------- CONTENT SCHEMA ----------------
    content = {
        '_description': 'Content schema — full production payload for Ch1 Light.',
        '_version': 'content_final_v1',
        '_theory_inheritance': 'For overlap subconcepts, competitive_theory_source points to NCERT subconcept code. Resolve at read time.',
        'chapter_name': 'Light - Reflection and Refraction',
        'class_level': '10',
        'subject': 'Physics',
        'subconcepts': {},
    }

    # NCERT subconcepts (with inherited competitive questions where overlap)
    for concept in master['concepts']:
        if concept['source'] != 'ncert':
            continue
        ncert_ck = concept['code']
        for sub in concept['subconcepts']:
            ncert_sub_code = sub['code']
            ncert_sub_name = sub['name']
            ncert_sub_data = ncert_sub_idx.get(ncert_sub_name, {}).get('data', {})

            # NCERT questions + examples
            ncert_questions, ncert_examples = extract_ncert_questions(ncert_sub_data, ncert_ck, ncert_sub_code)

            # Inherited competitive questions (from all overlapping comp codes)
            comp_questions = []
            for comp_code in sub.get('competitive_overlap_codes', []):
                for q in comp_questions_by_sub.get(comp_code, []):
                    qc = dict(q)
                    qc['id'] = f"{ncert_sub_code}__INHERIT__{q['id']}"
                    comp_questions.append(qc)

            # Theory: NCERT's own. For reference only (not pointer — this IS the source).
            theory = ncert_sub_data.get('Summary', {}).get('Theory', '')
            visual = ncert_sub_data.get('Summary', {}).get('VisualContent', {})

            content['subconcepts'][ncert_sub_code] = {
                'subconcept_code': ncert_sub_code,
                'subconcept_name': ncert_sub_name,
                'parent_concept_code': ncert_ck,
                'parent_concept_name': concept['name'],
                'source': 'ncert',
                'category': sub['category'],
                'isNCERT': True,
                'isFoundation': sub['has_competitive_content'],
                'theory': theory,
                'theory_VisualContent': visual,
                'competitive_theory_source': None,  # not needed — theory is stored here directly
                'ncert_questions': ncert_questions,
                'ncert_examples': ncert_examples,
                'competitive_questions': comp_questions,
                'overlap_source_codes': sub.get('competitive_overlap_codes', []),
            }

    # Competitive-only subconcepts
    for concept in master['concepts']:
        if concept['source'] != 'competitive_only':
            continue
        comp_parent_code = concept['code']
        for sub in concept['subconcepts']:
            sub_code = sub['code']
            sub_meta = comp_sub_idx[sub_code]
            theory_obj = comp_theories.get(sub_code, {})

            comp_questions = list(comp_questions_by_sub.get(sub_code, []))

            content['subconcepts'][sub_code] = {
                'subconcept_code': sub_code,
                'subconcept_name': sub_meta['name'],
                'parent_concept_code': comp_parent_code,
                'parent_concept_name': concept['name'],
                'source': 'competitive_only',
                'category': 'competitive_only',
                'is_connecting_topic': sub_meta['is_connecting_topic'],
                'tier': sub_meta['tier'],
                'isNCERT': False,
                'isFoundation': True,
                'theory': theory_obj.get('theory'),
                'key_formulas': theory_obj.get('key_formulas', []),
                'theory_VisualContent': theory_obj.get('VisualContent'),
                'competitive_theory_source': None,  # theory is native here
                'ncert_questions': [],
                'ncert_examples': [],
                'competitive_questions': comp_questions,
                'overlap_source_codes': [],
            }

    with open(OUT_CONTENT_PATH, 'w', encoding='utf-8') as f:
        json.dump(content, f, indent=2, ensure_ascii=False)

    # Print summary
    print('=' * 70)
    print('ASSEMBLY COMPLETE')
    print('=' * 70)
    print(f"\nMASTER SCHEMA: {OUT_MASTER_PATH}")
    for k, v in master['stats'].items():
        print(f'  {k}: {v}')

    print(f"\nCONTENT SCHEMA: {OUT_CONTENT_PATH}")
    print(f'  Subconcepts: {len(content["subconcepts"])}')
    ncert_subs = [s for s in content['subconcepts'].values() if s['source'] == 'ncert']
    comp_subs = [s for s in content['subconcepts'].values() if s['source'] == 'competitive_only']
    total_nq = sum(len(s['ncert_questions']) for s in ncert_subs)
    total_nex = sum(len(s['ncert_examples']) for s in ncert_subs)
    total_cq_inh = sum(len(s['competitive_questions']) for s in ncert_subs)
    total_cq_own = sum(len(s['competitive_questions']) for s in comp_subs)
    print(f'  NCERT subconcepts: {len(ncert_subs)} (questions={total_nq}, examples={total_nex}, inherited_comp_q={total_cq_inh})')
    print(f'  Competitive-only subconcepts: {len(comp_subs)} (questions={total_cq_own})')
    print(f'  Total questions in all subs: {total_nq + total_cq_inh + total_cq_own}')
    print(f'  Total examples: {total_nex}')

    print(f"\nSubconcept order (master schema):")
    for c in master['concepts']:
        tag = 'NCERT' if c['source'] == 'ncert' else 'COMP'
        print(f"  [{tag}] {c['code']}: {c['name']} ({len(c['subconcepts'])} subs)")


if __name__ == '__main__':
    assemble()
