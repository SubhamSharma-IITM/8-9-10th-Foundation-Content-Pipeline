"""
Topology Extractor — Deterministic concept/subconcept extraction from MathPix MMD.

Produces two JSONs:
1. topology.json — concepts + subconcepts with names, tiers, image refs
2. line_ranges.json — line ranges, content density, back exercise slots

No model needed. Pure regex + density rules.
"""

import re
import json
import sys
from pathlib import Path


def parse_sections(lines: list[str]) -> list[dict]:
    """
    Parse ONLY real NCERT structural sections from MathPix MMD.

    Real sections have NCERT numbering like "9.1", "9.2.1", etc.
    Everything else (Activity, Solution, Example, Magnification, Uses of...)
    is an inline header that MathPix promoted to \section* — skip these.

    The chapter title (\section*{chapter N ...}) is captured as the root.
    """
    sections = []
    for i, line in enumerate(lines):
        m = re.search(r'\\(sub)?section\*\{(.+?)\}', line)
        if not m:
            continue

        is_sub = m.group(1) is not None
        title = m.group(2).strip()
        # Clean title: remove \\ linebreaks
        title = re.sub(r'\s*\\\\\s*', ' ', title)

        # Classify: is this a REAL structural section?
        # Real sections have NCERT numbering: "9.1 ...", "9.2.1 ...", etc.
        has_ncert_number = bool(re.match(r'^\d+\.\d+', title))
        is_chapter_title = title.lower().startswith('chapter ')

        if has_ncert_number:
            # Determine hierarchy level from numbering
            num_match = re.match(r'^(\d+)\.(\d+)(\.(\d+))?\s+', title)
            if num_match:
                level = 'subsection' if num_match.group(3) else 'section'
            else:
                level = 'subsection' if is_sub else 'section'

            sections.append({
                'line': i + 1,
                'title': title,
                'level': level,  # 'section' for 9.1, 9.2; 'subsection' for 9.2.1, 9.3.2
                'raw_line': line.strip(),
            })
        elif is_chapter_title:
            sections.append({
                'line': i + 1,
                'title': title,
                'level': 'chapter',
                'raw_line': line.strip(),
            })

    return sections


def classify_section(title: str) -> str:
    """Classify a section as content, activity, question, exercise, or meta."""
    t = title.strip().upper()
    if t.startswith('ACTIVITY'):
        return 'activity'
    if 'Q U E S T I O N' in t or 'QUESTIONS' in t:
        return 'intext_questions'
    if 'E X E R C I S E' in t or 'EXERCISES' in t:
        return 'back_exercises'
    if 'WHAT YOU HAVE' in t or 'HAVE LEARNT' in t:
        return 'summary'
    if t.startswith('MORE TO KNOW') or t.startswith('DO YOU KNOW'):
        return 'extra_info'
    if re.match(r'^EXAMPLE \d', t):
        return 'solved_example'
    if re.match(r'^TABLE \d', t):
        return 'table'
    return 'content'


def measure_density(lines: list[str], start: int, end: int) -> dict:
    """Measure content density for a line range."""
    block = '\n'.join(lines[start - 1:end - 1])
    return {
        'line_count': end - start,
        'formulas': len(re.findall(r'\\frac\{', block)) + block.count('$$') // 2,
        'figures': block.count('includegraphics'),
        'tables': block.count('\\begin{table}'),
        'activities': len(re.findall(r'Activity \d+\.\d+', block)),
        'solved_examples': len(re.findall(r'Example \d+\.\d+', block)),
        'images_md': block.count('!['),
    }


def extract_image_refs(lines: list[str], start: int, end: int) -> list[dict]:
    """Extract image references (both markdown and LaTeX) within a line range."""
    images = []
    for i in range(start - 1, min(end - 1, len(lines))):
        line = lines[i]
        # Markdown images
        for m in re.finditer(r'!\[(.*?)\]\((.*?)\)', line):
            images.append({
                'type': 'markdown',
                'alt': m.group(1),
                'url': m.group(2),
                'line': i + 1,
            })
        # LaTeX includegraphics
        if 'includegraphics' in line:
            url_m = re.search(r'\{(https?://.*?)\}', line)
            if url_m:
                images.append({
                    'type': 'latex_figure',
                    'url': url_m.group(1),
                    'line': i + 1,
                })
        # Check next few lines for caption
        if 'caption{' in line or 'caption{' in (lines[i + 1] if i + 1 < len(lines) else ''):
            cap_m = re.search(r'\\caption\{(.+?)\}', line + (lines[i + 1] if i + 1 < len(lines) else ''))
            if cap_m and images:
                images[-1]['caption'] = cap_m.group(1).strip()
    return images


def clean_section_name(title: str) -> str:
    """Remove NCERT section numbers like '9.1', '9.2.1' from title."""
    # Remove leading number patterns: "9.1 ", "9.2.1 ", etc.
    cleaned = re.sub(r'^\d+\.\d+(\.\d+)?\s+', '', title)
    # Remove ALL CAPS formatting artifacts
    cleaned = cleaned.strip()
    # Title case if ALL CAPS
    if cleaned == cleaned.upper() and len(cleaned) > 3:
        cleaned = cleaned.title()
    return cleaned


def find_exercises_line(lines: list[str]) -> int:
    """Find where back exercises section starts."""
    for i, line in enumerate(lines):
        if 'E X E R C I S E' in line or ('section' in line and 'EXERCISES' in line.upper()):
            return i + 1
    return len(lines) + 1


def extract_topology(mmd_path: str) -> tuple[dict, dict]:
    """
    Main extractor. Returns (topology_json, line_ranges_json).

    Logic:
    - Chapter intro (before 9.1) + 9.1 → merged into Concept 1 (thin, recap)
    - 9.2, 9.3 → Concepts with subsections as subconcepts
    - Subsections with < 10 lines + no formulas/figures → merge into adjacent
    - Each section's line range extends to the NEXT structural section
      (ignoring Activity/Example/Solution inline headers)
    """
    with open(mmd_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    total_lines = len(lines)
    exercises_line = find_exercises_line(lines)
    all_sections = parse_sections(lines)

    # Calculate line ranges: each section extends to the next structural section
    # (structural = only sections in our parsed list, NOT MathPix artifacts)
    for j in range(len(all_sections)):
        start = all_sections[j]['line']
        if j + 1 < len(all_sections):
            end = all_sections[j + 1]['line']
        else:
            end = exercises_line  # Content ends at exercises
        all_sections[j]['end_line'] = end
        all_sections[j]['density'] = measure_density(lines, start, end)
        all_sections[j]['images'] = extract_image_refs(lines, start, end)

    # Separate into hierarchy levels
    chapter_header = [s for s in all_sections if s['level'] == 'chapter']
    top_sections = [s for s in all_sections if s['level'] == 'section']  # 9.1, 9.2, 9.3
    sub_sections = [s for s in all_sections if s['level'] == 'subsection']  # 9.2.1, 9.2.2, etc.

    # Build concepts
    concepts = []

    # Concept for chapter intro + first top section (if it's a recap like 9.1)
    # Check if first top section is thin (recap section)
    intro_start = 1
    first_concept_subs = []

    for i, top in enumerate(top_sections):
        concept_name = clean_section_name(top['title'])

        # Find subsections belonging to this top-level section
        next_top_line = top_sections[i + 1]['line'] if i + 1 < len(top_sections) else exercises_line
        my_subs = [s for s in sub_sections if top['line'] < s['line'] < next_top_line]

        subconcepts = []
        if my_subs:
            for sub in my_subs:
                sub_name = clean_section_name(sub['title'])
                density = sub['density']
                lc = density['line_count']
                tier = ('thin_merge_candidate' if lc < 10 and density['formulas'] == 0 and density['figures'] == 0
                        else 'rich' if lc >= 40
                        else 'medium' if lc >= 15
                        else 'thin')
                subconcepts.append({
                    'ncert_section': sub['title'],
                    'name': sub_name,
                    'line_start': sub['line'],
                    'line_end': sub['end_line'],
                    'density': density,
                    'tier': tier,
                    'images': sub['images'],
                })

            # Include concept intro (top-level content before first subsection)
            first_sub_line = my_subs[0]['line']
            intro_density = measure_density(lines, top['line'], first_sub_line)
            if intro_density['line_count'] > 3:
                # Meaningful intro: add as first subconcept
                subconcepts.insert(0, {
                    'ncert_section': top['title'] + ' (Introduction)',
                    'name': concept_name + ' - Introduction',
                    'line_start': top['line'],
                    'line_end': first_sub_line,
                    'density': intro_density,
                    'tier': 'thin' if intro_density['line_count'] < 15 else 'medium',
                    'images': extract_image_refs(lines, top['line'], first_sub_line),
                })
        else:
            # No subsections — the section itself is the only subconcept
            density = top['density']
            lc = density['line_count']
            tier = 'thin' if lc < 15 else ('medium' if lc < 40 else 'rich')

            # Check if this is a thin recap section that should merge with chapter intro
            if i == 0 and lc < 20:
                # Merge chapter intro + this section into one concept
                merged_start = intro_start
                subconcepts.append({
                    'ncert_section': top['title'],
                    'name': concept_name,
                    'line_start': merged_start,
                    'line_end': top['end_line'],
                    'density': measure_density(lines, merged_start, top['end_line']),
                    'tier': 'thin',
                    'images': extract_image_refs(lines, merged_start, top['end_line']),
                })
                concept_name = 'Basics of Light and Reflection'
            else:
                subconcepts.append({
                    'ncert_section': top['title'],
                    'name': concept_name,
                    'line_start': top['line'],
                    'line_end': top['end_line'],
                    'density': density,
                    'tier': tier,
                    'images': top['images'],
                })

        concepts.append({
            'ncert_section': top['title'],
            'name': concept_name,
            'subconcepts': subconcepts,
        })

    # Apply merge rules: thin_merge_candidate subconcepts merge into adjacent
    for concept in concepts:
        merged_subs = []
        skip_next = False
        subs = concept['subconcepts']
        for j in range(len(subs)):
            if skip_next:
                skip_next = False
                continue
            current = subs[j]
            if current['tier'] == 'thin_merge_candidate':
                # Merge into next subconcept if available, else previous
                if j + 1 < len(subs):
                    target = subs[j + 1]
                    target['name'] = current['name'] + ' + ' + target['name']
                    target['line_start'] = current['line_start']
                    target['density']['line_count'] += current['density']['line_count']
                    target['images'] = current['images'] + target['images']
                    target['tier'] = 'medium' if target['density']['line_count'] >= 15 else 'thin'
                    target['ncert_section'] = current['ncert_section'] + ' + ' + target['ncert_section']
                elif merged_subs:
                    target = merged_subs[-1]
                    target['name'] = target['name'] + ' + ' + current['name']
                    target['line_end'] = current['line_end']
                    target['density']['line_count'] += current['density']['line_count']
                    target['images'] = target['images'] + current['images']
                else:
                    merged_subs.append(current)
                    current['tier'] = 'thin'
            else:
                merged_subs.append(current)
        concept['subconcepts'] = merged_subs

    # Assign IDs
    for i, concept in enumerate(concepts):
        concept['id'] = f'C{i + 1}'
        for j, sub in enumerate(concept['subconcepts']):
            sub['id'] = f'C{i + 1}.S{j + 1}'

    # Build output JSONs
    topology = {
        'source_file': str(mmd_path),
        'total_lines': total_lines,
        'concepts': []
    }
    line_ranges = {}

    for concept in concepts:
        topo_concept = {
            'id': concept['id'],
            'name': concept['name'],
            'ncert_section': concept['ncert_section'],
            'subconcepts': []
        }
        for sub in concept['subconcepts']:
            topo_sub = {
                'id': sub['id'],
                'name': sub['name'],
                'tier': sub['tier'],
                'image_count': len(sub['images']),
            }
            topo_concept['subconcepts'].append(topo_sub)

            # Line ranges JSON
            line_ranges[sub['id']] = {
                'name': sub['name'],
                'ncert_section': sub['ncert_section'],
                'line_start': sub['line_start'],
                'line_end': sub['line_end'],
                'density': sub['density'],
                'images': [{'url': img.get('url', ''), 'caption': img.get('caption', ''), 'line': img.get('line', 0)} for img in sub['images']],
                'back_exercises': [],  # To be filled by back exercise mapper
                'generation_budget': {},  # To be filled by capacity formula
            }

        topology['concepts'].append(topo_concept)

    return topology, line_ranges


def print_summary(topology: dict, line_ranges: dict):
    """Print a human-readable summary."""
    print("=" * 80)
    print("TOPOLOGY SUMMARY")
    print("=" * 80)
    total_subs = 0
    for concept in topology['concepts']:
        print(f"\n{concept['id']}: {concept['name']}")
        print(f"    NCERT: {concept['ncert_section']}")
        for sub in concept['subconcepts']:
            lr = line_ranges[sub['id']]
            d = lr['density']
            total_subs += 1
            print(f"    {sub['id']}: {sub['name']}")
            print(f"        Tier: {sub['tier']} | Lines: {lr['line_start']}-{lr['line_end']} ({d['line_count']} lines)")
            print(f"        Formulas: {d['formulas']} | Figures: {d['figures']} | Tables: {d['tables']} | Activities: {d['activities']} | Examples: {d['solved_examples']}")
            if lr['images']:
                print(f"        Images: {len(lr['images'])}")

    print(f"\n{'=' * 80}")
    print(f"TOTAL: {len(topology['concepts'])} concepts, {total_subs} subconcepts")
    print(f"{'=' * 80}")


def build_schema(topology: dict) -> dict:
    """
    Build the database-ready schema JSON in reference format.

    Matches: acadza-history-demo/class9_history_chapter_1_topology.json
    Format: { "Chapter N: Title": { "Concept Name": ["Subconcept 1", "Subconcept 2", ...] } }

    This is the SCHEMA ONLY — no content populated.
    Content is populated per-subconcept in later pipeline stages.
    """
    # Extract chapter name: parse from the raw MMD first line or source file
    chapter_name = "Chapter"

    # Try to get from source file path
    src = topology.get('source_file', '')
    if src:
        # Read first few lines to find chapter title
        try:
            with open(src, 'r', encoding='utf-8') as f:
                for raw_line in f:
                    m = re.search(r'section\*\{(.+?)\}', raw_line)
                    if m:
                        title = m.group(1)
                        # Clean: "chapter 9 \\ Light - Reflection and \\ Refraction"
                        title = re.sub(r'\s*\\\\\s*', ' ', title).strip()
                        # Extract chapter number and name
                        cm = re.match(r'(?i)chapter\s*(\d+)\s*(.*)', title)
                        if cm:
                            ch_name = cm.group(2).strip(' -:')
                            chapter_name = ch_name
                        break
        except Exception:
            pass

    schema = {chapter_name: {}}

    for concept in topology['concepts']:
        concept_name = concept['name']
        subconcept_names = [sub['name'] for sub in concept['subconcepts']]
        schema[chapter_name][concept_name] = subconcept_names

    return schema


if __name__ == '__main__':
    import argparse
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(PROJECT_ROOT))
    from src.common import chapter_config
    from src.common.backup import safe_write_json
    from src.common.stage_validators import validate_topology_schema, validate_dual_topology

    parser = argparse.ArgumentParser(description='Regex topology extractor (FREE stage)')
    parser.add_argument('--chapter', help='Chapter key from chapter_config registry')
    parser.add_argument('mmd_path', nargs='?', help='Legacy: MMD path (used if --chapter omitted)')
    parser.add_argument('output_dir', nargs='?', help='Legacy: output dir')
    args = parser.parse_args()

    if args.chapter:
        cfg = chapter_config.load(args.chapter)
        mmd_path = str(cfg.mmd_path)
        cfg.topology_dir.mkdir(parents=True, exist_ok=True)
        schema_path = cfg.schema_path
        topology_path = cfg.topology_json_source_path
        line_ranges_path = cfg.line_ranges_path
    else:
        mmd_path = args.mmd_path or 'experiments/01_ocr_benchmarks/mathpix/ch09_light/ch09_mathpix.mmd'
        output_dir = Path(args.output_dir or 'experiments/03_topology_generation')
        output_dir.mkdir(parents=True, exist_ok=True)
        schema_path = output_dir / 'ch09_schema.json'
        topology_path = output_dir / 'ch09_topology.json'
        line_ranges_path = output_dir / 'ch09_line_ranges.json'

    print(f"\n=== Topology extraction ===")
    print(f"  MMD input  : {mmd_path}")
    print(f"  schema out : {schema_path}")
    print(f"  topo  out  : {topology_path}")
    print(f"  ranges out : {line_ranges_path}")

    topology, line_ranges = extract_topology(mmd_path)
    schema = build_schema(topology)

    # Snapshot + write all 3 outputs
    safe_write_json(schema_path, schema)
    safe_write_json(topology_path, topology)
    safe_write_json(line_ranges_path, line_ranges)

    print_summary(topology, line_ranges)
    print(f"\n--- SCHEMA (dual-format, database-ready) ---")
    print(json.dumps(schema, indent=2, ensure_ascii=False))

    # Run validators
    print("\n--- VALIDATORS ---")
    v1 = validate_dual_topology(schema_path)
    print(v1.report())
    v2 = validate_topology_schema(topology_path)
    print(v2.report())

    if not v1.ok or not v2.ok:
        print("\nVALIDATOR FAIL - downstream stages blocked until output is fixed")
        sys.exit(1)

    print(f"\nSaved: {schema_path}")
    print(f"Saved: {topology_path}")
    print(f"Saved: {line_ranges_path}")
