"""
Topology Extractor — Competitive/Foundation PDF variant.
Forked from: src/topology/extractor.py (NCERT version)

Differences from NCERT extractor:
- No NCERT section numbering (9.1, 9.2.1). Uses ALL-CAPS vs Title-Case to determine hierarchy.
- Detects CONNECTING TOPIC, ILLUSTRATION, CASE STUDY sections
- Marks is_connecting_topic for competitive-only subconcepts
- Filters out non-content sections (SOLUTION, Learn More, Keep in Memory, etc.)

Produces 3 JSONs (same format as NCERT):
1. comp_schema.json — database-ready: {chapter: {concept: [subconcepts]}}
2. comp_topology.json — internal: concepts, subconcepts with IDs, tiers
3. comp_line_ranges.json — internal: line ranges, density, image refs
"""
import re
import json
import sys
from pathlib import Path


# Sections to SKIP — these are not content topology sections
SKIP_PATTERNS = [
    r'^SOLUTION',
    r'^CONTENTS$',
    r'^Physics$',
    r'^Keep in Memory',
    r'^Learn\b',
    r'^More$',
    r'^Think Out of the Box',
    r'^Cautions',
    r'^Note\b',
    r'^DIRECTIONS',
    r'^Column I',
    r'^Column II',
    r'^List-I',
    r'^List-II',
    r'^Passage$',
    r'^SOLVED EXAMPLES',
    r'^MISCELLANEOUS SOLVED',
    r'^SOLUTIONS',
    r'^s.*!.*Ჩ',  # OCR artifact
    r'^Take a large',  # Activity instruction MathPix promoted
    r'^L?L?ILLUSTRAT',  # ILLUSTRATION / LLUSTRATION / ILLUSTRATIOM variants
    r'^L?l?lustrat',    # Lowercase OCR variant: Llustration
    r'^CASE\s*[-]?\s*STUDY',  # CASE STUDY-1, CASE STUDY-2 etc.
    r'^CASE\s*[-]?\s*[IVX]+',  # CASE-I, CASE-II etc.
    r'^Lateral displacement depends',  # Body text promoted to header by MathPix
    r'^\(b\)\s*For\s',  # Sub-label within table, not a real subconcept
    r'^LENS$',  # Bare "LENS" after ILLUSTRATION leak — not a standalone header

]

# Exercise section headers — mark where exercises begin
EXERCISE_PATTERNS = [
    r'^Exercise \d',
    r'^Foundation Builder',
    r'^Single Option Correct',
    r'^One or More',
    r'^Multiple Choice',
    r'^Assertion.Reason',
    r'^Fill in the Blanks',
    r'^True\s*/\s*False',
    r'^Match the Following',
    r'^Multiple Matching',
    r'^Passage Based',
    r'^Very Short Answer',
    r'^Short Answer',
    r'^Long Answer',
    r'^Reasoning Based',
    r'^HOTS',
    r'^Case Based',
    r'^Text-Book',
    r'^Exemplar',
    r'^Integer.*Numeric',
]


def parse_sections(lines: list) -> list:
    """
    Parse content sections from competitive PDF MMD.

    Classification:
    - ALL CAPS title (>= 3 words or known pattern) → concept-level (main topic)
    - Title Case → subconcept-level
    - CONNECTING TOPIC → marks next section as competitive-only
    - ILLUSTRATION → solved example (not topology, tracked separately)
    - CASE STUDY → separate tracking
    """
    sections = []
    is_connecting = False  # Flag: next real section is a connecting topic

    for i, line in enumerate(lines):
        m = re.search(r'\\section\*\{(.+?)\}', line)
        if not m:
            continue

        raw_title = m.group(1).strip()
        # Clean: remove \\ linebreaks, LaTeX formatting
        title = re.sub(r'\s*\\\\\s*', ' ', raw_title)
        title = re.sub(r'\$\\mathbf\{(.+?)\}\$', r'\1', title)  # \mathbf{1.4} → 1.4
        title = re.sub(r'!\[.*?\]\(.*?\)', '', title).strip()  # Remove inline images
        title = title.strip()

        if not title or len(title) < 2:
            continue

        # Check SKIP patterns
        should_skip = False
        for pat in SKIP_PATTERNS:
            if re.match(pat, title, re.IGNORECASE):
                should_skip = True
                break
        if should_skip:
            continue

        # Check if this is an EXERCISE section (marks end of theory content)
        is_exercise = False
        for pat in EXERCISE_PATTERNS:
            if re.match(pat, title, re.IGNORECASE):
                is_exercise = True
                break
        if is_exercise:
            continue  # Skip exercise headers — we track exercise start separately

        # Detect CONNECTING TOPIC marker
        if title.upper() == 'CONNECTING TOPIC':
            is_connecting = True
            continue  # The actual topic name is the NEXT section

        # Detect ILLUSTRATION (solved example, not topology) — catch ALL OCR variants
        if re.match(r'L?L?ILLUSTRAT', title, re.IGNORECASE):
            continue  # Skip — tracked separately

        # Detect CASE STUDY and CASE sub-sections
        if re.match(r'CASE\s*[-]?\s*(STUDY|[IVX]+)', title, re.IGNORECASE):
            continue  # Case studies/cases are exercise-level, not topology

        # Detect chapter title
        if re.match(r'^\d+\.\s+\w', title):
            # "1. Light-Reflection and Refraction"
            sections.append({
                'line': i + 1,
                'title': re.sub(r'^\d+\.\s+', '', title).strip(),
                'level': 'chapter',
                'raw_line': line.strip(),
                'is_connecting_topic': False,
            })
            continue

        # Determine hierarchy: ALL CAPS = concept, Title Case = subconcept
        # Strip LaTeX ($...$) before checking case — formulas shouldn't affect classification
        title_no_latex = re.sub(r'\$[^$]*\$', '', title)
        alpha_chars = re.sub(r'[^a-zA-Z]', '', title_no_latex)
        is_all_caps = alpha_chars == alpha_chars.upper() and len(alpha_chars) >= 5

        level = 'concept' if is_all_caps else 'subconcept'

        sections.append({
            'line': i + 1,
            'title': title,
            'level': level,
            'raw_line': line.strip(),
            'is_connecting_topic': is_connecting,
        })

        # Reset connecting flag after consuming it
        is_connecting = False

    return sections


def find_exercises_start(lines: list) -> int:
    """Find where Exercise 1 starts (end of theory content)."""
    for i, line in enumerate(lines):
        # Look for first Exercise header after substantial content
        if i < 100:  # Skip table of contents
            continue
        m = re.search(r'\\section\*\{Exercise \d', line, re.IGNORECASE)
        if m:
            return i + 1
        # Also check for MISCELLANEOUS SOLVED EXAMPLES (before exercises)
        if 'MISCELLANEOUS SOLVED' in line:
            return i + 1
    return len(lines) + 1


def find_illustrations(lines: list) -> list:
    """Extract all ILLUSTRATION solved examples with line ranges."""
    illustrations = []
    for i, line in enumerate(lines):
        m = re.search(r'\\section\*\{L?L?ILLUSTRAT(?:ION|IOM)\s*:?\s*\$?\\?m?a?t?h?b?f?\{?([\d.\s]+)', line, re.IGNORECASE)
        if m:
            illustrations.append({
                'num': m.group(1).strip().rstrip('.'),
                'line': i + 1,
            })
    # Calculate end lines
    for j in range(len(illustrations)):
        if j + 1 < len(illustrations):
            illustrations[j]['end_line'] = illustrations[j + 1]['line']
        else:
            illustrations[j]['end_line'] = illustrations[j]['line'] + 30  # Estimate
    return illustrations


def measure_density(lines: list, start: int, end: int) -> dict:
    """Measure content density for a line range."""
    end = min(end, len(lines) + 1)
    block = '\n'.join(lines[start - 1:end - 1])
    return {
        'line_count': end - start,
        'formulas': len(re.findall(r'\\frac\{', block)) + block.count('$$') // 2,
        'figures': block.count('!['),
        'tables': block.count('\\begin{table}') + block.count('\\begin{tabular}'),
        'illustrations': len(re.findall(r'ILLUSTRAT(?:ION|IOM)\s*:', block, re.IGNORECASE)),
    }


def extract_image_refs(lines: list, start: int, end: int) -> list:
    """Extract image references within a line range."""
    images = []
    end = min(end, len(lines) + 1)
    for i in range(start - 1, end - 1):
        line = lines[i]
        for m in re.finditer(r'!\[(.*?)\]\((.*?)\)', line):
            images.append({
                'alt': m.group(1),
                'url': m.group(2),
                'line': i + 1,
            })
    return images


def clean_title(title: str) -> str:
    """Clean and normalize section title."""
    cleaned = title.strip()
    # Title case if ALL CAPS
    if cleaned == cleaned.upper() and len(cleaned) > 3:
        cleaned = cleaned.title()
    return cleaned


def extract_topology(mmd_path: str) -> tuple:
    """
    Main extractor for competitive PDF.
    Returns (topology_json, line_ranges_json, illustrations_list).
    """
    with open(mmd_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    total_lines = len(lines)
    exercises_start = find_exercises_start(lines)
    all_sections = parse_sections(lines)
    illustrations = find_illustrations(lines)

    # Filter to only content sections (before exercises)
    content_sections = [s for s in all_sections if s['line'] < exercises_start]

    # Calculate line ranges
    for j in range(len(content_sections)):
        start = content_sections[j]['line']
        if j + 1 < len(content_sections):
            end = content_sections[j + 1]['line']
        else:
            end = exercises_start
        content_sections[j]['end_line'] = end
        content_sections[j]['density'] = measure_density(lines, start, end)
        content_sections[j]['images'] = extract_image_refs(lines, start, end)

    # Build concept → subconcept hierarchy
    concepts = []
    current_concept = None

    for s in content_sections:
        if s['level'] == 'chapter':
            continue  # Skip chapter title

        if s['level'] == 'concept':
            # Start a new concept
            if current_concept:
                concepts.append(current_concept)
            current_concept = {
                'title': s['title'],
                'name': clean_title(s['title']),
                'line': s['line'],
                'is_connecting_topic': s['is_connecting_topic'],
                'subconcepts': [],
            }
            # If no subconcepts follow, this concept IS the subconcept

        elif s['level'] == 'subconcept':
            if current_concept is None:
                # Orphan subconcept before first concept — create implicit concept
                current_concept = {
                    'title': 'Introduction',
                    'name': 'Introduction',
                    'line': s['line'],
                    'is_connecting_topic': False,
                    'subconcepts': [],
                }

            density = s['density']
            lc = density['line_count']
            tier = ('thin' if lc < 15 else 'medium' if lc < 40 else 'rich')

            current_concept['subconcepts'].append({
                'title': s['title'],
                'name': clean_title(s['title']),
                'line_start': s['line'],
                'line_end': s['end_line'],
                'density': density,
                'tier': tier,
                'images': s['images'],
                'is_connecting_topic': s['is_connecting_topic'],
            })

    # Don't forget last concept
    if current_concept:
        concepts.append(current_concept)

    # For concepts that have NO subconcepts, the concept itself becomes its own subconcept
    for concept in concepts:
        if not concept['subconcepts']:
            # Find end line
            idx = concepts.index(concept)
            if idx + 1 < len(concepts):
                end = concepts[idx + 1]['line']
            else:
                end = exercises_start
            density = measure_density(lines, concept['line'], end)
            lc = density['line_count']
            concept['subconcepts'].append({
                'title': concept['title'],
                'name': concept['name'],
                'line_start': concept['line'],
                'line_end': end,
                'density': density,
                'tier': 'thin' if lc < 15 else 'medium' if lc < 40 else 'rich',
                'images': extract_image_refs(lines, concept['line'], end),
                'is_connecting_topic': concept['is_connecting_topic'],
            })

    # Assign IDs
    for i, concept in enumerate(concepts):
        concept['id'] = f'COMP_C{i + 1}'
        for j, sub in enumerate(concept['subconcepts']):
            sub['id'] = f'COMP_C{i + 1}.S{j + 1}'

    # Build output JSONs
    topology = {
        'source_file': str(mmd_path),
        'total_lines': total_lines,
        'exercises_start_line': exercises_start,
        'illustrations_count': len(illustrations),
        'concepts': [],
    }
    line_ranges = {}

    for concept in concepts:
        topo_concept = {
            'id': concept['id'],
            'name': concept['name'],
            'is_connecting_topic': concept['is_connecting_topic'],
            'subconcepts': [],
        }
        for sub in concept['subconcepts']:
            topo_sub = {
                'id': sub['id'],
                'name': sub['name'],
                'tier': sub['tier'],
                'image_count': len(sub['images']),
                'is_connecting_topic': sub['is_connecting_topic'],
            }
            topo_concept['subconcepts'].append(topo_sub)

            line_ranges[sub['id']] = {
                'name': sub['name'],
                'line_start': sub['line_start'],
                'line_end': sub['line_end'],
                'density': sub['density'],
                'images': [{'url': img.get('url', ''), 'alt': img.get('alt', ''), 'line': img.get('line', 0)} for img in sub['images']],
                'is_connecting_topic': sub['is_connecting_topic'],
            }

        topology['concepts'].append(topo_concept)

    return topology, line_ranges, illustrations


def build_schema(topology: dict) -> dict:
    """Build database-ready schema JSON."""
    chapter_name = "Light - Reflection and Refraction"

    # Try to extract from source
    src = topology.get('source_file', '')
    if src:
        try:
            with open(src, 'r', encoding='utf-8') as f:
                for raw_line in f:
                    m = re.search(r'\\section\*\{\d+\.\s+(.+?)\}', raw_line)
                    if m:
                        chapter_name = re.sub(r'\s*\\\\\s*', ' ', m.group(1)).strip()
                        break
        except Exception:
            pass

    schema = {chapter_name: {}}
    for concept in topology['concepts']:
        concept_name = concept['name']
        subconcept_names = [sub['name'] for sub in concept['subconcepts']]
        schema[chapter_name][concept_name] = subconcept_names

    return schema


def print_summary(topology: dict, line_ranges: dict, illustrations: list):
    """Print human-readable summary."""
    print("=" * 80)
    print("COMPETITIVE TOPOLOGY SUMMARY")
    print("=" * 80)

    total_subs = 0
    connecting_count = 0

    for concept in topology['concepts']:
        tag = " [CONNECTING]" if concept['is_connecting_topic'] else ""
        print(f"\n{concept['id']}: {concept['name']}{tag}")
        for sub in concept['subconcepts']:
            lr = line_ranges[sub['id']]
            d = lr['density']
            total_subs += 1
            if sub['is_connecting_topic']:
                connecting_count += 1
            tag = " [CONNECTING]" if sub['is_connecting_topic'] else ""
            print(f"    {sub['id']}: {sub['name']}{tag}")
            print(f"        Tier: {sub['tier']} | Lines: {lr['line_start']}-{lr['line_end']} ({d['line_count']} lines) | Formulas: {d['formulas']} | Figs: {d['figures']} | Illustrations: {d['illustrations']}")

    print(f"\n{'=' * 80}")
    print(f"TOTAL: {len(topology['concepts'])} concepts, {total_subs} subconcepts")
    print(f"  Connecting topics (competitive-only): {connecting_count}")
    print(f"  Illustrations (solved examples): {len(illustrations)}")
    print(f"  Theory ends at line: {topology['exercises_start_line']}")
    print(f"{'=' * 80}")


if __name__ == '__main__':
    mmd_path = sys.argv[1] if len(sys.argv) > 1 else 'experiments/01_ocr_benchmarks/mathpix/ch01_light_competitive/ch01_light_competitive.mmd'
    output_dir = sys.argv[2] if len(sys.argv) > 2 else 'experiments/03_topology_generation/competitive'

    topology, line_ranges, illustrations = extract_topology(mmd_path)
    schema = build_schema(topology)

    # Save all JSONs
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    with open(f'{output_dir}/comp_schema.json', 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    with open(f'{output_dir}/comp_topology.json', 'w', encoding='utf-8') as f:
        json.dump(topology, f, indent=2, ensure_ascii=False)

    with open(f'{output_dir}/comp_line_ranges.json', 'w', encoding='utf-8') as f:
        json.dump(line_ranges, f, indent=2, ensure_ascii=False)

    with open(f'{output_dir}/comp_illustrations.json', 'w', encoding='utf-8') as f:
        json.dump(illustrations, f, indent=2, ensure_ascii=False)

    print_summary(topology, line_ranges, illustrations)

    print(f"\n--- SCHEMA (Database-ready) ---")
    print(json.dumps(schema, indent=2, ensure_ascii=False))
    print(f"\nSaved: {output_dir}/comp_schema.json")
    print(f"Saved: {output_dir}/comp_topology.json")
    print(f"Saved: {output_dir}/comp_line_ranges.json")
    print(f"Saved: {output_dir}/comp_illustrations.json ({len(illustrations)} illustrations)")
