"""Build master schema merging NCERT + Competitive via verified mapping."""
import json, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = 'D:/ACADZA_WORK/8-9-10th PIPELINE'

with open(f'{BASE}/experiments/03_topology_generation/ch09_schema.json', 'r', encoding='utf-8') as f:
    ncert_schema = json.load(f)
with open(f'{BASE}/experiments/03_topology_generation/competitive/comp_schema_sealed.json', 'r', encoding='utf-8') as f:
    comp_schema = json.load(f)
with open(f'{BASE}/experiments/03_topology_generation/competitive/comp_mapping_verified.json', 'r', encoding='utf-8') as f:
    mapping = json.load(f)

# Index competitive subs
comp_sub_index = {}
for c in comp_schema['concepts']:
    for s in c['subconcepts']:
        comp_sub_index[s['id']] = {
            'original_parent_concept': c['name'],
            'original_parent_code': c['id'],
            'name': s['name'],
            'tier': s.get('tier', 'thin'),
            'is_connecting_topic': s.get('is_connecting_topic', False),
            'line_start': s['line_start'],
            'line_end': s['line_end'],
            'line_count': s['line_count'],
            'formulas': s['formulas'],
            'figures': s['figures'],
            'illustrations': s['illustrations'],
        }

overlap_list = [m for m in mapping['mappings'] if m['category'] == 'overlap']
comp_only_list = [m for m in mapping['mappings'] if m['category'] == 'competitive_only']
ncert_only_list = mapping['ncert_only']

master = {
    '_description': 'Master schema for Ch1: Light - Reflection and Refraction. Merges NCERT + Competitive.',
    '_version': 'master_v1',
    'chapter': 'Light - Reflection and Refraction',
    'class_level': '10',
    'subject': 'Physics',
    'concepts': [],
    'competitive_only_concepts': [],
    'stats': {}
}

# Group overlapped comp subs by their NCERT target
comp_overlaps_by_ncert = defaultdict(list)
for m in overlap_list:
    comp_sub = comp_sub_index[m['comp_code']]
    comp_overlaps_by_ncert[m['ncert_code']].append({
        'comp_code': m['comp_code'],
        'name': comp_sub['name'],
        'original_parent_concept': comp_sub['original_parent_concept'],
        'original_parent_code': comp_sub['original_parent_code'],
        'line_start': comp_sub['line_start'],
        'line_end': comp_sub['line_end'],
        'tier': comp_sub['tier'],
        'is_connecting_topic': comp_sub['is_connecting_topic'],
    })

# Build NCERT-anchored concepts
ncert_ch = list(ncert_schema.keys())[0]
for c_idx, (parent_name, subs) in enumerate(ncert_schema[ncert_ch].items(), start=1):
    parent_code = f'NCRT_C{c_idx}'
    concept = {
        'code': parent_code,
        'name': parent_name,
        'source': 'ncert',
        'subconcepts': []
    }
    for s_idx, sub_name in enumerate(subs, start=1):
        sub_code = f'NCRT_C{c_idx}.S{s_idx}'
        overlaps_here = comp_overlaps_by_ncert.get(sub_code, [])
        is_ncert_only = any(n['ncert_code'] == sub_code for n in ncert_only_list)

        concept['subconcepts'].append({
            'code': sub_code,
            'name': sub_name,
            'source': 'ncert',
            'isNCERT': True,
            'isFoundation': not is_ncert_only,
            'is_ncert_only': is_ncert_only,
            'competitive_overlaps': overlaps_here,
        })
    master['concepts'].append(concept)

# Build competitive-only section — preserve original comp parents
comp_only_by_parent = defaultdict(list)
for m in comp_only_list:
    comp_sub = comp_sub_index[m['comp_code']]
    comp_only_by_parent[comp_sub['original_parent_code']].append({
        'comp_code': m['comp_code'],
        'name': comp_sub['name'],
        'line_start': comp_sub['line_start'],
        'line_end': comp_sub['line_end'],
        'tier': comp_sub['tier'],
        'is_connecting_topic': comp_sub['is_connecting_topic'],
    })

seen = set()
for c in comp_schema['concepts']:
    if c['id'] in seen or c['id'] not in comp_only_by_parent:
        continue
    seen.add(c['id'])
    master['competitive_only_concepts'].append({
        'code': c['id'],
        'name': c['name'],
        'source': 'competitive_only',
        'is_connecting_topic': c.get('is_connecting_topic', False),
        'subconcepts': [
            {
                'code': s['comp_code'],
                'name': s['name'],
                'source': 'competitive_only',
                'isNCERT': False,
                'isFoundation': True,
                'is_connecting_topic': s['is_connecting_topic'],
                'line_start': s['line_start'],
                'line_end': s['line_end'],
                'tier': s['tier'],
            }
            for s in comp_only_by_parent[c['id']]
        ]
    })

# Stats
total_ncert_subs = sum(len(c['subconcepts']) for c in master['concepts'])
total_overlap = sum(len(s.get('competitive_overlaps', [])) for c in master['concepts'] for s in c['subconcepts'])
total_comp_only_subs = sum(len(c['subconcepts']) for c in master['competitive_only_concepts'])
ncert_only_count = sum(1 for c in master['concepts'] for s in c['subconcepts'] if s.get('is_ncert_only'))

master['stats'] = {
    'ncert_concepts': len(master['concepts']),
    'ncert_subconcepts': total_ncert_subs,
    'overlapping_comp_subs_inherited': total_overlap,
    'competitive_only_concepts': len(master['competitive_only_concepts']),
    'competitive_only_subconcepts': total_comp_only_subs,
    'ncert_only_subconcepts': ncert_only_count,
}

out_path = f'{BASE}/experiments/03_topology_generation/competitive/master_schema.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(master, f, indent=2, ensure_ascii=False)

print(json.dumps(master, indent=2, ensure_ascii=False))
print(f'\nSaved: {out_path}')
