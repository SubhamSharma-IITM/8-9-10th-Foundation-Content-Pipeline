"""
Inject NCERT solved example solutions into ch09_final_content.json.
These 4 examples were missed in the solution generation pass.
Solutions extracted from ch09_mathpix.mmd OCR source.
"""
import json, os, sys, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.join(os.path.dirname(__file__), '..')
content_path = os.path.join(BASE, 'experiments/05_content_generation/ch09_final_content.json')

with open(content_path, 'r', encoding='utf-8') as f:
    content = json.load(f)

# Convert MathPix LaTeX: $...$ -> \(...\), $$...$$ -> \[...\]
def convert_latex(text):
    # Display math first ($$...$$)
    text = re.sub(r'\$\$(.*?)\$\$', r'\\[\1\\]', text, flags=re.DOTALL)
    # Inline math ($...$)
    text = re.sub(r'\$(.+?)\$', r'\\(\1\\)', text)
    return text

# Solutions from ch09_mathpix.mmd, pre-converted
solutions = {
    # Example 9.1: Convex mirror, R=3.00m
    "convex mirror used for rear-view": {
        "Solution": convert_latex(
            "**Given:**\n"
            "Radius of curvature, $R = +3.00$ m\n"
            "Object-distance, $u = -5.00$ m\n\n"
            "**Focal length:**\n"
            "$f = R/2 = +3.00/2 = +1.50$ m (principal focus of convex mirror is behind the mirror)\n\n"
            "**Using mirror formula:**\n"
            "$\\frac{1}{v} + \\frac{1}{u} = \\frac{1}{f}$\n\n"
            "$\\frac{1}{v} = \\frac{1}{f} - \\frac{1}{u} = \\frac{1}{1.50} - \\frac{1}{(-5.00)} = \\frac{1}{1.50} + \\frac{1}{5.00}$\n\n"
            "$\\frac{1}{v} = \\frac{5.00 + 1.50}{7.50}$\n\n"
            "$v = +1.15$ m\n\n"
            "The image is 1.15 m at the back of the mirror.\n\n"
            "**Magnification:**\n"
            "$m = \\frac{h'}{h} = -\\frac{v}{u} = -\\frac{1.15}{-5.00} = +0.23$\n\n"
            "The image is **virtual, erect and smaller** in size by a factor of 0.23."
        ),
        "Answer": "v = +1.15 m, m = +0.23",
        "answer_format": "numerical"
    },
    # Example 9.2: Concave mirror, h=4cm, u=-25cm, f=-15cm
    "object, 4.0 cm in size": {
        "Solution": convert_latex(
            "**Given:**\n"
            "Object-size, $h = +4.0$ cm\n"
            "Object-distance, $u = -25.0$ cm\n"
            "Focal length, $f = -15.0$ cm\n\n"
            "**Using mirror formula:**\n"
            "$\\frac{1}{v} + \\frac{1}{u} = \\frac{1}{f}$\n\n"
            "$\\frac{1}{v} = \\frac{1}{f} - \\frac{1}{u} = \\frac{1}{-15.0} - \\frac{1}{-25.0} = -\\frac{1}{15.0} + \\frac{1}{25.0}$\n\n"
            "$\\frac{1}{v} = \\frac{-5.0 + 3.0}{75.0} = \\frac{-2.0}{75.0}$\n\n"
            "$v = -37.5$ cm\n\n"
            "The screen should be placed at **37.5 cm in front of the mirror**. The image is **real**.\n\n"
            "**Magnification:**\n"
            "$m = \\frac{h'}{h} = -\\frac{v}{u}$\n\n"
            "$h' = -\\frac{v \\times h}{u} = -\\frac{(-37.5)(+4.0)}{(-25.0)}$\n\n"
            "Height of the image, $h' = -6.0$ cm\n\n"
            "The image is **inverted and enlarged**."
        ),
        "Answer": "v = -37.5 cm, h' = -6.0 cm",
        "answer_format": "numerical"
    },
    # Example 9.3: Concave lens, f=-15cm, v=-10cm
    "concave lens has focal length of 15 cm": {
        "Solution": convert_latex(
            "A concave lens always forms a virtual, erect image on the same side of the object.\n\n"
            "**Given:**\n"
            "Image-distance $v = -10$ cm\n"
            "Focal length $f = -15$ cm\n\n"
            "**Using lens formula:**\n"
            "$\\frac{1}{v} - \\frac{1}{u} = \\frac{1}{f}$\n\n"
            "$\\frac{1}{u} = \\frac{1}{v} - \\frac{1}{f} = \\frac{1}{-10} - \\frac{1}{(-15)} = -\\frac{1}{10} + \\frac{1}{15}$\n\n"
            "$\\frac{1}{u} = \\frac{-3 + 2}{30} = \\frac{-1}{30}$\n\n"
            "$u = -30$ cm\n\n"
            "The object should be placed at **30 cm from the lens**.\n\n"
            "**Magnification:**\n"
            "$m = \\frac{v}{u} = \\frac{-10}{-30} = +\\frac{1}{3} \\approx +0.33$\n\n"
            "The positive sign shows that the image is **erect and virtual**. The image is one-third of the size of the object."
        ),
        "Answer": "u = -30 cm, m = +0.33",
        "answer_format": "numerical"
    },
    # Example 9.4: Convex lens, f=10cm, u=-15cm, h=2cm
    "2.0 cm tall object is placed perpendicular": {
        "Solution": convert_latex(
            "**Given:**\n"
            "Height of the object $h = +2.0$ cm\n"
            "Focal length $f = +10$ cm\n"
            "Object-distance $u = -15$ cm\n\n"
            "**Using lens formula:**\n"
            "$\\frac{1}{v} - \\frac{1}{u} = \\frac{1}{f}$\n\n"
            "$\\frac{1}{v} = \\frac{1}{u} + \\frac{1}{f} = \\frac{1}{(-15)} + \\frac{1}{10} = -\\frac{1}{15} + \\frac{1}{10}$\n\n"
            "$\\frac{1}{v} = \\frac{-2 + 3}{30} = \\frac{1}{30}$\n\n"
            "$v = +30$ cm\n\n"
            "The image is formed at **30 cm on the other side** of the optical centre. The image is **real and inverted**.\n\n"
            "**Magnification and image height:**\n"
            "$m = \\frac{h'}{h} = \\frac{v}{u}$\n\n"
            "$h' = h \\times (v/u) = 2.0 \\times (+30/-15) = -4.0$ cm\n\n"
            "$m = \\frac{v}{u} = \\frac{+30}{-15} = -2$\n\n"
            "The negative signs of $m$ and $h'$ show that the image is **inverted and real**. "
            "A real, inverted image, 4 cm tall, is formed at 30 cm on the other side of the lens. The image is **two times enlarged**."
        ),
        "Answer": "v = +30 cm, h' = -4.0 cm, m = -2",
        "answer_format": "numerical"
    },
}

# Find and inject solutions
updated = 0
for concept_key, subconcepts in content.items():
    for sub_key, sub_data in subconcepts.items():
        examples = sub_data.get('Examples', {})
        for ex_key, ex in examples.items():
            if ex.get('_source') != 'ncert' and not ex.get('isFromNCERT'):
                continue
            if ex.get('Solution') and ex['Solution'].strip():
                continue  # Already has a solution

            q_text = ex.get('Question', '')
            for match_str, sol_data in solutions.items():
                if match_str in q_text.lower() or match_str in q_text:
                    ex['Solution'] = sol_data['Solution']
                    ex['Answer'] = sol_data['Answer']
                    ex['answer_format'] = sol_data['answer_format']
                    updated += 1
                    print(f"  Injected solution for {sub_key} / {ex_key}: {q_text[:60]}...")
                    break

if updated > 0:
    with open(content_path, 'w', encoding='utf-8') as f:
        json.dump(content, f, ensure_ascii=False, indent=2)
    print(f"\nUpdated {updated} NCERT example solutions in ch09_final_content.json")
else:
    print("No examples needed updating")
