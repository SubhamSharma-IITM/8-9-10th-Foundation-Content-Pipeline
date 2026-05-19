"""
build_review_v2.py — Regenerate review/index.html from content_schema_final.json.

Sources:
  - experiments/05_content_generation/content_schema_final.json
  - experiments/03_topology_generation/competitive/master_schema_final.json
  - review/_shell_head.html (lines 1-209 of the old index.html)
  - review/_images_line.js  (IMAGES base64 blob from old index.html)

Produces:
  - review/index.html         (regenerated)
  - review/index_v1_backup.html (one-time backup of the previous build)

Two trees are embedded:
  - NCERT_TREE: 3 NCERT concepts only (NCERT mode sidebar/content)
  - COMP_TREE : 3 NCERT concepts + 6 competitive-only concepts (Comp mode)

Label rules (comp mode):
  - overlap subconcept        -> NCERT + COMP pills ; theory = NCERT theory ;
                                 questions stacked: NCERT source -> NCERT gen -> Examples -> Comp inherited
  - ncert_only subconcept     -> NCERT pill        ; theory + NCERT Qs only
  - competitive_only sub      -> COMP ADV pill     ; comp theory + Key Formulas box + comp Qs
"""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"D:/ACADZA_WORK/8-9-10th PIPELINE")
CONTENT_PATH = ROOT / "experiments/05_content_generation/content_schema_final.json"
MASTER_PATH = ROOT / "experiments/03_topology_generation/competitive/master_schema_final.json"
FOUNDATION_IMAGES_DIR = ROOT / "experiments/01_ocr_benchmarks/mathpix/ch01_light_competitive/mmd_extracted/images"
REVIEW_DIR = ROOT / "review"
SHELL_HEAD = REVIEW_DIR / "_shell_head.html"
IMAGES_LINE = REVIEW_DIR / "_images_line.js"
OUT_HTML = REVIEW_DIR / "index.html"
BACKUP_HTML = REVIEW_DIR / "index_v1_backup.html"


def _safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


# -------------------- Text preprocessing --------------------
_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\((?:\./)?images/([^)\s]+)\)")
_FIGURE_ENV_RE = re.compile(r"\\begin\{figure\}[^\n]*?[\s\S]*?\\end\{figure\}", re.MULTILINE)
_OTHER_ENV_RE = re.compile(r"\\begin\{(tabular|center|table|array|equation|align|matrix|bmatrix|pmatrix)[^}]*\}[\s\S]*?\\end\{\1\}", re.MULTILINE)
_CAPTIONSETUP_RE = re.compile(r"\\captionsetup\{[^}]*\}", re.MULTILINE)
_CAPTION_RE = re.compile(r"\\caption\{[^}]*\}", re.MULTILINE)


def _collect_foundation_image_refs(content: dict) -> set[str]:
    refs: set[str] = set()
    for sc in content["subconcepts"].values():
        for key in ("ncert_questions", "ncert_examples", "competitive_questions"):
            for q in sc.get(key, []):
                for field in ("question_text", "solution_text"):
                    text = q.get(field) or ""
                    for m in _MD_IMG_RE.finditer(text):
                        refs.add(m.group(1))
                opts = q.get("options") or {}
                if isinstance(opts, dict):
                    for v in opts.values():
                        for m in _MD_IMG_RE.finditer(str(v)):
                            refs.add(m.group(1))
    return refs


def _build_foundation_images(refs: set[str]) -> dict[str, str]:
    """Returns {basename -> data URI}. Missing files are skipped with a warning."""
    out: dict[str, str] = {}
    if not FOUNDATION_IMAGES_DIR.exists():
        _safe_print(f"[build_review_v2] WARNING: foundation images dir missing: {FOUNDATION_IMAGES_DIR}")
        return out
    missing = 0
    for ref in sorted(refs):
        fpath = FOUNDATION_IMAGES_DIR / ref
        if not fpath.exists():
            missing += 1
            continue
        ext = fpath.suffix.lower().lstrip(".")
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext or 'png'}"
        b64 = base64.b64encode(fpath.read_bytes()).decode("ascii")
        out[ref] = f"data:{mime};base64,{b64}"
    if missing:
        _safe_print(f"[build_review_v2] WARNING: {missing}/{len(refs)} foundation image refs not found on disk")
    _safe_print(f"[build_review_v2] foundation images loaded: {len(out)}/{len(refs)}")
    return out


def _strip_artifacts(text: str) -> str:
    """Remove LaTeX environment wrappers from MathPix OCR.
    For \\begin{figure}...\\end{figure}: keep any markdown images inside, drop the wrapper.
    """
    if not text:
        return text

    def _fig_replacer(m):
        inner = m.group(0)
        imgs = re.findall(r"!\[[^\]]*\]\([^)]*\)", inner)
        if imgs:
            return "\n\n" + "\n\n".join(imgs) + "\n\n"
        return " "

    text = _FIGURE_ENV_RE.sub(_fig_replacer, text)
    text = _OTHER_ENV_RE.sub(" ", text)
    text = _CAPTIONSETUP_RE.sub("", text)
    text = _CAPTION_RE.sub("", text)
    return text


def _normalize_for_dedupe(text: str) -> str:
    if not text:
        return ""
    norm = re.sub(r"\s+", " ", text.strip().lower())
    # Strip image and math noise so visually identical stems collide
    norm = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", norm)
    norm = re.sub(r"\$[^$]*\$", "", norm)
    norm = re.sub(r"\\[a-z]+\{[^}]*\}", "", norm)
    return norm.strip()[:400]


def _dedupe_list(qlist: list, stats: dict) -> list:
    seen: set[str] = set()
    out = []
    for q in qlist:
        key = _normalize_for_dedupe(q.get("question_text") or "")
        if len(key) < 20:
            out.append(q)
            continue
        if key in seen:
            stats["removed"] = stats.get("removed", 0) + 1
            continue
        seen.add(key)
        out.append(q)
    return out


def _preprocess_content(content: dict) -> dict:
    """In place: strip LaTeX artifacts, dedupe duplicate questions per list."""
    stats = {"removed": 0, "stripped_artifacts": 0}
    for sc in content["subconcepts"].values():
        for key in ("ncert_questions", "ncert_examples", "competitive_questions"):
            qlist = sc.get(key, [])
            for q in qlist:
                for field in ("question_text", "solution_text"):
                    orig = q.get(field) or ""
                    new = _strip_artifacts(orig)
                    if new != orig:
                        stats["stripped_artifacts"] += 1
                        q[field] = new
                opts = q.get("options") or {}
                if isinstance(opts, dict):
                    for k, v in list(opts.items()):
                        if isinstance(v, str):
                            opts[k] = _strip_artifacts(v)
            sc[key] = _dedupe_list(qlist, stats)
    _safe_print(f"[build_review_v2] dedupe: removed {stats['removed']} duplicate questions")
    _safe_print(f"[build_review_v2] stripped LaTeX artifacts in {stats['stripped_artifacts']} fields")
    return content


def _pack_sub(sc: dict, include_competitive: bool) -> dict:
    """Project a content_schema subconcept into the shape the JS app consumes."""
    tvc = sc.get("theory_VisualContent") or {}
    pack = {
        "code": sc["subconcept_code"],
        "name": sc["subconcept_name"],
        "parent_code": sc.get("parent_concept_code"),
        "parent_name": sc.get("parent_concept_name"),
        "category": sc.get("category"),
        "source": sc.get("source"),
        "theory": sc.get("theory") or "",
        "theory_image_ref": tvc.get("source_image_ref"),
        "ncert_questions": sc.get("ncert_questions", []),
        "ncert_examples": sc.get("ncert_examples", []),
    }
    if include_competitive:
        pack["competitive_questions"] = sc.get("competitive_questions", [])
        pack["key_formulas"] = sc.get("key_formulas") or []
        pack["competitive_theory_source"] = sc.get("competitive_theory_source")
    return pack


def build_trees(master: dict, content: dict) -> tuple[list, list]:
    subs = content["subconcepts"]

    ncert_tree: list[dict] = []
    comp_tree: list[dict] = []

    for concept in master["concepts"]:
        node_base = {
            "code": concept["code"],
            "name": concept["name"],
            "source": concept["source"],
            "subs": [],
        }

        # NCERT tree: NCERT concepts only
        if concept["source"] == "ncert":
            ncert_node = {**node_base, "subs": []}
            for sub in concept["subconcepts"]:
                sc = subs.get(sub["code"])
                if not sc:
                    continue
                ncert_node["subs"].append(_pack_sub(sc, include_competitive=False))
            ncert_tree.append(ncert_node)

        # Comp tree: all concepts
        comp_node = {**node_base, "subs": []}
        for sub in concept["subconcepts"]:
            sc = subs.get(sub["code"])
            if not sc:
                continue
            comp_node["subs"].append(_pack_sub(sc, include_competitive=True))
        comp_tree.append(comp_node)

    return ncert_tree, comp_tree


# -------------------- APP JS --------------------
# Written as a single template string; no .format placeholders inside (braces will conflict).
APP_JS = r"""
// ================= State =================
let currentMode = 'ncert';       // 'ncert' | 'comp'
let currentSubCode = null;
let scoreCorrect = 0;
let scoreWrong = 0;
let qState = {};                 // { qid: { selection, numericValue, textValue, submitted } }

const SUB_INDEX = {};            // code -> sub (ncert mode)
const SUB_INDEX_COMP = {};       // code -> sub (comp mode)

function buildIndex() {
  NCERT_TREE.forEach(c => c.subs.forEach(s => SUB_INDEX[s.code] = s));
  COMP_TREE.forEach(c => c.subs.forEach(s => SUB_INDEX_COMP[s.code] = s));
}

// ================= Utilities =================
function esc(s) { return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function md(s) {
  if (!s) return '';
  // Protect LaTeX math blocks so markdown rules don't touch them (\[ \], \( \), $$ $$, $ $)
  const saved = [];
  s = s.replace(/\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$/g, m => { saved.push(m); return '__MATH' + (saved.length-1) + '__'; });
  s = s.replace(/\$([^$\n]+?)\$/g, (m, inner) => { saved.push('\\(' + inner + '\\)'); return '__MATH' + (saved.length-1) + '__'; });
  // Markdown images -> <img> (looks up FOUNDATION_IMAGES by basename)
  s = s.replace(/!\[[^\]]*\]\((?:\.\/)?images\/([^)\s]+)\)/g, (m, fname) => {
    const src = (typeof FOUNDATION_IMAGES !== 'undefined') ? FOUNDATION_IMAGES[fname] : null;
    if (!src) return '<div class="image-placeholder">Image: ' + esc(fname) + ' (missing)</div>';
    return '<div class="image-wrap"><img src="' + src + '" alt="' + esc(fname) + '"></div>';
  });
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  // ordered/unordered lists (simple)
  s = s.replace(/^(?:\d+\.\s.+(?:\n|$))+/gm, block => {
    const items = block.trim().split(/\n/).map(x => x.replace(/^\d+\.\s+/, '')).map(x => '<li>' + x + '</li>').join('');
    return '<ol>' + items + '</ol>';
  });
  s = s.replace(/^(?:[-*]\s.+(?:\n|$))+/gm, block => {
    const items = block.trim().split(/\n/).map(x => x.replace(/^[-*]\s+/, '')).map(x => '<li>' + x + '</li>').join('');
    return '<ul>' + items + '</ul>';
  });
  s = s.split(/\n\n+/).map(p => p.trim() ? (p.match(/^<(ul|ol|h\d|div|details)/) ? p : '<p>' + p.replace(/\n/g,'<br>') + '</p>') : '').join('');
  s = s.replace(/__MATH(\d+)__/g, (_, i) => saved[+i]);
  return s;
}

function stripOptionsFromStem(text) {
  if (!text) return '';
  // Remove "(A) ...", "(B) ...", etc. from stem
  return text.replace(/\n?\s*\([A-D]\)[\s\S]*$/, '').trim();
}

function renderImage(ref) {
  if (!ref) return '';
  const src = (typeof IMAGES !== 'undefined') ? IMAGES[ref] : null;
  if (!src) return '<div class="image-placeholder">Image: ' + esc(ref) + ' (asset missing)</div>';
  return '<div class="image-wrap"><img src="' + src + '" alt="' + esc(ref) + '"></div>';
}

function renderVisualContent(vc) {
  if (!vc || !vc.needed) return '';
  if (vc.source_image_ref) return renderImage(vc.source_image_ref);
  if (vc.image_generation_needed) {
    return '<div class="image-placeholder">[Image to be generated] ' + esc(vc.image_description || '') + '</div>';
  }
  return '';
}

// Split question image vs solution image using heuristics (figure mentioned in stem vs solution).
function inferImagePlacement(q) {
  const vc = q.VisualContent;
  if (!vc || !vc.needed) return { qvc: null, svc: null };
  const qText = (q.question_text || '').toLowerCase();
  const sText = (q.solution_text || '').toLowerCase();
  const inQ = qText.includes('figure') || qText.includes('diagram') || qText.includes('shown below');
  const inS = sText.includes('figure') || sText.includes('ray diagram');
  if (inQ && !inS) return { qvc: vc, svc: null };
  if (inS && !inQ) return { qvc: null, svc: vc };
  if (inQ && inS) return { qvc: null, svc: vc };
  return { qvc: null, svc: vc };
}

// ================= Labels =================
function difficultyPill(d) {
  const v = (d || 'Medium');
  const cls = v === 'Easy' ? 'label-easy' : v === 'Hard' ? 'label-hard' : 'label-medium';
  return '<span class="label ' + cls + '">' + esc(v) + '</span>';
}

function sourcePillNCERT(q) {
  const src = q._source;
  if (src === 'ncert') return '<span class="label label-source">NCERT</span>';
  if (src === 'generated') return '<span class="label label-generated">Generated</span>';
  return '<span class="label label-source">NCERT</span>';
}

function formatPill(q) {
  if (q.scq_format) return '<span class="label label-format">' + esc(q.scq_format) + '</span>';
  if (q.answer_format) return '<span class="label label-format">' + esc(q.answer_format) + '</span>';
  return '';
}

function tierPill(q) {
  const name = q.exercise_name;
  if (!name) return '';
  const short = name.length > 22 ? name.slice(0, 22) + '...' : name;
  return '<span class="label label-tier" style="background:#E3F2FD;color:#1565C0" title="' + esc(name) + '">' + esc(short) + '</span>';
}

function foundationTypePill(q) {
  if (!q.foundation_type) return '';
  const ft = q.foundation_type;
  const bg = ft === 'NTSE' ? '#FFE0B2' : ft === 'KVPY' ? '#C8E6C9' : ft === 'JSTSE' ? '#F8BBD0' : '#ECEFF1';
  const fg = ft === 'NTSE' ? '#E65100' : ft === 'KVPY' ? '#1B5E20' : ft === 'JSTSE' ? '#880E4F' : '#37474F';
  return '<span class="label" style="background:' + bg + ';color:' + fg + ';font-weight:700">' + esc(ft) + '</span>';
}

function ncertSourceOriginPill(q) {
  if (q.isBackExercise) return '<span class="label label-format">Back Exercise</span>';
  if (q.isInTextQuestion) return '<span class="label label-format">In-Text</span>';
  return '';
}

// ================= Sidebar =================
function buildSidebar() {
  const sb = document.getElementById('sidebar');
  const tree = currentMode === 'ncert' ? NCERT_TREE : COMP_TREE;
  const title = currentMode === 'ncert' ? 'NCERT Mode' : 'Competitive Mode';
  const sub = currentMode === 'ncert'
    ? 'Class 10 CBSE Science syllabus content.'
    : 'Foundation content layered on NCERT.';

  let h = '<h3 style="color:var(--accent);margin-bottom:2px">' + title + '</h3>';
  h += '<p style="font-size:0.7rem;color:var(--text3);padding:0 8px 8px">' + sub + '</p>';

  for (const concept of tree) {
    const isCompOnly = concept.source === 'competitive_only';
    const badge = isCompOnly ? ' <span style="font-size:0.58rem;background:#FFF3E8;color:var(--accent);padding:1px 5px;border-radius:3px;font-weight:700">COMP ONLY</span>' : '';
    h += '<div class="sidebar-group">';
    h += '<div class="sidebar-concept" data-expand="1" style="cursor:pointer">' + esc(concept.name) + badge + '</div>';
    h += '<div class="sidebar-subs" style="display:none">';
    for (const sub of concept.subs) {
      const cat = sub.category;
      let pills = '';
      if (currentMode === 'comp') {
        if (cat === 'overlap') {
          pills = '<span class="pill pill-ncert">NCERT</span><span class="pill pill-comp">COMP</span>';
        } else if (cat === 'ncert_only') {
          pills = '<span class="pill pill-ncert">NCERT</span>';
        } else if (cat === 'competitive_only') {
          pills = '<span class="pill pill-adv">COMP ADV</span>';
        }
      } else {
        pills = '<span class="pill pill-ncert">NCERT</span>';
      }
      h += '<div class="sidebar-sub" data-sub-code="' + esc(sub.code) + '">';
      h += '<span class="sub-name">' + esc(sub.name) + '</span>';
      h += '<span class="sub-pills">' + pills + '</span>';
      h += '</div>';
    }
    h += '</div></div>';
  }
  sb.innerHTML = h;

  sb.querySelectorAll('[data-expand]').forEach(el => {
    el.addEventListener('click', () => {
      const subs = el.nextElementSibling;
      subs.style.display = subs.style.display === 'none' ? 'block' : 'none';
    });
  });
  sb.querySelectorAll('[data-sub-code]').forEach(el => {
    el.addEventListener('click', () => app.selectSub(el.dataset.subCode, el));
  });
}

// ================= Question card =================
function qState_get(qid) {
  if (!qState[qid]) qState[qid] = { selection: null, numericValue: '', textValue: '', submitted: false };
  return qState[qid];
}

function renderQuestionCard(q, qid, sourceKind) {
  // sourceKind: 'ncert' | 'comp'
  const s = qState_get(qid);
  let h = '';

  // Label row
  h += '<div class="label-row">';
  if (sourceKind === 'ncert') {
    h += sourcePillNCERT(q);
    h += ncertSourceOriginPill(q);
  } else {
    h += '<span class="label" style="background:#EDE7F6;color:#5E35B1;font-weight:700">Foundation</span>';
    h += tierPill(q);
    h += foundationTypePill(q);
  }
  h += formatPill(q);
  h += difficultyPill(q.Difficulty);
  h += '</div>';

  const { qvc, svc } = inferImagePlacement(q);

  // Stem
  const stem = stripOptionsFromStem(q.question_text || '');
  h += '<div class="q-text">' + md(stem) + '</div>';
  if (qvc) h += renderVisualContent(qvc);

  // Options (SCQ)
  const hasOptions = q.options && typeof q.options === 'object' && Object.keys(q.options).length >= 2;
  const isSCQ = (q.type === 'scq' || hasOptions);

  if (isSCQ && hasOptions) {
    h += '<div class="options-grid">';
    for (const label of ['A','B','C','D']) {
      if (!(label in q.options)) continue;
      const optText = q.options[label];
      let cls = 'option-card';
      let icon = '';
      if (s.submitted) {
        cls += ' disabled';
        const isCorrect = (q.answer_key === label);
        if (s.selection === label) {
          cls += isCorrect ? ' correct' : ' incorrect';
          icon = isCorrect ? '<span class="option-icon">&#10003;</span>' : '<span class="option-icon">&#10007;</span>';
        } else if (isCorrect) {
          cls += ' missed';
          icon = '<span class="option-icon">&#10003;</span>';
        }
      } else if (s.selection === label) {
        cls += ' selected';
      }
      const click = s.submitted ? '' : ' data-qid="' + qid + '" data-opt="' + label + '"';
      h += '<div class="' + cls + '"' + click + '><span class="option-label">' + label + '</span><span class="option-text">' + md(optText) + '</span>' + icon + '</div>';
    }
    h += '</div>';
    h += '<div class="q-actions">';
    if (s.submitted) {
      h += '<button class="submit-btn submitted">Submitted</button>';
      h += '<button class="btn-reset" data-reset-qid="' + qid + '">Reset</button>';
      if (q.solution_text) h += '<button class="btn-sol" data-sol-qid="' + qid + '">Show Solution</button>';
    } else {
      const activeCls = s.selection ? ' active' : '';
      h += '<button class="submit-btn' + activeCls + '" data-submit-qid="' + qid + '" data-answer="' + esc(q.answer_key || '') + '" data-qtype="scq">Submit</button>';
    }
    h += '</div>';
    if (s.submitted) {
      const correct = (s.selection === q.answer_key);
      h += '<div class="result-banner ' + (correct ? 'correct' : 'incorrect') + '">' + (correct ? '&#10003; Correct!' : '&#10007; Incorrect. Answer: ' + esc(q.answer_key || '')) + '</div>';
    }
  } else if (q.answer_format === 'numerical' || q.type === 'integer') {
    // numerical input
    let inputCls = 'numeric-input', feedback = '';
    if (s.submitted) {
      const userVal = parseFloat(s.numericValue);
      const ans = q.answer_key || '';
      const numMatch = String(ans).match(/-?[\d.]+/);
      const correctVal = numMatch ? parseFloat(numMatch[0]) : NaN;
      const correct = !isNaN(userVal) && !isNaN(correctVal) && Math.abs(userVal - correctVal) < 0.1;
      inputCls += correct ? ' correct' : ' incorrect';
      feedback = correct ? '<span class="numeric-feedback correct">&#10003; Correct!</span>'
        : '<span class="numeric-feedback incorrect">&#10007; Answer: ' + esc(ans) + '</span>';
    }
    h += '<div class="numeric-group"><input type="number" class="' + inputCls + '" data-num-qid="' + qid + '" placeholder="Your answer..." value="' + esc(s.numericValue || '') + '"' + (s.submitted ? ' disabled' : '') + '>' + feedback + '</div>';
    h += '<div class="q-actions">';
    if (s.submitted) {
      h += '<button class="submit-btn submitted">Submitted</button>';
      h += '<button class="btn-reset" data-reset-qid="' + qid + '">Reset</button>';
      if (q.solution_text) h += '<button class="btn-sol" data-sol-qid="' + qid + '">Show Solution</button>';
    } else {
      const activeCls = s.numericValue ? ' active' : '';
      h += '<button class="submit-btn' + activeCls + '" data-submit-qid="' + qid + '" data-answer="' + esc(q.answer_key || '') + '" data-qtype="numerical">Submit</button>';
    }
    h += '</div>';
  } else {
    // descriptive
    h += '<textarea class="text-area' + (s.submitted ? ' submitted' : '') + '" data-text-qid="' + qid + '" placeholder="Type your answer..."' + (s.submitted ? ' disabled' : '') + '>' + esc(s.textValue || '') + '</textarea>';
    h += '<div class="q-actions">';
    if (s.submitted) {
      h += '<button class="submit-btn submitted">Submitted</button>';
      h += '<button class="btn-reset" data-reset-qid="' + qid + '">Reset</button>';
      if (q.solution_text) h += '<button class="btn-sol" data-sol-qid="' + qid + '">Show Solution</button>';
    } else {
      const activeCls = (s.textValue || '').trim() ? ' active' : '';
      h += '<button class="submit-btn' + activeCls + '" data-submit-qid="' + qid + '" data-answer="" data-qtype="descriptive">Submit</button>';
    }
    h += '</div>';
    if (s.submitted) h += '<div class="result-banner correct">&#10003; Answer recorded</div>';
  }

  // Solution panel
  if (q.solution_text && s.submitted) {
    h += '<div class="sol-panel" id="sol-' + qid + '"><h4>Solution</h4><div class="sol-text">' + md(q.solution_text) + '</div>';
    if (svc) h += renderVisualContent(svc);
    h += '</div>';
  }

  return '<div class="card"><div class="card-body" id="q-' + qid + '" data-q=\'' + JSON.stringify(q).replace(/'/g, '&#39;').replace(/\\/g, '\\\\') + '\' data-qsource="' + sourceKind + '">' + h + '</div></div>';
}

function renderExampleCard(ex) {
  const diff = difficultyPill(ex.Difficulty);
  const src = (ex._source === 'ncert' ? '<span class="label label-source">NCERT</span>' : '<span class="label label-generated">Generated</span>');
  let h = '<div class="card"><div class="card-body">';
  h += '<div class="label-row">' + src + diff + '</div>';
  h += '<div class="q-text">' + md(ex.question_text || '') + '</div>';
  if (ex.VisualContent) h += renderVisualContent(ex.VisualContent);
  if (ex.solution_text) {
    h += '<details class="sol-details"><summary>Show Solution</summary>';
    h += '<div class="sol-panel visible"><div class="sol-text">' + md(ex.solution_text) + '</div></div></details>';
  }
  h += '</div></div>';
  return h;
}

// ================= Main content render =================
function qid_for(sub, prefix, i) {
  return (prefix + '_' + sub.code + '_' + i).replace(/[^a-zA-Z0-9_]/g, '_');
}

function renderSubContent(sub) {
  const cat = sub.category;
  let h = '';
  h += '<h2 class="sub-title">' + esc(sub.name) + '</h2>';
  h += '<div class="sub-parent">' + esc(sub.parent_name || '') + '</div>';

  // Category pill header
  let catBadges = '<div class="label-row">';
  if (currentMode === 'comp') {
    if (cat === 'overlap') catBadges += '<span class="pill pill-ncert">NCERT</span><span class="pill pill-comp">COMP</span>';
    else if (cat === 'ncert_only') catBadges += '<span class="pill pill-ncert">NCERT</span>';
    else if (cat === 'competitive_only') catBadges += '<span class="pill pill-adv">COMP ADV</span>';
  } else {
    catBadges += '<span class="pill pill-ncert">NCERT</span>';
  }
  catBadges += '</div>';
  h += catBadges;

  // Tier legend — shown in Comp mode whenever comp questions exist
  if (currentMode === 'comp' && (sub.competitive_questions || []).length) {
    h += '<details class="tier-legend"><summary>What do the tier / foundation labels mean?</summary>';
    h += '<p class="legend-note">All competitive questions here are lifted directly from the exercise sections of the <i>10 Physics Foundation</i> source book. Each exercise in that book targets a different proficiency tier, and we preserve that tiering. Difficulty (Easy / Medium / Hard) is <b>not random</b> - it is inferred per-question by the LLM using a Class-10 rubric, biased by the tier the question sits in.</p>';
    h += '<ul>';
    h += '<li><b>Master Boards</b> - Exercise 1 in the source book. CBSE/State board-style questions. Useful for <i>school and board exam</i> practice. Mostly Easy and Medium.</li>';
    h += '<li><b>Master NCERT</b> - Exercise 2. Deeper NCERT-aligned drilling. Useful for <i>board exam revision</i> and building fluency on the core syllabus before stepping up. Easy to Medium.</li>';
    h += '<li><b>Foundation Builder</b> - Exercise 3. Step-up tier mostly in MCQ form. Useful for <i>NTSE, NSEJS and KVPY-style talent exams</i>, and the foundation layer for <i>JEE Main, NEET and IOQP (Physics Olympiad)</i>. Mostly Medium with some Hard.</li>';
    h += '<li><b>Foundation Builder+</b> - Exercise 4. Hardest tier, cross-topic and multi-step. Useful for <i>JEE Advanced foundation prep, NEET, and IOQP/INPhO Olympiad shortlisting</i>. Mostly Hard.</li>';
    h += '<li><b>NTSE / KVPY / JSTSE</b> - question is a verified past-year problem from that national exam. NTSE and NSEJS target Class 10; JSTSE targets Class 9. These tags are <i>lifted from the source book</i>; questions without a tag are original but tier-style matched.</li>';
    h += '</ul></details>';
  }

  // Theory
  const theoryText = sub.theory || '';
  if (theoryText) {
    h += '<div class="card"><div class="card-header"><div class="section-title"><span class="section-icon" style="background:var(--blue)">T</span>Theory</div></div>';
    h += '<div class="card-body"><div class="theory-text">' + md(theoryText) + '</div>';
    if (sub.theory_image_ref) h += renderImage(sub.theory_image_ref);
    h += '</div></div>';
  }

  // Key Formulas (comp-only subs)
  if (currentMode === 'comp' && cat === 'competitive_only' && sub.key_formulas && sub.key_formulas.length) {
    h += '<div class="card key-formulas"><div class="card-header"><div class="section-title"><span class="section-icon" style="background:#7E57C2">F</span>Key Formulas</div></div>';
    h += '<div class="card-body"><ul class="formula-list">';
    for (const f of sub.key_formulas) {
      h += '<li>\\[' + f + '\\]</li>';
    }
    h += '</ul></div></div>';
  }

  // Questions & examples — partition by source group
  const ncertQs = sub.ncert_questions || [];
  const examples = sub.ncert_examples || [];
  const compQs = (sub.competitive_questions || []);

  // Split NCERT questions by source (source vs generated)
  const ncertSource = ncertQs.filter(q => q._source !== 'generated');
  const ncertGen = ncertQs.filter(q => q._source === 'generated');

  // NCERT section — always shown for ncert/overlap/ncert_only subs
  const showNCERTQs = (cat === 'overlap' || cat === 'ncert_only' || currentMode === 'ncert');

  if (showNCERTQs && ncertSource.length) {
    h += '<div class="section-title"><span class="section-icon" style="background:var(--green)">Q</span>NCERT Source Questions (' + ncertSource.length + ')</div>';
    ncertSource.forEach((q, i) => { h += renderQuestionCard(q, qid_for(sub, 'nsrc', i), 'ncert'); });
  }
  if (showNCERTQs && ncertGen.length) {
    h += '<div class="section-title"><span class="section-icon" style="background:var(--blue)">G</span>NCERT Generated Questions (' + ncertGen.length + ')</div>';
    ncertGen.forEach((q, i) => { h += renderQuestionCard(q, qid_for(sub, 'ngen', i), 'ncert'); });
  }
  if (showNCERTQs && examples.length) {
    h += '<div class="section-title"><span class="section-icon" style="background:#7E57C2">E</span>Solved Examples (' + examples.length + ')</div>';
    examples.forEach((ex, i) => { h += renderExampleCard(ex); });
  }

  // Competitive section — only in comp mode, for overlap + competitive_only
  if (currentMode === 'comp' && (cat === 'overlap' || cat === 'competitive_only') && compQs.length) {
    h += '<div class="section-title"><span class="section-icon" style="background:var(--accent)">C</span>Competitive Questions (' + compQs.length + ')</div>';
    compQs.forEach((q, i) => { h += renderQuestionCard(q, qid_for(sub, 'comp', i), 'comp'); });
  }

  // Empty-state
  if (!theoryText && !ncertQs.length && !examples.length && !compQs.length) {
    h += '<div class="card"><div class="card-body" style="text-align:center;padding:32px;color:var(--text3)">No content available for this subconcept yet.</div></div>';
  }

  return h;
}

// ================= App =================
const app = {
  init() {
    buildIndex();
    buildSidebar();
    this.bindDelegatedEvents();
    updateCountsBar();
  },

  toggleMode() {
    currentMode = currentMode === 'ncert' ? 'comp' : 'ncert';
    const btn = document.getElementById('modeToggle');
    if (currentMode === 'comp') {
      btn.textContent = 'NCERT Mode';
      btn.style.background = 'var(--accent)';
      btn.style.color = '#fff';
    } else {
      btn.textContent = 'Competitive Mode';
      btn.style.background = 'var(--surface)';
      btn.style.color = 'var(--accent)';
    }
    buildSidebar();
    updateCountsBar();
    document.getElementById('welcome').style.display = 'block';
    document.getElementById('subView').style.display = 'none';
    currentSubCode = null;
  },

  toggleSidebar() {
    const layout = document.getElementById('mainLayout');
    const icon = document.getElementById('toggleIcon');
    layout.classList.toggle('collapsed');
    icon.innerHTML = layout.classList.contains('collapsed') ? '&#9654;' : '&#9664;';
  },

  toggleMobile() {
    const sb = document.getElementById('sidebar');
    const overlay = document.getElementById('mobileOverlay');
    if (!sb || !overlay) return;
    const open = sb.classList.contains('mobile-open');
    if (open) { sb.classList.remove('mobile-open'); overlay.classList.remove('visible'); }
    else      { sb.classList.add('mobile-open');    overlay.classList.add('visible'); }
  },
  closeMobile() {
    const sb = document.getElementById('sidebar');
    const overlay = document.getElementById('mobileOverlay');
    if (sb) sb.classList.remove('mobile-open');
    if (overlay) overlay.classList.remove('visible');
  },

  selectSub(code, el) {
    document.querySelectorAll('.sidebar-sub').forEach(e => e.classList.remove('active'));
    if (el) el.classList.add('active');
    const idx = currentMode === 'ncert' ? SUB_INDEX : SUB_INDEX_COMP;
    const sub = idx[code];
    if (!sub) return;
    currentSubCode = code;
    document.getElementById('welcome').style.display = 'none';
    const v = document.getElementById('subView');
    v.style.display = 'block';
    v.innerHTML = renderSubContent(sub);
    if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([v]);
    this.closeMobile();
  },

  bindDelegatedEvents() {
    // Header toggle button binds via onclick in markup; the rest delegate from subView
    const root = document.getElementById('subView');
    root.addEventListener('click', (e) => {
      const t = e.target;
      // Option select
      const optCard = t.closest ? t.closest('[data-qid][data-opt]') : null;
      if (optCard && !optCard.classList.contains('disabled')) {
        const qid = optCard.dataset.qid, opt = optCard.dataset.opt;
        const s = qState_get(qid);
        s.selection = opt;
        app.rerender(qid);
        return;
      }
      const submitBtn = t.closest ? t.closest('[data-submit-qid]') : null;
      if (submitBtn) {
        const qid = submitBtn.dataset.submitQid;
        const answer = submitBtn.dataset.answer || '';
        const qtype = submitBtn.dataset.qtype;
        app.submitAnswer(qid, answer, qtype);
        return;
      }
      const resetBtn = t.closest ? t.closest('[data-reset-qid]') : null;
      if (resetBtn) {
        app.resetQuestion(resetBtn.dataset.resetQid);
        return;
      }
      const solBtn = t.closest ? t.closest('[data-sol-qid]') : null;
      if (solBtn) {
        app.toggleSolution(solBtn.dataset.solQid);
        return;
      }
    });
    root.addEventListener('input', (e) => {
      const numEl = e.target.closest ? e.target.closest('[data-num-qid]') : null;
      if (numEl) {
        const qid = numEl.dataset.numQid;
        const s = qState_get(qid);
        s.numericValue = numEl.value;
        const btn = root.querySelector('[data-submit-qid="' + qid + '"]');
        if (btn) btn.classList.toggle('active', !!numEl.value);
        return;
      }
      const txtEl = e.target.closest ? e.target.closest('[data-text-qid]') : null;
      if (txtEl) {
        const qid = txtEl.dataset.textQid;
        const s = qState_get(qid);
        s.textValue = txtEl.value;
        const btn = root.querySelector('[data-submit-qid="' + qid + '"]');
        if (btn) btn.classList.toggle('active', !!(txtEl.value || '').trim());
      }
    });
  },

  submitAnswer(qid, answer, qtype) {
    const s = qState_get(qid);
    if (s.submitted) return;
    s.submitted = true;
    let correct = false;
    if (qtype === 'scq') {
      correct = (s.selection === answer);
    } else if (qtype === 'numerical') {
      const u = parseFloat(s.numericValue);
      const m = (answer || '').match(/-?[\d.]+/);
      const c = m ? parseFloat(m[0]) : NaN;
      correct = !isNaN(u) && !isNaN(c) && Math.abs(u - c) < 0.1;
    } else {
      correct = true;
    }
    s._wasCorrect = correct;
    if (correct) scoreCorrect++; else scoreWrong++;
    document.getElementById('scoreCorrect').textContent = scoreCorrect;
    document.getElementById('scoreWrong').textContent = scoreWrong;
    this.rerender(qid);
  },

  resetQuestion(qid) {
    const s = qState[qid];
    if (s && s.submitted) {
      scoreCorrect = Math.max(0, scoreCorrect - (s._wasCorrect ? 1 : 0));
      scoreWrong   = Math.max(0, scoreWrong   - (s._wasCorrect ? 0 : 1));
    }
    delete qState[qid];
    document.getElementById('scoreCorrect').textContent = scoreCorrect;
    document.getElementById('scoreWrong').textContent = scoreWrong;
    this.rerender(qid);
  },

  toggleSolution(qid) {
    const el = document.getElementById('sol-' + qid);
    if (!el) return;
    el.classList.toggle('visible');
    if (el.classList.contains('visible') && window.MathJax && MathJax.typesetPromise) {
      setTimeout(() => MathJax.typesetPromise([el]), 60);
    }
  },

  rerender(qid) {
    const el = document.getElementById('q-' + qid);
    if (!el) return;
    const q = JSON.parse(el.dataset.q);
    const sourceKind = el.dataset.qsource || 'ncert';
    const card = renderQuestionCard(q, qid, sourceKind);
    // renderQuestionCard returns a wrapping <div class="card">, so we just replace the card-body contents
    const tmp = document.createElement('div');
    tmp.innerHTML = card;
    const newBody = tmp.querySelector('#q-' + qid);
    if (newBody) el.innerHTML = newBody.innerHTML;
    if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([el]);
  },
};

function updateCountsBar() {
  // Count subs / Qs for current mode
  const tree = currentMode === 'ncert' ? NCERT_TREE : COMP_TREE;
  let subs = 0, q = 0, ex = 0;
  for (const c of tree) {
    for (const s of c.subs) {
      subs++;
      q += (s.ncert_questions || []).length;
      ex += (s.ncert_examples || []).length;
      if (currentMode === 'comp') q += (s.competitive_questions || []).length;
    }
  }
  const bar = document.querySelector('.stats-bar');
  if (!bar) return;
  bar.innerHTML =
    '<div>Concepts: <span>' + tree.length + '</span></div>' +
    '<div>Subconcepts: <span>' + subs + '</span></div>' +
    '<div>Questions: <span>' + q + '</span></div>' +
    '<div>Examples: <span>' + ex + '</span></div>';
}

document.addEventListener('DOMContentLoaded', () => app.init());
"""


EXTRA_CSS = r"""
<style>
.label-row { display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px; }
.pill { display:inline-block;padding:2px 8px;border-radius:10px;font-size:0.66rem;font-weight:700;letter-spacing:0.02em;margin-right:3px; }
.pill-ncert { background:var(--green-light);color:var(--green); }
.pill-comp  { background:#E3F2FD;color:#1565C0; }
.pill-adv   { background:#FFF3E8;color:var(--accent); }
.label-tier { font-weight:600; }
.sidebar-sub { display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 12px;cursor:pointer;border-radius:6px;margin:2px 4px;font-size:0.82rem;color:var(--text1); }
.sidebar-sub:hover { background:var(--surface2); }
.sidebar-sub.active { background:var(--blue-light);color:var(--blue);font-weight:600; }
.sidebar-sub .sub-pills { display:flex;gap:3px;flex-shrink:0; }
.sidebar-sub .sub-name { flex:1;line-height:1.2; }
.sidebar-concept { padding:10px 12px;font-weight:700;color:var(--navy);cursor:pointer;background:var(--surface2);border-radius:6px;margin:6px 4px 2px;font-size:0.88rem; }
.sidebar-concept:hover { background:var(--blue-light); }
.sub-title { font-size:1.4rem;font-weight:700;color:var(--navy);margin-bottom:2px; }
.sub-parent { font-size:0.82rem;color:var(--text3);margin-bottom:14px; }
.image-wrap { margin:12px 0;text-align:center; }
.image-wrap img { max-width:100%;border-radius:8px;border:1px solid var(--border); }
.image-placeholder { background:#FFF8E1;color:#8D6E00;padding:12px;border-radius:6px;border:1px dashed #D4B560;font-size:0.82rem;margin:10px 0;font-family:monospace; }
.key-formulas .formula-list { list-style:none;padding:0;margin:0;display:grid;gap:10px; }
.key-formulas .formula-list li { background:var(--surface2);padding:12px 16px;border-radius:6px;border-left:3px solid #7E57C2;font-size:1.02rem; }
.sol-details > summary { cursor:pointer;color:var(--green);font-weight:600;font-size:0.88rem;margin-top:12px; }
.tier-legend { background:var(--surface2);border-radius:6px;padding:10px 14px;margin:10px 0 16px;border:1px solid var(--border);font-size:0.84rem; }
.tier-legend > summary { cursor:pointer;color:var(--accent);font-weight:700;font-size:0.82rem; }
.tier-legend ul { margin:10px 0 0;padding-left:18px;color:var(--text2);line-height:1.55; }
.tier-legend li { margin-bottom:6px; }
.tier-legend b { color:var(--navy); }
.tier-legend .legend-note { color:var(--text2);margin:8px 0 6px;line-height:1.55;font-size:0.82rem; }
.tier-legend i { color:var(--accent);font-style:normal;font-weight:500; }
</style>
"""


def main():
    _safe_print("[build_review_v2] loading data")
    content = json.loads(CONTENT_PATH.read_text("utf-8"))
    master = json.loads(MASTER_PATH.read_text("utf-8"))

    if not SHELL_HEAD.exists() or not IMAGES_LINE.exists():
        _safe_print("[build_review_v2] ERROR: shell/images extraction files missing. "
                    "Run the extraction step from the old index.html first.")
        sys.exit(1)

    shell_head = SHELL_HEAD.read_text("utf-8")
    # Patch MathJax config on the fly: allow $...$ and process markdown-safe HTML.
    # Use a lambda so re.sub does not apply its own backslash-escape rules to the replacement.
    mathjax_replacement = (
        "window.MathJax = {\n"
        "  tex: {\n"
        "    inlineMath: [['\\\\(','\\\\)'], ['$','$']],\n"
        "    displayMath: [['\\\\[','\\\\]'], ['$$','$$']],\n"
        "    processEscapes: true\n"
        "  },\n"
        "  options: { skipHtmlTags: ['script','noscript','style','textarea','pre','code'] },\n"
        "  startup: { typeset: false }\n"
        "};"
    )
    shell_head = re.sub(
        r"window\.MathJax\s*=\s*\{[\s\S]*?\};",
        lambda _m: mathjax_replacement,
        shell_head,
        count=1,
    )
    images_line = IMAGES_LINE.read_text("utf-8").rstrip()

    # Preprocess: strip LaTeX env artifacts + dedupe questions
    _safe_print("[build_review_v2] preprocessing content")
    content = _preprocess_content(content)

    # Foundation images (markdown-style ./images/X in question/solution text)
    refs = _collect_foundation_image_refs(content)
    _safe_print(f"[build_review_v2] foundation image refs found: {len(refs)}")
    foundation_images = _build_foundation_images(refs)

    _safe_print("[build_review_v2] building trees")
    ncert_tree, comp_tree = build_trees(master, content)

    def json_for_html(obj) -> str:
        # Make safe to embed between <script> tags
        return json.dumps(obj, ensure_ascii=False).replace("</", r"<\/")

    ncert_js = "const NCERT_TREE = " + json_for_html(ncert_tree) + ";"
    comp_js = "const COMP_TREE = " + json_for_html(comp_tree) + ";"
    foundation_js = "const FOUNDATION_IMAGES = " + json_for_html(foundation_images) + ";"

    # Stats for quick visibility
    n_ncert_subs = sum(len(c["subs"]) for c in ncert_tree)
    n_comp_subs = sum(len(c["subs"]) for c in comp_tree)
    _safe_print(f"[build_review_v2] NCERT concepts={len(ncert_tree)} subs={n_ncert_subs}")
    _safe_print(f"[build_review_v2] COMP  concepts={len(comp_tree)} subs={n_comp_subs}")

    # One-time backup of the pre-v2 file
    if OUT_HTML.exists() and not BACKUP_HTML.exists():
        BACKUP_HTML.write_text(OUT_HTML.read_text("utf-8"), "utf-8")
        _safe_print(f"[build_review_v2] backed up old index.html -> {BACKUP_HTML.name}")

    # Assemble
    parts = []
    parts.append(shell_head.rstrip())
    parts.append(EXTRA_CSS)
    parts.append("<script>")
    parts.append(images_line)
    parts.append(foundation_js)
    parts.append(ncert_js)
    parts.append(comp_js)
    parts.append(APP_JS)
    parts.append("</script>")
    parts.append("</body></html>")
    final_html = "\n".join(parts)

    OUT_HTML.write_text(final_html, "utf-8")
    size_mb = OUT_HTML.stat().st_size / (1024 * 1024)
    _safe_print(f"[build_review_v2] wrote {OUT_HTML} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
