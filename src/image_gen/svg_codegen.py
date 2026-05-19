"""
svg_codegen.py - LLM-generated SVG diagrams with sanitizer and cairosvg renderer.

Replaces matplotlib for textbook-quality schematic diagrams. SVG produces crisper
lines, better arrow markers, and cleaner typography than matplotlib defaults.

Pipeline:
  description -> LLM SVG codegen -> sanitize (tag allowlist, attr blocklist)
              -> cairosvg render to PNG -> output validation (size + pixel variance)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Tuple

# Tags allowed in our SVG output (everything else is stripped)
ALLOWED_TAGS = {
    "svg", "g", "defs", "marker", "pattern", "linearGradient", "radialGradient",
    "stop", "clipPath", "mask", "symbol", "use",
    "rect", "circle", "ellipse", "line", "path", "polygon", "polyline",
    "text", "tspan", "title", "desc",
}
# Tags that must be removed entirely (potential script/embed surface)
FORBIDDEN_TAGS = {"script", "foreignObject", "iframe", "embed", "object", "image", "video", "audio"}
# Attributes pattern for event handlers
EVENT_HANDLER_RE = re.compile(r"\s(on\w+)\s*=\s*(\"[^\"]*\"|'[^']*')", re.IGNORECASE)
# href/xlink:href to external (non-fragment) URLs
EXTERNAL_HREF_RE = re.compile(r"\s(xlink:)?href\s*=\s*(\"(?!#)[^\"]*\"|'(?!#)[^']*')", re.IGNORECASE)


SVG_SYSTEM_PROMPT = """You are a senior scientific illustrator producing SVG diagrams for an NCERT
Class 10 Science textbook published by NCERT Delhi. Your output goes directly to print and
digital editions read by 20+ million students. The quality bar is "published physics textbook
illustration" - not "screenshot of a quick sketch".

## OUTPUT FORMAT (non-negotiable)
- Output ONLY raw SVG markup, starting with `<svg ...>` and ending with `</svg>`.
- No markdown fences. No commentary. No XML declaration. No HTML wrapper.
- Set viewBox to give the diagram breathing room - typical: viewBox="0 0 900 600" with 60-80px margins on each side, viewBox="0 0 700 700" for square spatial diagrams.
- First child: `<rect width="100%" height="100%" fill="white"/>` (white background).
- Last child: a small caption `<text>` describing the diagram (font-size 14, fill="#444").

## ALLOWED ELEMENTS
svg, g, defs, marker, rect, circle, ellipse, line, path, polygon, polyline, text, tspan,
linearGradient, radialGradient, stop, pattern, title, desc.
FORBIDDEN: script, foreignObject, iframe, embed, object, image, video, audio, event handlers, external URLs.

## VISUAL LANGUAGE (NCERT physics convention)

### Color discipline
- Default: black lines on white (#000 on #FFF). Resist temptation to add colors.
- Magnet poles: N = #C0392B (textbook red), S = #2874A6 (textbook blue). Use #FFF text labels on the colored halves so N/S are unmissable.
- Current direction (I): #C0392B red arrow.
- Magnetic field direction (B): black or dark navy (#1B2A4A).
- Conductors/wires: black, stroke-width 3.
- Field lines: black, stroke-width 1.8-2.0 (thinner than wires so the visual hierarchy is clear).
- Cardboard/surface/table: light gray fill #ECECEC with #888 outline.
- Accent for emphasis (rare): #2C5282.

### Stroke widths (visual hierarchy)
- Primary objects (the magnet, the wire, the device): stroke-width 3.
- Secondary structure (axes, coordinate frames, surface outlines): stroke-width 1.5.
- Field lines / construction lines: stroke-width 1.8-2.
- Arrows on lines: same width as their parent line.
- Use `stroke-linecap="round"` on every line/path for smooth ends.

### Typography
- font-family="Arial, Helvetica, sans-serif" everywhere.
- Major axis labels (N, S, X, Y, P, A, B, C as points): font-size 24, font-weight="bold".
- Variable labels (B, F, I, v, theta) in physics convention: font-size 18, font-style="italic".
- Annotation text ("Magnetic Field Line", "Current Direction", "Compass needle"): font-size 14, regular.
- Caption (bottom of diagram): font-size 14, fill="#444", text-anchor="middle".
- Use `text-anchor="middle"` for labels centered on a point. Use `dominant-baseline="middle"` to center vertically.
- For labels next to a point, offset by 12-18 px in the direction away from the point.

### Arrows (this is where most diagrams fail)
Define in `<defs>` once:
```
<marker id="arrowhead" viewBox="0 0 12 12" markerWidth="10" markerHeight="10" refX="11" refY="6" orient="auto-start-reverse" markerUnits="strokeWidth">
  <path d="M0,1 L11,6 L0,11 z" fill="context-stroke"/>
</marker>
```
Use `marker-end="url(#arrowhead)"` on lines/paths that need a directional arrow at their END.
Use `marker-start="url(#arrowhead)"` for arrows pointing into a point.
For arrows in the MIDDLE of a long curve (field line direction indicators), draw a SHORT separate
line with marker-end positioned at the desired mid-curve location. Place arrows at 30%, 60% of
the curve length for long field lines.

### Smooth curves (for field lines, ray paths)
- Use `<path d="M x1 y1 C cx1 cy1, cx2 cy2, x2 y2"/>` (cubic Bezier) for natural-looking curves.
- Avoid sharp `<polyline>` for field lines - they look like wireframes.
- Symmetric field lines should be mirror-pair Beziers with reflected control points.
- For a magnetic field around a bar magnet: 3-4 field lines on the top half, 3-4 mirrored on bottom, plus a horizontal one through the magnet's axis if helpful.

### Spatial composition
- Center the main subject. Leave at least 50px margin on each side of the viewBox.
- For diagrams with directional context (e.g. "current downward through cardboard"), include a small XY compass or "this way up" indicator if helpful.
- For 3D-ish diagrams (wire through cardboard), draw the cardboard as a `<path>` parallelogram (top edge shorter / shifted right vs bottom edge) to suggest perspective.

## STRUCTURAL TEMPLATE (follow this order)
```
<svg viewBox="..." xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="white"/>
  <defs>
    <marker id="arrowhead" ...>...</marker>
    <!-- any patterns/gradients -->
  </defs>
  <!-- Layer 1: background structure (surfaces, axes) -->
  <!-- Layer 2: field lines or paths (drawn FIRST so the main object covers them where they meet) -->
  <!-- Layer 3: main object(s) (magnet, wire, lens, mirror, conductor) -->
  <!-- Layer 4: directional arrows on field lines (mid-curve) -->
  <!-- Layer 5: labels (N, S, B, I, text annotations) -->
  <!-- Layer 6: bottom caption -->
</svg>
```

## QUALITY CHECKLIST (silently audit before finishing)
- [ ] viewBox set with adequate margin
- [ ] White background rect
- [ ] Arrowhead marker defined in defs
- [ ] Every line/path has stroke and stroke-width set explicitly (no default 1px)
- [ ] Labels never overlap drawn elements
- [ ] N pole label is RED-colored or RED background, S pole label is BLUE-colored or BLUE background
- [ ] Field lines are smooth Bezier curves (not jagged polylines)
- [ ] Arrows present on lines that have direction (current, field, force, ray)
- [ ] Caption at the bottom describes the diagram in <= 8 words
- [ ] No element extends outside the viewBox

## ANTI-PATTERNS (do NOT do these)
- Don't use `<text>` with no font-size attribute (will render tiny by default).
- Don't use `<line>` for curves - use `<path>`.
- Don't omit `stroke-width` (default 1px looks anemic).
- Don't put labels directly ON TOP of drawn elements.
- Don't use markdown code fences. Don't add an `<?xml ...?>` declaration.
- Don't use colors not in the discipline above (no rainbow gradient field lines, no neon).
- Don't draw arrows as separate small triangle polygons - use proper `<marker>` definitions for consistent arrow style throughout the diagram."""


def build_user_prompt(
    description: str,
    image_code: str,
    chapter_name: str = "",
    subconcept_name: str = "",
    prev_error: str = "",
) -> str:
    """Build the per-diagram user prompt with chapter context for grounding."""
    parts = []
    if chapter_name or subconcept_name:
        parts.append("## CONTEXT")
        if chapter_name:
            parts.append(f"Chapter: {chapter_name}")
        if subconcept_name:
            parts.append(f"Subconcept: {subconcept_name}")
        parts.append("")
    parts.append("## DIAGRAM TO PRODUCE")
    parts.append(f"Code: {image_code}")
    parts.append("Description:")
    parts.append(description)
    parts.append("")
    parts.append("## INSTRUCTION")
    parts.append("Apply the full system-prompt style guide: NCERT physics convention, "
                 "color discipline (N=red #C0392B, S=blue #2874A6, field lines black), "
                 "stroke hierarchy (objects=3, lines=2, fields=1.8), Bezier curves for "
                 "field lines, proper <marker> arrowheads in <defs>, labels offset 12-18px "
                 "from the point they refer to, bottom caption. Run the quality checklist "
                 "silently before returning. Output ONLY the <svg>...</svg> markup.")
    msg = "\n".join(parts)
    if prev_error:
        msg += (
            f"\n\n## RETRY NOTE\nPrevious attempt failed with:\n{prev_error[:600]}\n\n"
            "Fix the issue and produce clean SVG. Common fixes:\n"
            "- ensure viewBox is set on the <svg> root\n"
            "- ensure </svg> closing tag is present\n"
            "- avoid forbidden tags (script, foreignObject, iframe, etc.)\n"
            "- avoid event handlers (onclick, onload)\n"
            "- avoid external URLs in href attributes"
        )
    return msg


def extract_svg(raw: str) -> str:
    """Pull <svg>...</svg> out of any LLM response, stripping fences/commentary."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    m = re.search(r"<svg[\s\S]*?</svg>", raw)
    return m.group(0) if m else raw


def sanitize_svg(svg: str) -> Tuple[str, list[str]]:
    """Remove dangerous tags/attrs. Returns (sanitized_svg, list_of_warnings)."""
    warnings: list[str] = []

    # 1. Strip forbidden tags (paired + self-closing)
    for tag in FORBIDDEN_TAGS:
        before = svg
        svg = re.sub(rf"<\s*{tag}\b[\s\S]*?</\s*{tag}\s*>", "", svg, flags=re.IGNORECASE)
        svg = re.sub(rf"<\s*{tag}\b[^>]*/?>", "", svg, flags=re.IGNORECASE)
        if svg != before:
            warnings.append(f"stripped <{tag}> tag(s)")

    # 2. Strip event handler attributes (onclick, onload, etc.)
    if EVENT_HANDLER_RE.search(svg):
        warnings.append("stripped event handler attributes")
        svg = EVENT_HANDLER_RE.sub("", svg)

    # 3. Strip external href/xlink:href (keep #fragment refs)
    if EXTERNAL_HREF_RE.search(svg):
        warnings.append("stripped external href attributes")
        svg = EXTERNAL_HREF_RE.sub("", svg)

    # 4. Inventory tags to confirm only allowed ones remain
    tags_found = set(t.lower() for t in re.findall(r"<\s*([a-zA-Z]+)", svg))
    not_allowed = tags_found - ALLOWED_TAGS
    if not_allowed:
        warnings.append(f"unfamiliar tags present (kept but flagged): {sorted(not_allowed)}")

    return svg, warnings


def validate_svg_root(svg: str) -> tuple[bool, str]:
    """Quick structural check before rendering."""
    if not svg.strip().startswith("<svg"):
        return False, "does not start with <svg"
    if "</svg>" not in svg:
        return False, "missing </svg> closing tag"
    if "viewBox" not in svg and "width" not in svg:
        return False, "no viewBox or width attribute on <svg> root"
    return True, ""


def render_svg_to_png(svg: str, output_path: Path, output_width: int = 1000) -> tuple[bool, str]:
    """Convert SVG markup to PNG via cairosvg. Returns (success, error_message)."""
    try:
        import cairosvg
    except ImportError:
        return False, "cairosvg not installed"
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cairosvg.svg2png(
            bytestring=svg.encode("utf-8"),
            write_to=str(output_path),
            output_width=output_width,
        )
        return True, ""
    except Exception as e:
        return False, f"cairosvg render error: {e}"


def validate_png_output(p: Path, min_bytes: int = 1024, min_pixel_std: float = 5.0) -> tuple[bool, list[str]]:
    """Same gate as matplotlib codegen: exists, PNG header, non-blank."""
    errs: list[str] = []
    if not p.exists():
        return False, [f"PNG missing: {p}"]
    if p.stat().st_size < min_bytes:
        errs.append(f"PNG too small: {p.stat().st_size} bytes")
        return False, errs
    head = p.read_bytes()[:8]
    if not head.startswith(b"\x89PNG\r\n\x1a\n"):
        errs.append("no PNG header")
        return False, errs
    try:
        from PIL import Image
        import numpy as np
        arr = np.array(Image.open(p).convert("RGB"))
        std = float(arr.std())
        if std < min_pixel_std:
            errs.append(f"PNG appears blank: pixel std={std:.2f}")
            return False, errs
    except ImportError:
        errs.append("PIL/numpy missing - skipped blank check")
    return True, errs


def codegen_svg_and_render(svg_raw: str, output_path: Path) -> tuple[bool, list[str], str]:
    """Full pipeline: extract -> sanitize -> structural-check -> render -> validate PNG.
    Returns (success, errors, sanitized_svg)."""
    errors: list[str] = []
    svg = extract_svg(svg_raw)
    svg, warns = sanitize_svg(svg)
    for w in warns:
        errors.append(f"[sanitize-warn] {w}")
    ok, msg = validate_svg_root(svg)
    if not ok:
        return False, errors + [f"[svg-root] {msg}"], svg
    ok, msg = render_svg_to_png(svg, output_path)
    if not ok:
        return False, errors + [f"[render] {msg}"], svg
    ok, errs = validate_png_output(output_path)
    if not ok:
        return False, errors + [f"[validate] {e}" for e in errs], svg
    return True, errors, svg


if __name__ == "__main__":
    # Sanitizer smoke tests
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=== TEST 1: clean SVG passes through ===")
    s = '<svg viewBox="0 0 100 100"><rect fill="white" width="100" height="100"/><line x1="10" y1="10" x2="90" y2="90" stroke="black"/></svg>'
    out, warns = sanitize_svg(s)
    print(f"  warns={warns}, length preserved: {len(out)==len(s)}")
    assert out == s, "clean SVG should pass through unchanged"

    print("\n=== TEST 2: script tag stripped ===")
    s = '<svg><script>alert(1)</script><rect/></svg>'
    out, warns = sanitize_svg(s)
    print(f"  warns={warns}")
    assert "script" not in out.lower()

    print("\n=== TEST 3: onclick stripped ===")
    s = '<svg><rect onclick="alert(1)" fill="red"/></svg>'
    out, warns = sanitize_svg(s)
    print(f"  warns={warns}")
    assert "onclick" not in out.lower()

    print("\n=== TEST 4: external href stripped ===")
    s = '<svg><a xlink:href="https://evil.com"><text>click</text></a></svg>'
    out, warns = sanitize_svg(s)
    print(f"  warns={warns}")
    assert "evil.com" not in out

    print("\n=== TEST 5: render real SVG ===")
    s = '<svg viewBox="0 0 200 100" xmlns="http://www.w3.org/2000/svg"><rect width="200" height="100" fill="white"/><circle cx="100" cy="50" r="30" fill="navy"/></svg>'
    ok, msg = render_svg_to_png(s, Path("test_svg_render.png"))
    print(f"  render ok: {ok}, msg: {msg}")
    if ok:
        ok2, errs = validate_png_output(Path("test_svg_render.png"))
        print(f"  validation ok: {ok2}, errs: {errs}")
        Path("test_svg_render.png").unlink(missing_ok=True)

    print("\nALL SVG SANITIZER TESTS PASSED")
