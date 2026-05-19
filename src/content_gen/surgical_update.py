"""
Surgical Schema Corrections — Update ONLY specific fields without touching the rest.

Takes a proofreading report or manual instruction and applies targeted fixes
to specific JSON paths in the content file.

Usage:
  # From proofreading report (batch)
  python src/content_gen/surgical_update.py --report ch09_proofread_report.json --auto

  # Single field fix (manual)
  python src/content_gen/surgical_update.py --path "Subconcept: Reflection Of Light/Summary/Theory" --instruction "Remove AI filler phrases"
"""
import json, os, sys, time, argparse, shutil
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from google import genai
from google.genai import types

BASE = os.path.join(os.path.dirname(__file__), '..', '..')

api_key = os.environ.get('GEMINI_API_KEY', '')
if not api_key:
    print("ERROR: Set GEMINI_API_KEY")
    sys.exit(1)

client = genai.Client(api_key=api_key)
MODEL = "gemini-3-flash-preview"

CORRECTION_PROMPT = r"""You are editing CBSE Class 10 Science study material. Apply the correction below to the text.

RULES:
- Make ONLY the requested change. Do not rewrite, add, or remove anything else.
- Preserve all LaTeX notation: \(...\) for inline, \[...\] for display
- Preserve all formatting: **bold**, numbered lists, bullet points
- Preserve all image references (IMG_C2.S5_1 etc.)
- Keep the same length and tone — just fix the specific issue
- Return ONLY the corrected text, nothing else (no explanation, no quotes)

ORIGINAL TEXT:
{original}

CORRECTION INSTRUCTION:
{instruction}

CORRECTED TEXT:"""


def navigate_json(data, path_parts):
    """Navigate nested JSON by key path. Returns (parent, key, value) or None."""
    current = data
    for i, part in enumerate(path_parts[:-1]):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    final_key = path_parts[-1]
    if isinstance(current, dict) and final_key in current:
        return current, final_key, current[final_key]
    return None


def apply_correction(original_text, instruction):
    """Call LLM to apply a specific correction to text."""
    prompt = CORRECTION_PROMPT.format(original=original_text[:2000], instruction=instruction)
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=2000,
            thinking_config=types.ThinkingConfig(thinking_budget=256),
        )
    )
    return response.text.strip()


def surgical_update(content_path, json_path, instruction, dry_run=False):
    """Apply a single surgical correction to a specific JSON path."""
    with open(content_path, 'r', encoding='utf-8') as f:
        content = json.load(f)

    # Parse path: "Concept: .../Subconcept: .../SCQs/Question 1/Solution"
    path_parts = [p.strip() for p in json_path.split('/')]
    result = navigate_json(content, path_parts)

    if result is None:
        print(f"  ERROR: Path not found: {json_path}")
        return None

    parent, key, original_text = result

    if not isinstance(original_text, str):
        print(f"  ERROR: Value at path is not a string (type: {type(original_text).__name__})")
        return None

    print(f"  Original ({len(original_text)} chars): {original_text[:80]}...")
    print(f"  Instruction: {instruction}")

    if dry_run:
        print(f"  [DRY RUN — no changes applied]")
        return None

    # Apply correction via LLM
    corrected = apply_correction(original_text, instruction)
    print(f"  Corrected ({len(corrected)} chars): {corrected[:80]}...")

    # Verify correction is reasonable (not empty, not drastically different length)
    if len(corrected) < len(original_text) * 0.3:
        print(f"  WARNING: Correction is much shorter than original. Skipping.")
        return None
    if len(corrected) > len(original_text) * 3:
        print(f"  WARNING: Correction is much longer than original. Skipping.")
        return None

    # Apply
    parent[key] = corrected

    # Save
    with open(content_path, 'w', encoding='utf-8') as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

    return {
        'path': json_path,
        'instruction': instruction,
        'original': original_text,
        'corrected': corrected,
        'timestamp': datetime.now().isoformat(),
    }


def batch_from_report(content_path, report_path, dry_run=False, severity_filter=None):
    """Apply corrections from a proofreading report."""
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)

    if severity_filter:
        report = [r for r in report if r.get('severity') in severity_filter]

    print(f"Processing {len(report)} issues from report...")
    print(f"Severity filter: {severity_filter or 'all'}")

    # Group issues by location (apply all fixes to same field at once)
    by_location = {}
    for issue in report:
        loc = issue.get('location', '')
        if loc not in by_location:
            by_location[loc] = []
        by_location[loc].append(issue)

    changelog = []
    for loc, issues in by_location.items():
        instructions = '; '.join(
            f"Replace '{i.get('text_snippet', '')}' with '{i.get('suggestion', '')}'"
            for i in issues if i.get('suggestion')
        )
        if not instructions:
            continue

        print(f"\n--- {loc} ({len(issues)} issues) ---")
        result = surgical_update(content_path, loc, instructions, dry_run=dry_run)
        if result:
            changelog.append(result)

    # Save changelog
    if changelog:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_path = os.path.join(BASE, f'experiments/05_content_generation/ch09_corrections_log_{ts}.json')
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(changelog, f, ensure_ascii=False, indent=2)
        print(f"\nChangelog saved: {log_path}")
        print(f"Total corrections applied: {len(changelog)}")

    return changelog


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Surgical schema corrections')
    parser.add_argument('--report', help='Path to proofreading report JSON')
    parser.add_argument('--path', help='JSON path for single correction')
    parser.add_argument('--instruction', help='Correction instruction for single fix')
    parser.add_argument('--severity', nargs='+', default=None, help='Filter by severity: low medium high')
    parser.add_argument('--dry-run', action='store_true', help='Preview without applying')
    args = parser.parse_args()

    content_path = os.path.join(BASE, 'experiments/05_content_generation/ch09_final_content.json')

    # Backup before any modifications
    if not args.dry_run:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = content_path.replace('.json', f'_pre_surgery_{ts}.json')
        shutil.copy2(content_path, backup)
        print(f"Backup: {backup}")

    if args.report:
        batch_from_report(content_path, args.report, dry_run=args.dry_run, severity_filter=args.severity)
    elif args.path and args.instruction:
        result = surgical_update(content_path, args.path, args.instruction, dry_run=args.dry_run)
        if result:
            print(f"\nCorrection applied successfully.")
    else:
        parser.print_help()
