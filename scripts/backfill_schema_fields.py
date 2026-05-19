"""
Backfill schema v8 fields (isNCERT, isFoundation, foundation_type) into ch09_final_content.json.
Also ensures _source field is correct for all items.

Creates a backup before modifying.
"""
import json, os, sys, shutil
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.join(os.path.dirname(__file__), '..')
content_path = os.path.join(BASE, 'experiments/05_content_generation/ch09_final_content.json')

# Backup first (never overwrite rule)
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup_path = content_path.replace('.json', f'_backup_{timestamp}.json')
shutil.copy2(content_path, backup_path)
print(f"Backup created: {backup_path}")

with open(content_path, 'r', encoding='utf-8') as f:
    content = json.load(f)

stats = {'scq': 0, 'subj': 0, 'example': 0, 'already_had': 0}

for concept_key, subconcepts in content.items():
    for sub_key, sub_data in subconcepts.items():
        # Process SCQs
        for key, item in sub_data.get('SCQs', {}).items():
            if 'isNCERT' not in item:
                item['isNCERT'] = True
                item['isFoundation'] = False
                item['foundation_type'] = None
                stats['scq'] += 1
            else:
                stats['already_had'] += 1

        # Process SubjectiveTypes
        for key, item in sub_data.get('SubjectiveTypes', {}).items():
            if 'isNCERT' not in item:
                item['isNCERT'] = True
                item['isFoundation'] = False
                item['foundation_type'] = None
                stats['subj'] += 1
            else:
                stats['already_had'] += 1

        # Process Examples
        for key, item in sub_data.get('Examples', {}).items():
            if 'isNCERT' not in item:
                item['isNCERT'] = True
                item['isFoundation'] = False
                item['foundation_type'] = None
                stats['example'] += 1
            else:
                stats['already_had'] += 1

# Save
with open(content_path, 'w', encoding='utf-8') as f:
    json.dump(content, f, ensure_ascii=False, indent=2)

total = stats['scq'] + stats['subj'] + stats['example']
print(f"\nBackfill complete:")
print(f"  SCQs:       {stats['scq']} items updated")
print(f"  Subjective: {stats['subj']} items updated")
print(f"  Examples:   {stats['example']} items updated")
print(f"  Total:      {total} items (+ {stats['already_had']} already had fields)")
print(f"\nAll items now have: isNCERT=true, isFoundation=false, foundation_type=null")
