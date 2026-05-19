"""
Cross-validate competitive topology: Regex MMD extraction vs PDF Color extraction.
Confirms concepts and subconcepts by matching text + color + size signals.
"""
import fitz, json, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# === SOURCE 1: Regex extraction from MMD ===
with open('experiments/03_topology_generation/competitive/comp_topology.json', 'r', encoding='utf-8') as f:
    topo = json.load(f)

regex_concepts = []
regex_subconcepts = []
for c in topo['concepts']:
    regex_concepts.append(c['name'])
    for s in c['subconcepts']:
        if s['name'] != c['name']:  # skip self-referencing singles
            regex_subconcepts.append({'name': s['name'], 'parent': c['name']})

# === SOURCE 2: PDF color extraction ===
doc = fitz.open('C:/Users/gamin/Downloads/10 PHYSICS FOUNDATION.pdf')

pdf_concepts = []
pdf_subconcepts = []

skip_concept = ['Fig', 'SOLUTION', 'ILLUSTRATION', 'Exercise', 'MISCELLANEOUS', 'SOLVED',
                'CONTENTS', 'Foundation', 'Brief Explanations', 'r-.']
skip_sub = ['Fig', 'SOLUTION', 'Keep in Memory', 'Learn', 'Physics', 'Light-Reflection',
            'ILLUSTRATION', 'Time', 'Tim', 'ck Your', 'Multiple Choice', 'Assertion-Reason',
            'Fill in the Blanks', 'True / False', 'Match the Following', 'Passage Based',
            'Very Short', 'Short Answer', 'Long Answer', 'Reasoning Based', 'HOTS',
            'Case Based', 'Text-Book', 'Exemplar', 'Single Option', 'One or More',
            'Integer', 'Multiple Matching', 'Assertion &', 'Foundation', 'Other formulae']

for page_num in range(3, 42):
    page = doc[page_num]
    blocks = page.get_text('dict')['blocks']
    for block in blocks:
        if block['type'] != 0:
            continue
        for line_block in block['lines']:
            line_text = ''
            max_size = 0
            is_cyan = False
            is_bold = False
            for span in line_block['spans']:
                text = span['text'].strip()
                if not text:
                    continue
                color = span['color']
                r = (color >> 16) & 0xFF
                g = (color >> 8) & 0xFF
                b = color & 0xFF
                size = span['size']
                bold = bool(span['flags'] & 16)
                if r < 20 and g > 150 and b > 200:
                    is_cyan = True
                    if size > max_size:
                        max_size = size
                    is_bold = is_bold or bold
                line_text += text + ' '
            line_text = line_text.strip()
            if not line_text or len(line_text) < 3 or not is_cyan:
                continue
            if max_size >= 12.0:
                if not any(line_text.startswith(s) for s in skip_concept):
                    pdf_concepts.append({'text': line_text, 'page': page_num + 1, 'size': max_size})
            elif max_size >= 11.0 and is_bold:
                if not any(line_text.startswith(s) for s in skip_sub):
                    # Also skip CASE entries
                    if not line_text.startswith('CASE'):
                        pdf_subconcepts.append({'text': line_text, 'page': page_num + 1, 'size': max_size})

doc.close()


def normalize(s):
    return re.sub(r'[^a-z0-9 ]', '', s.lower()).strip()


# === CONCEPT CROSS-VALIDATION ===
print('=' * 80)
print('CONCEPT CROSS-VALIDATION: Regex MMD vs PDF Color+Size')
print('=' * 80)
print(f'Regex concepts: {len(regex_concepts)}')
print(f'PDF concepts (cyan 12.6pt): {len(pdf_concepts)}')

matched = []
regex_only = []

for rc in regex_concepts:
    rc_n = normalize(rc)
    best_match = None
    for pc in pdf_concepts:
        pc_n = normalize(pc['text'])
        if rc_n == pc_n:
            best_match = ('EXACT', pc)
            break
        if len(rc_n) > 8 and len(pc_n) > 8:
            if rc_n[:15] == pc_n[:15]:
                best_match = ('PREFIX', pc)
                break
            if rc_n in pc_n or pc_n in rc_n:
                best_match = ('CONTAINS', pc)
                break
    if best_match:
        matched.append((rc, best_match[0], best_match[1]))
    else:
        regex_only.append(rc)

# PDF concepts not matched
matched_pdf_norms = set()
for _, _, pc in matched:
    matched_pdf_norms.add(normalize(pc['text']))

pdf_only = [pc for pc in pdf_concepts if normalize(pc['text']) not in matched_pdf_norms]
# Check partial matches for pdf_only
real_pdf_only = []
for pc in pdf_only:
    pc_n = normalize(pc['text'])
    found = False
    for _, _, mpc in matched:
        if pc_n in normalize(mpc['text']) or normalize(mpc['text']) in pc_n:
            found = True
            break
    if not found:
        real_pdf_only.append(pc)

print(f'\nMATCHED: {len(matched)}')
for rc, match_type, pc in matched:
    print(f'  [{match_type:8s}] Regex: {rc[:40]:40s} <=> PDF(p{pc["page"]}): {pc["text"][:40]}')

if regex_only:
    print(f'\nREGEX ONLY ({len(regex_only)}) — in MMD but NOT confirmed by PDF color:')
    for r in regex_only:
        print(f'  UNCONFIRMED: {r}')

if real_pdf_only:
    print(f'\nPDF ONLY ({len(real_pdf_only)}) — in PDF color but NOT in regex:')
    for p in real_pdf_only:
        print(f'  MISSED: P{p["page"]} | {p["text"][:70]}')


# === SUBCONCEPT CROSS-VALIDATION ===
print(f'\n{"=" * 80}')
print('SUBCONCEPT CROSS-VALIDATION: Regex MMD vs PDF Color+Size')
print('=' * 80)
print(f'Regex subconcepts: {len(regex_subconcepts)}')
print(f'PDF subconcepts (cyan 11.7pt bold): {len(pdf_subconcepts)}')

sub_matched = []
sub_regex_only = []

for rs in regex_subconcepts:
    rs_n = normalize(rs['name'])
    best = None
    for ps in pdf_subconcepts:
        ps_n = normalize(ps['text'])
        if rs_n == ps_n:
            best = ('EXACT', ps)
            break
        if len(rs_n) > 8 and len(ps_n) > 8:
            if rs_n[:15] == ps_n[:15]:
                best = ('PREFIX', ps)
                break
            if rs_n in ps_n or ps_n in rs_n:
                best = ('CONTAINS', ps)
                break
    if best:
        sub_matched.append((rs['name'], rs['parent'], best[0], best[1]))
    else:
        sub_regex_only.append(rs)

sub_matched_pdf_norms = set()
for _, _, _, ps in sub_matched:
    sub_matched_pdf_norms.add(normalize(ps['text']))

sub_pdf_only = [ps for ps in pdf_subconcepts if normalize(ps['text']) not in sub_matched_pdf_norms]
# Filter partial matches
real_sub_pdf_only = []
for ps in sub_pdf_only:
    ps_n = normalize(ps['text'])
    found = False
    for _, _, _, mps in sub_matched:
        if ps_n in normalize(mps['text']) or normalize(mps['text']) in ps_n:
            found = True
            break
    if not found:
        real_sub_pdf_only.append(ps)

print(f'\nMATCHED: {len(sub_matched)}')
for name, parent, match_type, ps in sub_matched:
    print(f'  [{match_type:8s}] Regex: {name[:35]:35s} (under {parent[:20]:20s}) <=> PDF(p{ps["page"]}): {ps["text"][:35]}')

if sub_regex_only:
    print(f'\nREGEX ONLY ({len(sub_regex_only)}) — NOT confirmed by PDF color:')
    for r in sub_regex_only:
        print(f'  UNCONFIRMED: {r["name"]:40s} (under {r["parent"]})')

if real_sub_pdf_only:
    print(f'\nPDF ONLY ({len(real_sub_pdf_only)}) — in PDF color but NOT in regex:')
    for p in real_sub_pdf_only:
        print(f'  MISSED: P{p["page"]} | {p["text"][:70]}')

# === SUMMARY ===
print(f'\n{"=" * 80}')
print('SUMMARY')
print('=' * 80)
total_c = len(matched)
total_s = len(sub_matched)
print(f'CONFIRMED CONCEPTS:    {total_c} (text + color + size validated)')
print(f'CONFIRMED SUBCONCEPTS: {total_s} (text + color + size validated)')
print(f'Unconfirmed regex concepts:    {len(regex_only)}')
print(f'Unconfirmed regex subconcepts: {len(sub_regex_only)}')
print(f'Missed by regex (PDF only):    concepts={len(real_pdf_only)}, subconcepts={len(real_sub_pdf_only)}')
