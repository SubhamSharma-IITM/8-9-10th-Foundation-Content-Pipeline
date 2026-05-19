"""Inspect exercise section structure in competitive MMD."""
import re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = 'D:/ACADZA_WORK/8-9-10th PIPELINE'

with open(f'{BASE}/experiments/01_ocr_benchmarks/mathpix/ch01_light_competitive/ch01_light_competitive.mmd', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print('=' * 70)
print('ALL SECTION HEADERS FROM LINE 1600 TO END')
print('=' * 70)

for i, line in enumerate(lines):
    s = line.strip()
    if i < 1600:
        continue
    m = re.match(r'^\\section\*\{(.+?)\}', s)
    if m:
        title = m.group(1)
        # Skip pure page artifacts
        if title.strip() in ['Physics', 'Note']:
            continue
        # Print every header with classification
        print(f'  L{i+1:4d}  {title[:85]}')
    elif re.match(r'^Exercise\s+\d', s) or 'Foundation Builder' in s and len(s) < 50:
        print(f'  L{i+1:4d}  [INLINE] {s[:85]}')
