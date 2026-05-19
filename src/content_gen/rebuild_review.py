"""Rebuild final content JSON + review data from latest generation."""
import json, os, sys, re, base64
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.join(os.path.dirname(__file__), '..', '..')

with open(os.path.join(BASE, 'experiments/03_topology_generation/ch09_schema.json'), 'r', encoding='utf-8') as f:
    schema = json.load(f)
with open(os.path.join(BASE, 'experiments/03_topology_generation/ch09_line_ranges.json'), 'r', encoding='utf-8') as f:
    lr = json.load(f)
with open(os.path.join(BASE, 'experiments/03_topology_generation/ch09_unified_mapping.json'), 'r', encoding='utf-8') as f:
    unified = json.load(f)

out_dir = os.path.join(BASE, 'experiments/05_content_generation/ch09_full')

content_by_sid = {}
for fname in sorted(os.listdir(out_dir)):
    if not fname.endswith('.json') or fname == 'ch09_full_results.json':
        continue
    sid = fname.replace('.json', '')
    with open(os.path.join(out_dir, fname), 'r', encoding='utf-8') as f:
        data = json.load(f)
    if 'error' not in data.get('content', {}):
        content_by_sid[sid] = data['content']

chapter_name = list(schema.keys())[0]
concepts = schema[chapter_name]
final_content = {}

for concept_name, subconcepts in concepts.items():
    concept_key = f"Concept: {concept_name}"
    final_content[concept_key] = {}

    for sub_name in subconcepts:
        sid = None
        for s, data in lr.items():
            if data['name'] == sub_name:
                sid = s
                break
        if not sid or sid not in content_by_sid:
            continue

        gen = content_by_sid[sid]
        u = unified.get(sid, {})
        sub_key = f"Subconcept: {sub_name}"

        sub_content = {
            "Summary": {
                "Theory": gen.get('theory', ''),
                "VisualContent": gen.get('theory_visual_content', {"Needed": False}),
            },
            "SCQs": {},
            "SubjectiveTypes": {},
            "Examples": {},
        }

        # Generated SCQs — skip those without options
        scq_idx = 0
        for i, scq in enumerate(gen.get('scqs', [])):
            q = scq.get('question', '')
            fmt = scq.get('scq_format', 'standard')
            if fmt == 'assertion_reason':
                has_opts = 'Both A and R' in q or 'both A and R' in q.lower()
            else:
                has_opts = bool(re.search(r'\(A\)', q)) and bool(re.search(r'\(B\)', q))

            if not has_opts:
                continue

            scq_idx += 1
            sub_content["SCQs"][f"Question {scq_idx}"] = {
                "isBackExercise": False, "isInTextQuestion": False,
                "scq_format": fmt, "Difficulty": scq.get('difficulty', 'Medium'),
                "Question": q, "Answer": scq.get('answer', ''),
                "Solution": scq.get('solution', ''),
                "VisualContent": scq.get('visual_content', {"needed": False}),
                "_source": "generated",
            }

        # Generated Subjective
        for i, subj in enumerate(gen.get('subjective', [])):
            sub_content["SubjectiveTypes"][f"Question {i+1}"] = {
                "isBackExercise": False, "isInTextQuestion": False,
                "answer_format": subj.get('answer_format', 'descriptive'),
                "Difficulty": subj.get('difficulty', 'Medium'),
                "Question": subj.get('question', ''),
                "Answer": subj.get('answer', ''),
                "Solution": subj.get('solution', ''),
                "VisualContent": subj.get('visual_content', {"needed": False}),
                "_source": "generated",
            }

        # Existing NCERT questions
        for existing in u.get('back_exercises', []) + u.get('intext_questions', []):
            qtype = existing.get('type', 'subjective')
            target = "SCQs" if qtype == 'scq' else "SubjectiveTypes"
            idx = len(sub_content[target]) + 1
            source = "back_exercise" if existing['id'].startswith('BACK') else "in_text"
            sub_content[target][f"Question {idx}"] = {
                "isBackExercise": existing['id'].startswith('BACK'),
                "isInTextQuestion": existing['id'].startswith('INTEXT'),
                "Difficulty": existing.get('difficulty', 'Medium'),
                "Question": existing.get('question_text', ''),
                "Answer": str(existing.get('answer', '')) if existing.get('answer') else '',
                "Solution": "",
                "VisualContent": {"needed": False},
                "_source": source,
            }

        # Generated Examples
        for i, ex in enumerate(gen.get('examples', [])):
            sub_content["Examples"][f"Example {i+1}"] = {
                "isSolvedExample": True, "isFromNCERT": False,
                "Difficulty": ex.get('difficulty', 'Medium'),
                "Question": ex.get('question', ''),
                "Solution": ex.get('solution', ''),
                "VisualContent": ex.get('visual_content', {"needed": False}),
                "_source": "generated",
            }

        # NCERT examples
        for ncert_ex in u.get('solved_examples', []):
            idx = len(sub_content["Examples"]) + 1
            sub_content["Examples"][f"Example {idx}"] = {
                "isSolvedExample": True, "isFromNCERT": True,
                "Difficulty": "Medium",
                "Question": ncert_ex.get('question', ''),
                "Solution": "",
                "VisualContent": {"needed": False},
                "_source": "ncert",
            }

        final_content[concept_key][sub_key] = sub_content

# Save final content
out_path = os.path.join(BASE, 'experiments/05_content_generation/ch09_final_content.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(final_content, f, indent=2, ensure_ascii=False)

total_scq = sum(len(s.get('SCQs', {})) for c in final_content.values() for s in c.values())
total_subj = sum(len(s.get('SubjectiveTypes', {})) for c in final_content.values() for s in c.values())
total_ex = sum(len(s.get('Examples', {})) for c in final_content.values() for s in c.values())

print(f"Final content: {os.path.getsize(out_path) // 1024}KB")
print(f"SCQs: {total_scq} | Subjective: {total_subj} | Examples: {total_ex} | Total: {total_scq + total_subj + total_ex}")

# Rebuild review_data.js with inline data
images_b64 = {}
img_dir = os.path.join(BASE, 'experiments/05_content_generation/ch09_generated_images')
if os.path.exists(img_dir):
    for fname in os.listdir(img_dir):
        if fname.endswith('.png'):
            with open(os.path.join(img_dir, fname), 'rb') as f:
                images_b64[fname.replace('.png', '')] = f"data:image/png;base64,{base64.b64encode(f.read()).decode('ascii')}"

review_data = os.path.join(BASE, 'review/review_data.js')
with open(review_data, 'w', encoding='utf-8') as f:
    f.write(f"const CONTENT_DATA = {json.dumps(final_content, ensure_ascii=False)};\n")
    f.write(f"const SCHEMA_DATA = {json.dumps(schema, ensure_ascii=False)};\n")
    f.write(f"const GENERATED_IMAGES = {json.dumps(images_b64, ensure_ascii=False)};\n")

print(f"Review data: {os.path.getsize(review_data) // 1024}KB")

# Now rebuild the self-contained HTML
logo_path = 'D:/ACADZA_WORK/acadza-pdf-generator/partners/acadza/logo.png'
with open(logo_path, 'rb') as f:
    logo_b64 = base64.b64encode(f.read()).decode('ascii')

gear_path = 'D:/ACADZA_WORK/acadza-pdf-generator/partners/acadza/watermark.svg'
with open(gear_path, 'r') as f:
    gear_svg = f.read()
gear_b64 = base64.b64encode(gear_svg.encode('utf-8')).decode('ascii')

# Read index.html template (strip the old inlined data)
with open(os.path.join(BASE, 'review/index.html'), 'r', encoding='utf-8') as f:
    html = f.read()

# Find and replace the old data block
# The data is between <script> and the next </script> that contains CONTENT_DATA
data_start = html.find('const CONTENT_DATA')
if data_start > 0:
    # Find the <script> tag before it
    script_start = html.rfind('<script>', 0, data_start)
    # Find the </script> after it
    script_end = html.find('</script>', data_start) + len('</script>')
    # Replace with new data
    with open(review_data, 'r', encoding='utf-8') as f:
        new_data = f.read()
    html = html[:script_start] + f'<script>\n{new_data}\n</script>' + html[script_end:]

with open(os.path.join(BASE, 'review/index.html'), 'w', encoding='utf-8') as f:
    f.write(html)

print(f"HTML rebuilt: {os.path.getsize(os.path.join(BASE, 'review/index.html')) // 1024}KB")
print("Done — refresh review/index.html in browser")
