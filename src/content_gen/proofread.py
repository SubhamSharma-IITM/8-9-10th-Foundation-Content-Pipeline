"""
AI Proofreading Pipeline — Detect AI slop, filler words, and factual errors.

Reads ch09_final_content.json, sends each Theory/Solution/Question text
to Gemini Flash for proofreading. Outputs a report — does NOT modify content.

Usage: GEMINI_API_KEY=xxx python src/content_gen/proofread.py
"""
import json, os, sys, time
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from google import genai
from google.genai import types

BASE = os.path.join(os.path.dirname(__file__), '..', '..')

PROOFREAD_PROMPT = r"""You are an experienced CBSE Class 10 Science teacher reviewing study material written for students.

Your job: flag content that sounds AI-generated, uses filler words, or contains factual errors.

WHAT TO FLAG:
1. **AI filler phrases**: "It is important to note that", "In conclusion", "This demonstrates that", "As we can see", "It should be noted", "Let us delve into", "Furthermore", "Moreover", "In essence"
2. **Overly formal/robotic tone**: Passive voice overuse, unnecessarily complex sentences, text that doesn't sound like a teacher explaining to a student
3. **Redundant statements**: Saying the same thing twice in different words
4. **Factual errors**: Incorrect physics/science facts, wrong formulas, incorrect sign conventions
5. **Out-of-scope content**: Information not relevant to the subconcept being discussed
6. **Missing clarity**: Places where a student would be confused

WHAT IS FINE (do NOT flag):
- Technical terms used correctly (focal length, refractive index, etc.)
- Step-by-step solution format (Given → Formula → Substitute → Answer)
- LaTeX math notation like \( f = R/2 \)
- Bold terms on first introduction
- Short, direct sentences

For each issue found, respond in this JSON array format:
[
  {
    "text_snippet": "exact problematic text (10-40 words)",
    "issue_type": "ai_filler | robotic_tone | redundant | factual_error | out_of_scope | unclear",
    "severity": "low | medium | high",
    "suggestion": "rewritten version or correction"
  }
]

If the content is clean and sounds natural, return an empty array: []

CONTENT TO REVIEW:
"""

api_key = os.environ.get('GEMINI_API_KEY', '')
if not api_key:
    print("ERROR: Set GEMINI_API_KEY")
    sys.exit(1)

client = genai.Client(api_key=api_key)
MODEL = "gemini-3-flash-preview"


def proofread_text(text, context_label):
    """Send text to Gemini for proofreading. Returns list of issues."""
    if not text or len(text.strip()) < 30:
        return []

    prompt = PROOFREAD_PROMPT + f"\n[{context_label}]\n{text}"

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=1000,
                thinking_config=types.ThinkingConfig(thinking_budget=256),
            )
        )
        issues = json.loads(response.text)
        if isinstance(issues, list):
            return issues
        return []
    except Exception as e:
        print(f"    ERROR: {e}")
        return []


def main():
    content_path = os.path.join(BASE, 'experiments/05_content_generation/ch09_final_content.json')
    with open(content_path, 'r', encoding='utf-8') as f:
        content = json.load(f)

    report = []
    total_texts = 0
    total_issues = 0
    start = time.time()

    print("=" * 60)
    print("AI PROOFREADING PIPELINE")
    print(f"Model: {MODEL}")
    print("=" * 60)

    for concept_key, subconcepts in content.items():
        for sub_key, sub_data in subconcepts.items():
            sub_name = sub_key.replace('Subconcept: ', '')
            print(f"\n--- {sub_name} ---")

            # Proofread Theory
            theory = sub_data.get('Summary', {}).get('Theory', '')
            if theory:
                label = f"Theory | {sub_name}"
                print(f"  Proofreading theory ({len(theory)} chars)...")
                issues = proofread_text(theory, label)
                total_texts += 1
                if issues:
                    total_issues += len(issues)
                    for issue in issues:
                        issue['location'] = f"{sub_key}/Summary/Theory"
                        issue['content_type'] = 'theory'
                    report.extend(issues)
                    print(f"    -> {len(issues)} issues found")
                else:
                    print(f"    -> Clean")

            # Proofread each question and solution
            for section in ['SCQs', 'SubjectiveTypes', 'Examples']:
                for key, item in sub_data.get(section, {}).items():
                    # Proofread question text
                    q_text = item.get('Question', '')
                    if q_text and len(q_text) > 50:
                        label = f"{section}/{key} Question | {sub_name}"
                        issues = proofread_text(q_text, label)
                        total_texts += 1
                        if issues:
                            total_issues += len(issues)
                            for issue in issues:
                                issue['location'] = f"{sub_key}/{section}/{key}/Question"
                                issue['content_type'] = 'question'
                            report.extend(issues)

                    # Proofread solution
                    sol = item.get('Solution', '')
                    if sol and len(sol) > 50:
                        label = f"{section}/{key} Solution | {sub_name}"
                        issues = proofread_text(sol, label)
                        total_texts += 1
                        if issues:
                            total_issues += len(issues)
                            for issue in issues:
                                issue['location'] = f"{sub_key}/{section}/{key}/Solution"
                                issue['content_type'] = 'solution'
                            report.extend(issues)

            # Progress indicator
            q_count = len(sub_data.get('SCQs', {})) + len(sub_data.get('SubjectiveTypes', {}))
            print(f"  Questions: {q_count} checked")

    elapsed = time.time() - start

    # Save report
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = os.path.join(BASE, f'experiments/05_content_generation/ch09_proofread_report_{timestamp}.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Summary
    print("\n" + "=" * 60)
    print("PROOFREADING COMPLETE")
    print("=" * 60)
    print(f"Texts reviewed: {total_texts}")
    print(f"Issues found:   {total_issues}")
    print(f"Time:           {elapsed:.1f}s")
    print(f"Report saved:   {report_path}")

    # Breakdown by type
    if report:
        by_type = {}
        by_severity = {}
        for r in report:
            t = r.get('issue_type', 'unknown')
            s = r.get('severity', 'unknown')
            by_type[t] = by_type.get(t, 0) + 1
            by_severity[s] = by_severity.get(s, 0) + 1

        print(f"\nBy issue type:")
        for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
            print(f"  {t}: {c}")
        print(f"\nBy severity:")
        for s, c in sorted(by_severity.items()):
            print(f"  {s}: {c}")


if __name__ == '__main__':
    main()
