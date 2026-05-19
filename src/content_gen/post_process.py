"""
Post-processing for generated content.

1. Replace image codes (IMG_C2.S5_1) with natural language ("the figure below")
2. Strip any NCERT figure/table numbers (Figure 9.9, Table 9.3) from displayed text
3. Keep image codes in metadata fields (source_image_ref) for internal pipeline use
4. Validate LaTeX delimiters
"""

import re
import json


def post_process_content(content: dict) -> dict:
    """
    Post-process generated content.
    Modifies text fields only — metadata fields (source_image_ref) preserved.
    """
    # Serialize to string for text-level replacements
    content_str = json.dumps(content, ensure_ascii=False)

    # Step 1: Replace image codes in TEXT fields (not in source_image_ref)
    # The pattern: image codes appear in theory, question, solution text
    # But also in "source_image_ref": "IMG_C2.S5_1" — we must NOT touch those

    # Strategy: replace only in text values, not in the source_image_ref key
    # Split approach: handle source_image_ref separately

    # First protect source_image_ref values
    protected = {}
    for i, match in enumerate(re.finditer(r'"source_image_ref"\s*:\s*"(IMG_C\d+\.S\d+_\d+)"', content_str)):
        placeholder = f"__PROTECTED_IMG_REF_{i}__"
        protected[placeholder] = match.group(0)
        content_str = content_str.replace(match.group(0), placeholder, 1)

    # Now replace all image codes in remaining text
    def _replace(m):
        context = m.group(0)
        if 'as shown in' in context.lower() or 'shown in' in context.lower():
            return re.sub(r'IMG_C\d+\.S\d+_\d+', 'the figure below', context)
        elif '(' in context:
            return re.sub(r'IMG_C\d+\.S\d+_\d+', 'see the figure below', context)
        else:
            return re.sub(r'IMG_C\d+\.S\d+_\d+', 'the figure below', context)

    content_str = re.sub(r'.{0,20}IMG_C\d+\.S\d+_\d+.{0,5}', _replace, content_str)

    # Restore protected references
    for placeholder, original in protected.items():
        content_str = content_str.replace(placeholder, original)

    # Step 1.5: Auto-fix LaTeX delimiters ($...$ → \(...\), $$...$$ → \[...\])
    # Protect source_image_ref and other metadata fields first (already protected above)
    # Fix display math first ($$...$$)
    content_str = re.sub(r'\$\$([^$]+)\$\$', r'\\[\1\\]', content_str)
    # Fix inline math ($...$) — but not currency or already-escaped
    content_str = re.sub(r'(?<!\\)\$(?!\$)([^$]+?)(?<!\\)\$(?!\$)', r'\\(\1\\)', content_str)

    # Step 2: Strip NCERT figure/table numbers from text
    # "Figure 9.9" -> "the figure", "Table 9.3" -> "the table"
    # But only in text values, not in metadata
    content_str = re.sub(r'(?:as shown in |shown in |see |refer to )?(Figure|Fig\.?)\s+\d+\.?\d*(?:\s*\([a-z]\))?', 'the figure', content_str, flags=re.IGNORECASE)
    content_str = re.sub(r'(Table)\s+\d+\.?\d*', 'the table', content_str, flags=re.IGNORECASE)

    # Step 3: Clean up double references
    content_str = content_str.replace('the the figure', 'the figure')
    content_str = content_str.replace('in in the figure', 'in the figure')

    return json.loads(content_str)


def validate_scq_options(content: dict) -> list:
    """Validate that every SCQ has complete options (A)(B)(C)(D) in question text."""
    failures = []
    for i, scq in enumerate(content.get('scqs', [])):
        q = scq.get('question', '')
        fmt = scq.get('scq_format', 'standard')

        if fmt == 'assertion_reason':
            # Must have the 4 evaluation options
            if 'Both A and R are true' not in q and 'both A and R' not in q.lower():
                failures.append({
                    'index': i,
                    'format': fmt,
                    'issue': 'Assertion-Reason evaluation options (A)(B)(C)(D) missing',
                })
        else:
            # Must have (A), (B), (C), (D)
            has_a = bool(re.search(r'\(A\)', q))
            has_b = bool(re.search(r'\(B\)', q))
            has_c = bool(re.search(r'\(C\)', q))
            has_d = bool(re.search(r'\(D\)', q))
            if not (has_a and has_b and has_c and has_d):
                missing = [l for l, present in [('A', has_a), ('B', has_b), ('C', has_c), ('D', has_d)] if not present]
                failures.append({
                    'index': i,
                    'format': fmt,
                    'issue': f'Missing options: ({"), (".join(missing)})',
                })

    return failures


def validate_latex(content: dict) -> dict:
    """Validate LaTeX delimiters in generated content."""
    content_str = json.dumps(content, ensure_ascii=False)

    checks = {
        'uses_inline_parens': bool(re.search(r'\\\(', content_str)),
        'uses_display_brackets': bool(re.search(r'\\\[', content_str)),
        'uses_dollar_sign': bool(re.search(r'(?<!\\)\$(?!\$)', content_str)),
        'has_image_codes_in_text': bool(re.search(r'IMG_C\d+\.S\d+_\d+', re.sub(r'"source_image_ref"\s*:\s*"[^"]*"', '', content_str))),
        'has_ncert_figure_numbers': bool(re.search(r'Figure\s+\d+\.?\d+', content_str)),
    }

    checks['latex_compliant'] = checks['uses_inline_parens'] and not checks['uses_dollar_sign']
    checks['image_codes_clean'] = not checks['has_image_codes_in_text']
    checks['ncert_refs_clean'] = not checks['has_ncert_figure_numbers']

    return checks


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    with open('experiments/05_content_generation/C2.S5_FINAL_3.1pro_HIGH.json', 'r') as f:
        data = json.load(f)

    processed = post_process_content(data['content'])
    checks = validate_latex(processed)

    print("=== POST-PROCESSED CONTENT ===")
    print(json.dumps(processed, indent=2, ensure_ascii=False)[:2000])

    print(f"\n=== VALIDATION ===")
    for k, v in checks.items():
        status = 'PASS' if v else 'FAIL'
        if k in ('uses_dollar_sign', 'has_image_codes_in_text', 'has_ncert_figure_numbers'):
            status = 'PASS' if not v else 'FAIL'
        print(f"  {k}: {status}")
