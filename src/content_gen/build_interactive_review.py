"""
Build Interactive Review HTML — Premium Design with Question Interactions.

Adapts maths2-v2 design system: option cards, submit/reset, numeric input,
sidebar toggle, score tracker. Single self-contained HTML file.
"""
import json, os, sys, base64, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.join(os.path.dirname(__file__), '..', '..')

# Load all data
with open(os.path.join(BASE, 'experiments/05_content_generation/ch09_final_content.json'), 'r', encoding='utf-8') as f:
    content = json.load(f)
with open(os.path.join(BASE, 'experiments/03_topology_generation/ch09_schema.json'), 'r', encoding='utf-8') as f:
    schema = json.load(f)
with open(os.path.join(BASE, 'experiments/03_topology_generation/ch09_image_codes.json'), 'r', encoding='utf-8') as f:
    img_codes = json.load(f)

# Build image map from local files
image_urls = {}
img_dir = os.path.join(BASE, 'experiments/01_ocr_benchmarks/mathpix/ch09_light/mmd_extracted/images')
for code, info in img_codes.items():
    local = info.get('local_file', '')
    if local and os.path.exists(local):
        with open(local, 'rb') as imgf:
            image_urls[code] = f'data:image/jpeg;base64,{base64.b64encode(imgf.read()).decode("ascii")}'

# Add generated images
gen_img_dir = os.path.join(BASE, 'experiments/05_content_generation/ch09_generated_images')
if os.path.exists(gen_img_dir):
    for fname in os.listdir(gen_img_dir):
        if fname.endswith('.png'):
            key = f"GEN_{fname.replace('.png', '')}"
            with open(os.path.join(gen_img_dir, fname), 'rb') as imgf:
                image_urls[key] = f'data:image/png;base64,{base64.b64encode(imgf.read()).decode("ascii")}'

# Encode logo
with open('D:/ACADZA_WORK/acadza-pdf-generator/partners/acadza/logo.png', 'rb') as f:
    logo_b64 = base64.b64encode(f.read()).decode('ascii')

content_js = json.dumps(content, ensure_ascii=False)
schema_js = json.dumps(schema, ensure_ascii=False)
image_urls_js = json.dumps(image_urls, ensure_ascii=False)

# Load competitive mode data
comp_topo_path = os.path.join(BASE, 'experiments/03_topology_generation/competitive/comp_topology.json')
comp_mapping_path = os.path.join(BASE, 'experiments/03_topology_generation/competitive/demo_mapping.json')
comp_topology = {}
comp_mapping = []
if os.path.exists(comp_topo_path):
    with open(comp_topo_path, 'r', encoding='utf-8') as f:
        comp_topology = json.load(f)
if os.path.exists(comp_mapping_path):
    with open(comp_mapping_path, 'r', encoding='utf-8') as f:
        comp_mapping = json.load(f).get('mapping', [])

comp_topology_js = json.dumps(comp_topology, ensure_ascii=False)
comp_mapping_js = json.dumps(comp_mapping, ensure_ascii=False)

# Count stats
total_scq = sum(len(s.get('SCQs',{})) for c in content.values() for s in c.values())
total_subj = sum(len(s.get('SubjectiveTypes',{})) for c in content.values() for s in c.values())
total_ex = sum(len(s.get('Examples',{})) for c in content.values() for s in c.values())

html = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Acadza Content Review — Light: Reflection and Refraction</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet"/>
<script>
window.MathJax = {
  tex: { inlineMath: [['\\\\(','\\\\)']], displayMath: [['\\\\[','\\\\]']] },
  startup: { typeset: false }
};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" async></script>
<style>
:root {
  --bg: #F8F6F3;
  --surface: #FFFFFF;
  --surface2: #F3F0EC;
  --surface3: #EAE6E0;
  --accent: #ff8008;
  --accent-light: #FFF3E8;
  --accent-hover: #e67000;
  --text: #2D2A26;
  --text2: #6B6560;
  --text3: #9C9590;
  --green: #3D8B63;
  --green-light: #E2F0E8;
  --red: #C0392B;
  --red-light: #FDEBEB;
  --blue: #4A78A0;
  --blue-light: #E8EFF5;
  --navy: #1B2A4A;
  --border: #E5DFD6;
  --border-light: #F0EBE3;
  --shadow-sm: 0 1px 3px rgba(45,42,38,0.06);
  --shadow-md: 0 4px 12px rgba(45,42,38,0.08);
  --radius: 12px;
  --radius-sm: 8px;
}
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;
  -webkit-font-smoothing:antialiased;line-height:1.65;font-size:15px}

/* Header */
.sticky-top{position:sticky;top:0;z-index:100;background:var(--surface);box-shadow:var(--shadow-md)}
header{padding:12px 24px;display:flex;align-items:center;justify-content:space-between;border-bottom:3px solid var(--accent)}
header .logo{height:32px}
header h1{font-size:1.1rem;color:var(--navy);font-weight:700}
header h1 span{color:var(--text2);font-weight:400;font-size:0.82rem;margin-left:6px}
.header-right{display:flex;gap:14px;align-items:center}
.score-tracker{font-size:0.8rem;color:var(--text2);background:var(--surface2);padding:5px 12px;border-radius:20px}
.score-correct{color:var(--green);font-weight:700}
.score-wrong{color:var(--red);font-weight:700}
.stats-bar{display:flex;gap:16px;padding:7px 24px;background:var(--surface2);font-size:0.75rem;color:var(--text2);
  font-weight:500;border-bottom:1px solid var(--border-light);flex-wrap:wrap}
.stats-bar span{color:var(--green);font-weight:700}

/* Layout */
.main-layout{display:flex;min-height:calc(100vh - 100px);position:relative}
.sidebar{width:280px;min-width:280px;background:var(--surface);border-right:1px solid var(--border-light);
  padding:16px 12px;overflow-y:auto;max-height:calc(100vh - 100px);position:sticky;top:100px;
  transition:width 0.25s ease,min-width 0.25s ease,padding 0.25s ease,opacity 0.2s ease}
.main-layout.sidebar-hidden .sidebar{width:0;min-width:0;padding:0;overflow:hidden;opacity:0}
.content{flex:1;min-width:0;max-width:800px;margin:0 auto;padding:24px 32px}

/* Sidebar Toggle */
.sidebar-toggle{position:sticky;top:100px;align-self:flex-start;width:26px;min-width:26px;height:44px;
  background:var(--surface2);border:1.5px solid var(--border);border-left:none;
  border-radius:0 var(--radius-sm) var(--radius-sm) 0;cursor:pointer;display:flex;align-items:center;
  justify-content:center;color:var(--accent);font-size:0.7rem;z-index:10;margin-left:-1px;flex-shrink:0;
  transition:background 0.2s}
.sidebar-toggle:hover{background:var(--accent-light);border-color:var(--accent)}
.toggle-icon{transition:transform 0.25s ease;display:inline-block}
.main-layout.sidebar-hidden .toggle-icon{transform:rotate(180deg)}

/* Sidebar Items */
.sidebar h3{color:var(--accent);font-size:0.65rem;text-transform:uppercase;letter-spacing:1px;
  padding:12px 8px 6px;font-weight:700}
.sidebar-group{margin-bottom:4px}
.sidebar-concept{padding:8px 10px;font-size:0.82rem;font-weight:600;color:var(--navy);cursor:pointer;
  border-radius:var(--radius-sm);transition:background 0.15s}
.sidebar-concept:hover{background:var(--surface2)}
.sidebar-sub{padding:7px 10px 7px 24px;font-size:0.8rem;color:var(--text2);cursor:pointer;
  border-radius:var(--radius-sm);transition:all 0.15s;display:flex;justify-content:space-between;align-items:center}
.sidebar-sub:hover{background:rgba(255,128,8,0.06);color:var(--text)}
.sidebar-sub.active{background:rgba(255,128,8,0.12);color:var(--accent);font-weight:600;border-left:3px solid var(--accent)}
.sidebar-sub .badge{font-size:0.65rem;background:var(--surface2);color:var(--text3);padding:2px 6px;border-radius:10px}

/* Cards */
.card{background:var(--surface);border:1px solid var(--border-light);border-radius:var(--radius);
  margin-bottom:16px;box-shadow:var(--shadow-sm);overflow:hidden}
.card-header{padding:16px 20px;border-bottom:1px solid var(--border-light)}
.card-body{padding:16px 20px}
.section-title{font-size:1rem;font-weight:700;color:var(--navy);margin:24px 0 12px;display:flex;align-items:center;gap:8px}
.section-icon{width:24px;height:24px;border-radius:6px;display:flex;align-items:center;justify-content:center;
  font-size:0.7rem;font-weight:800;color:#fff}

/* Theory */
.theory-text{font-size:0.95rem;line-height:1.85;color:var(--text);font-weight:420}
.theory-text strong{color:var(--navy);font-weight:700}
.theory-text p{margin-bottom:0.8rem}
.content-img{max-width:100%;height:auto;max-height:260px;border-radius:var(--radius-sm);border:1px solid var(--border);margin:8px 0}
.img-caption{font-size:0.72rem;color:var(--text3);font-style:italic;margin-top:2px}

/* Labels */
.label{display:inline-block;padding:2px 8px;border-radius:4px;font-size:0.68rem;font-weight:600;letter-spacing:0.3px}
.label-source{background:#EDE7F6;color:#5E35B1}
.label-generated{background:var(--blue-light);color:var(--blue)}
.label-easy{background:var(--green-light);color:var(--green)}
.label-medium{background:#FFF8E1;color:#F57F17}
.label-hard{background:var(--red-light);color:var(--red)}
.label-format{background:var(--surface2);color:var(--text3)}

/* Question */
.q-text{font-size:0.95rem;line-height:1.8;color:var(--text);font-weight:450;margin:8px 0}

/* Options */
.options-grid{display:flex;flex-direction:column;gap:8px;margin:14px 0}
.option-card{display:flex;align-items:flex-start;gap:14px;padding:13px 16px;border:2px solid var(--border);
  border-radius:var(--radius-sm);cursor:pointer;transition:all 0.15s;background:var(--surface);user-select:none}
.option-card:hover:not(.disabled){border-color:var(--accent);background:#FDF8F4;box-shadow:var(--shadow-sm)}
.option-card.selected{border-color:var(--accent);background:#FDF8F4;box-shadow:0 0 0 3px rgba(255,128,8,0.1)}
.option-card.correct{border-color:var(--green)!important;background:var(--green-light)!important;box-shadow:0 0 0 3px rgba(61,139,99,0.1)!important}
.option-card.incorrect{border-color:var(--red)!important;background:var(--red-light)!important}
.option-card.missed{border-color:var(--green)!important;background:var(--green-light)!important;opacity:0.65}
.option-card.disabled{cursor:default}
.option-label{display:flex;align-items:center;justify-content:center;min-width:28px;height:28px;border-radius:50%;
  background:var(--surface2);font-weight:800;font-size:0.75rem;color:var(--text2);flex-shrink:0;border:2px solid var(--border);transition:all 0.15s}
.option-card.selected .option-label{background:var(--accent);color:#fff;border-color:var(--accent)}
.option-card.correct .option-label{background:var(--green);color:#fff;border-color:var(--green)}
.option-card.incorrect .option-label{background:var(--red);color:#fff;border-color:var(--red)}
.option-card.missed .option-label{background:var(--green);color:#fff;border-color:var(--green)}
.option-text{flex:1;font-size:0.88rem;line-height:1.6;padding-top:2px}
.option-icon{font-size:1rem;flex-shrink:0;padding-top:2px;font-weight:700}

/* Numeric Input */
.numeric-group{display:flex;gap:12px;align-items:center;margin:14px 0}
.numeric-input{width:180px;padding:10px 14px;border:2px solid var(--border);border-radius:var(--radius-sm);
  font-size:0.95rem;color:var(--text);background:var(--surface);transition:all 0.2s}
.numeric-input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(255,128,8,0.1)}
.numeric-input.correct{border-color:var(--green);background:var(--green-light)}
.numeric-input.incorrect{border-color:var(--red);background:var(--red-light)}
.numeric-feedback{font-weight:700;font-size:0.85rem}
.numeric-feedback.correct{color:var(--green)}
.numeric-feedback.incorrect{color:var(--red)}

/* Text Area */
.text-area{width:100%;min-height:80px;padding:10px 14px;border:2px solid var(--border);border-radius:var(--radius-sm);
  font-size:0.88rem;font-family:inherit;color:var(--text);resize:vertical;transition:border-color 0.2s}
.text-area:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(255,128,8,0.1)}
.text-area.submitted{background:var(--green-light);border-color:var(--green)}

/* Buttons */
.q-actions{display:flex;gap:10px;padding:4px 0 8px;align-items:center;flex-wrap:wrap}
.submit-btn{padding:9px 24px;border:none;border-radius:var(--radius-sm);cursor:pointer;font-size:0.85rem;
  font-weight:700;transition:all 0.2s;background:var(--surface3);color:var(--text3);pointer-events:none}
.submit-btn.active{background:var(--accent);color:#fff;pointer-events:auto;box-shadow:0 3px 12px rgba(255,128,8,0.3)}
.submit-btn.active:hover{background:var(--accent-hover);transform:translateY(-1px)}
.submit-btn.submitted{background:var(--green);color:#fff;pointer-events:none}
.btn-reset{padding:7px 16px;border:none;border-radius:var(--radius-sm);cursor:pointer;font-size:0.78rem;
  font-weight:600;background:var(--surface3);color:var(--text2);transition:all 0.2s}
.btn-reset:hover{background:var(--border);color:var(--text)}
.btn-sol{padding:8px 18px;border:none;border-radius:var(--radius-sm);cursor:pointer;font-size:0.82rem;
  font-weight:600;background:var(--green);color:#fff;box-shadow:0 2px 6px rgba(61,139,99,0.2);transition:all 0.2s}
.btn-sol:hover{background:#2E7D4B;transform:translateY(-1px)}

/* Result Banner */
.result-banner{padding:10px 16px;border-radius:var(--radius-sm);margin:10px 0;font-weight:700;font-size:0.85rem;
  display:flex;align-items:center;gap:8px}
.result-banner.correct{background:var(--green-light);color:var(--green);border:1.5px solid var(--green)}
.result-banner.incorrect{background:var(--red-light);color:var(--red);border:1.5px solid var(--red)}

/* Solution Panel */
.sol-panel{margin:12px 0;padding:16px;background:var(--surface2);border-radius:var(--radius-sm);
  border-left:4px solid var(--green);display:none}
.sol-panel.visible{display:block}
.sol-panel h4{font-size:0.78rem;color:var(--green);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;font-weight:700}
.sol-text{font-size:0.9rem;line-height:1.75;color:var(--text);font-weight:420}

/* Mobile */
@media(max-width:768px){
  .sidebar{position:fixed;top:0;left:0;bottom:0;z-index:200;width:85vw!important;min-width:85vw!important;
    max-height:100vh;transform:translateX(-100%);box-shadow:var(--shadow-lg)}
  .sidebar.mobile-open{transform:translateX(0)}
  .sidebar-toggle{display:none}
  .content{padding:16px!important}
  header{flex-direction:column;align-items:center;gap:4px;padding:10px 16px}
  header .header-inner{flex-direction:column!important;align-items:center!important;gap:6px!important}
  header .logo{height:28px}
  header h1{font-size:0.95rem;text-align:center}
  header h1 span{display:block;margin-left:0!important;margin-top:2px}
  .header-right{justify-content:center}
  .stats-bar{justify-content:center}
  .mobile-toggle{display:flex!important}
  .mobile-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.3);z-index:199}
  .mobile-overlay.visible{display:block}
}
@media(min-width:769px){.mobile-toggle{display:none!important}.mobile-overlay{display:none!important}}
</style>
</head>
<body>

<div class="sticky-top">
  <header>
    <div class="header-inner" style="display:flex;align-items:center;gap:10px">
      <button class="mobile-toggle" onclick="app.toggleMobile()" style="background:none;border:none;cursor:pointer;font-size:1.3rem;color:var(--accent)">&#9776;</button>
      <img src="data:image/png;base64,''' + logo_b64 + '''" alt="Acadza" class="logo"/>
      <h1>Content Review<span>| Chapter: Light — Reflection and Refraction</span></h1>
    </div>
    <div class="header-right">
      <button id="modeToggle" onclick="app.toggleMode()" style="padding:6px 16px;border:2px solid var(--accent);border-radius:20px;background:var(--surface);color:var(--accent);font-weight:700;font-size:0.78rem;cursor:pointer;transition:all 0.2s">
        Competitive Mode
      </button>
      <div class="score-tracker">
        <span class="score-correct" id="scoreCorrect">0</span> correct
        <span class="score-wrong" id="scoreWrong">0</span> wrong
      </div>
    </div>
  </header>
  <div class="stats-bar">
    <div>Concepts: <span>3</span></div>
    <div>Subconcepts: <span>14</span></div>
    <div>SCQs: <span>''' + str(total_scq) + '''</span></div>
    <div>Subjective: <span>''' + str(total_subj) + '''</span></div>
    <div>Examples: <span>''' + str(total_ex) + '''</span></div>
  </div>
</div>

<div class="mobile-overlay" id="mobileOverlay" onclick="app.toggleMobile()"></div>

<div class="main-layout" id="mainLayout">
  <aside class="sidebar" id="sidebar"></aside>
  <button class="sidebar-toggle" id="sidebarToggle" onclick="app.toggleSidebar()">
    <span class="toggle-icon" id="toggleIcon">&#9664;</span>
  </button>
  <main class="content" id="contentArea">
    <div id="welcome" style="text-align:center;padding:60px 20px">
      <h2 style="font-size:1.5rem;color:var(--navy);margin-bottom:8px">Class 10, Physics</h2>
      <h3 style="font-size:1.1rem;color:var(--text2);font-weight:400;margin-bottom:24px">Chapter: Light — Reflection and Refraction</h3>
      <p style="color:var(--text3)">Select a subconcept from the sidebar to begin reviewing.</p>
    </div>
    <div id="subView" style="display:none"></div>
  </main>
</div>

<script>
const CONTENT = ''' + content_js + ''';
const SCHEMA = ''' + schema_js + ''';
const IMAGES = ''' + image_urls_js + ''';
const COMP_TOPOLOGY = ''' + comp_topology_js + ''';
const COMP_MAPPING = ''' + comp_mapping_js + ''';
let currentMode = 'ncert'; // 'ncert' or 'competitive'

const qState = {};
let scoreCorrect = 0, scoreWrong = 0;

const app = {
  init() {
    this.buildSidebar();
  },

  toggleSidebar() {
    document.getElementById('mainLayout').classList.toggle('sidebar-hidden');
  },

  toggleMobile() {
    const sb = document.getElementById('sidebar');
    const ov = document.getElementById('mobileOverlay');
    sb.classList.toggle('mobile-open');
    ov.classList.toggle('visible');
  },

  buildSidebar() {
    const sb = document.getElementById('sidebar');
    const ch = Object.keys(SCHEMA)[0];
    let h = '<h3>Content Index</h3>';
    for (const [cn, subs] of Object.entries(SCHEMA[ch])) {
      h += '<div class="sidebar-group"><div class="sidebar-concept">' + cn + '</div>';
      for (const sub of subs) {
        const ck = 'Concept: ' + cn, sk = 'Subconcept: ' + sub;
        const d = CONTENT[ck]?.[sk];
        const n = d ? Object.keys(d.SCQs||{}).length + Object.keys(d.SubjectiveTypes||{}).length + Object.keys(d.Examples||{}).length : 0;
        h += '<div class="sidebar-sub" onclick="app.selectSub(\\'' + ck.replace(/'/g,"\\\\'") + '\\',\\'' + sk.replace(/'/g,"\\\\'") + '\\',this)">' +
          '<span>' + sub + '</span><span class="badge">' + n + '</span></div>';
      }
      h += '</div>';
    }
    sb.innerHTML = h;
  },

  selectSub(ck, sk, el) {
    document.querySelectorAll('.sidebar-sub').forEach(e => e.classList.remove('active'));
    if (el) el.classList.add('active');
    const d = CONTENT[ck]?.[sk];
    if (!d) return;
    document.getElementById('welcome').style.display = 'none';
    const v = document.getElementById('subView');
    v.style.display = 'block';
    v.innerHTML = this.renderSub(sk.replace('Subconcept: ',''), d);
    if (window.MathJax?.typesetPromise) MathJax.typesetPromise([v]);
    // Close mobile sidebar
    document.getElementById('sidebar').classList.remove('mobile-open');
    document.getElementById('mobileOverlay').classList.remove('visible');
    setTimeout(() => v.scrollIntoView({behavior:'smooth',block:'start'}), 100);
  },

  md(t) {
    if (!t) return '';
    return t.replace(/\\\\n/g,'<br>')
      .replace(/\\n/g,'<br>')
      .replace(/\\*\\*(.+?)\\*\\*/g,'<strong>$1</strong>')
      .replace(/Assertion \\(A\\):/g,'<strong>Assertion (A):</strong>')
      .replace(/Reason \\(R\\):/g,'<strong>Reason (R):</strong>');
  },

  img(vc) {
    if (!vc || (!vc.needed && !vc.Needed)) return '';
    const ref = vc.source_image_ref;
    if (ref && IMAGES[ref]) return '<div style="margin:8px 0"><img src="'+IMAGES[ref]+'" class="content-img"/>' +
      (vc.image_description ? '<p class="img-caption">'+vc.image_description+'</p>' : '') + '</div>';
    if (vc.image_generation_needed) return '<p class="img-caption">[Diagram: '+(vc.generation_description||'').substring(0,80)+'...]</p>';
    return '';
  },

  // Get question-specific or solution-specific visual content
  // Supports v7 schema (QuestionVisualContent/SolutionVisualContent) and v6 fallback (single VisualContent)
  getQVC(q) { return q.QuestionVisualContent || null; },
  getSVC(q) { return q.SolutionVisualContent || null; },
  // v6 fallback: use text heuristic to decide placement of single VisualContent
  inferImagePlacement(q) {
    const vc = q.VisualContent;
    if (!vc || (!vc.needed && !vc.Needed)) return { qvc: null, svc: null };
    // If v7 fields exist, use them directly
    if (q.QuestionVisualContent || q.SolutionVisualContent) return { qvc: q.QuestionVisualContent, svc: q.SolutionVisualContent };
    // v6 fallback: check where "figure below" is mentioned
    const qText = (q.Question || '').toLowerCase();
    const sText = (q.Solution || '').toLowerCase();
    const figInQ = qText.includes('figure below') || qText.includes('figure above') || qText.includes('diagram shown');
    const figInS = sText.includes('figure below') || sText.includes('figure above') || sText.includes('ray diagram');
    if (figInQ && !figInS) return { qvc: vc, svc: null };
    if (figInS && !figInQ) return { qvc: null, svc: vc };
    if (figInQ && figInS) return { qvc: null, svc: vc }; // prefer solution to avoid redundancy
    // Neither mentions it — default to solution (most common case)
    return { qvc: null, svc: vc };
  },

  labels(q) {
    const src = q._source === 'generated' ? '<span class="label label-generated">Generated</span>' :
                q._source === 'ncert' ? '<span class="label label-source">NCERT</span>' :
                '<span class="label label-source">Source</span>';
    const diff = q.Difficulty === 'Easy' ? '<span class="label label-easy">Easy</span>' :
                 q.Difficulty === 'Hard' ? '<span class="label label-hard">Hard</span>' :
                 '<span class="label label-medium">Medium</span>';
    let fmt = '';
    if (q.scq_format) fmt = '<span class="label label-format">'+q.scq_format+'</span>';
    if (q.answer_format) fmt = '<span class="label label-format">'+q.answer_format+'</span>';
    return '<div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px">'+src+diff+fmt+'</div>';
  },

  parseOptions(qText) {
    // Extract options from question text: (A) text... (B) text...
    // For assertion-reason, skip "Assertion (A):" — find last (A) that has (B) after it
    const parts = [];
    let optStart = -1, searchFrom = 0;
    while (true) {
      const idx = qText.indexOf('(A)', searchFrom);
      if (idx === -1) break;
      if (qText.indexOf('(B)', idx) > idx) optStart = idx;
      searchFrom = idx + 3;
    }
    if (optStart < 0) return { stem: qText, options: [] };
    const stem = qText.substring(0, optStart).trim();
    const rest = qText.substring(optStart);
    const regex = /\\(([A-D])\\)\\s*([\\s\\S]*?)(?=\\([A-D]\\)|$)/g;
    let m;
    while ((m = regex.exec(rest)) !== null) {
      parts.push({ label: m[1], text: m[2].trim() });
    }
    return { stem, options: parts };
  },

  getState(qid) {
    if (!qState[qid]) qState[qid] = { selection: null, submitted: false, numericValue: '', textValue: '' };
    return qState[qid];
  },

  selectOption(qid, label) {
    const s = this.getState(qid);
    if (s.submitted) return;
    s.selection = label;
    this.rerender(qid);
  },

  numericInput(qid, val) {
    const s = this.getState(qid);
    if (s.submitted) return;
    s.numericValue = val;
    document.getElementById('submit-'+qid).className = 'submit-btn' + (val ? ' active' : '');
  },

  textInput(qid, val) {
    const s = this.getState(qid);
    s.textValue = val;
    document.getElementById('submit-'+qid).className = 'submit-btn' + (val.trim() ? ' active' : '');
  },

  submitAnswer(qid, correctAnswer, qtype) {
    const s = this.getState(qid);
    if (s.submitted) return;
    s.submitted = true;

    if (qtype === 'scq') {
      const correct = s.selection === correctAnswer;
      if (correct) scoreCorrect++; else scoreWrong++;
    } else if (qtype === 'numerical') {
      // Try numeric comparison
      const userVal = parseFloat(s.numericValue);
      const correctVal = parseFloat(correctAnswer);
      if (!isNaN(userVal) && !isNaN(correctVal) && Math.abs(userVal - correctVal) < 0.01) {
        scoreCorrect++;
      } else {
        scoreWrong++;
      }
    } else {
      // Descriptive — always accept
      scoreCorrect++;
    }

    document.getElementById('scoreCorrect').textContent = scoreCorrect;
    document.getElementById('scoreWrong').textContent = scoreWrong;
    this.rerender(qid);
  },

  resetQuestion(qid) {
    const s = this.getState(qid);
    if (s.submitted) {
      // Undo score
      scoreCorrect = Math.max(0, scoreCorrect - (s._wasCorrect ? 1 : 0));
      scoreWrong = Math.max(0, scoreWrong - (s._wasCorrect ? 0 : 1));
    }
    delete qState[qid];
    document.getElementById('scoreCorrect').textContent = scoreCorrect;
    document.getElementById('scoreWrong').textContent = scoreWrong;
    this.rerender(qid);
  },

  toggleSolution(solId) {
    const el = document.getElementById(solId);
    if (!el) return;
    el.classList.toggle('visible');
    if (el.classList.contains('visible') && window.MathJax) {
      if (MathJax.typesetClear) MathJax.typesetClear([el]);
      if (MathJax.typesetPromise) setTimeout(() => MathJax.typesetPromise([el]), 80);
    }
  },

  rerender(qid) {
    const el = document.getElementById('q-'+qid);
    if (!el) return;
    const data = JSON.parse(el.dataset.q);
    el.innerHTML = this.renderQuestionInner(qid, data);
    if (window.MathJax?.typesetPromise) MathJax.typesetPromise([el]);
  },

  renderQuestionInner(qid, q) {
    const s = this.getState(qid);
    const parsed = this.parseOptions(q.Question || '');
    let h = this.labels(q);

    // Question stem
    h += '<div class="q-text">' + this.md(parsed.stem) + '</div>';
    // Image placement: question-level image if applicable
    const { qvc, svc } = this.inferImagePlacement(q);
    if (qvc) h += this.img(qvc);

    if (parsed.options.length >= 3) {
      // SCQ with options
      h += '<div class="options-grid">';
      for (const opt of parsed.options) {
        let cls = 'option-card';
        let icon = '';
        if (s.submitted) {
          cls += ' disabled';
          const isCorrect = opt.label === q.Answer;
          if (s.selection === opt.label) {
            cls += isCorrect ? ' correct' : ' incorrect';
            icon = isCorrect ? '<span class="option-icon">&#10003;</span>' : '<span class="option-icon">&#10007;</span>';
          } else if (isCorrect) {
            cls += ' missed';
            icon = '<span class="option-icon">&#10003;</span>';
          }
        } else if (s.selection === opt.label) {
          cls += ' selected';
        }
        const click = s.submitted ? '' : ' onclick="app.selectOption(\\''+qid+'\\',\\''+opt.label+'\\')\"';
        h += '<div class="'+cls+'"'+click+'><span class="option-label">'+opt.label+'</span><span class="option-text">'+this.md(opt.text)+'</span>'+icon+'</div>';
      }
      h += '</div>';

      // Submit/Reset
      h += '<div class="q-actions">';
      if (s.submitted) {
        const correct = s.selection === q.Answer;
        s._wasCorrect = correct;
        h += '<button class="submit-btn submitted">Submitted</button>';
        h += '<button class="btn-reset" onclick="app.resetQuestion(\\''+qid+'\\')">Reset</button>';
        if (q.Solution) h += '<button class="btn-sol" onclick="app.toggleSolution(\\'sol-'+qid+'\\')">Show Solution</button>';
      } else {
        h += '<button class="submit-btn'+(s.selection ? ' active' : '')+'" id="submit-'+qid+'" onclick="app.submitAnswer(\\''+qid+'\\',\\''+q.Answer+'\\',\\'scq\\')">Submit</button>';
      }
      h += '</div>';

      if (s.submitted) {
        const correct = s.selection === q.Answer;
        h += '<div class="result-banner '+(correct?'correct':'incorrect')+'">'+(correct?'&#10003; Correct!':'&#10007; Incorrect. Answer: '+q.Answer)+'</div>';
      }

    } else if (q.answer_format === 'numerical') {
      // Numeric input
      let inputCls = 'numeric-input', feedback = '';
      if (s.submitted) {
        const userVal = parseFloat(s.numericValue);
        const answer = q.Answer || '';
        const numMatch = answer.match(/-?[\\d.]+/);
        const correctVal = numMatch ? parseFloat(numMatch[0]) : NaN;
        const correct = !isNaN(userVal) && !isNaN(correctVal) && Math.abs(userVal - correctVal) < 0.1;
        inputCls += correct ? ' correct' : ' incorrect';
        feedback = correct ? '<span class="numeric-feedback correct">&#10003; Correct!</span>'
          : '<span class="numeric-feedback incorrect">&#10007; Answer: '+q.Answer+'</span>';
        s._wasCorrect = correct;
      }
      h += '<div class="numeric-group"><input type="number" class="'+inputCls+'" id="num-'+qid+'" placeholder="Your answer..."' +
        ' value="'+(s.numericValue||'')+'" '+(s.submitted?'disabled':'')+' oninput="app.numericInput(\\''+qid+'\\',this.value)">'+feedback+'</div>';
      h += '<div class="q-actions">';
      if (s.submitted) {
        h += '<button class="submit-btn submitted">Submitted</button>';
        h += '<button class="btn-reset" onclick="app.resetQuestion(\\''+qid+'\\')">Reset</button>';
        if (q.Solution) h += '<button class="btn-sol" onclick="app.toggleSolution(\\'sol-'+qid+'\\')">Show Solution</button>';
      } else {
        h += '<button class="submit-btn'+(s.numericValue?' active':'')+'" id="submit-'+qid+'" onclick="app.submitAnswer(\\''+qid+'\\',\\''+q.Answer+'\\',\\'numerical\\')">Submit</button>';
      }
      h += '</div>';

    } else {
      // Descriptive text area
      h += '<textarea class="text-area'+(s.submitted?' submitted':'')+'" id="txt-'+qid+'" placeholder="Type your answer..."' +
        (s.submitted?' disabled':'') + ' oninput="app.textInput(\\''+qid+'\\',this.value)">'+(s.textValue||'')+'</textarea>';
      h += '<div class="q-actions">';
      if (s.submitted) {
        h += '<button class="submit-btn submitted">Submitted</button>';
        h += '<button class="btn-reset" onclick="app.resetQuestion(\\''+qid+'\\')">Reset</button>';
        if (q.Solution) h += '<button class="btn-sol" onclick="app.toggleSolution(\\'sol-'+qid+'\\')">Show Solution</button>';
      } else {
        h += '<button class="submit-btn'+(s.textValue?.trim()?' active':'')+'" id="submit-'+qid+'" onclick="app.submitAnswer(\\''+qid+'\\',\\'\\',\\'descriptive\\')">Submit</button>';
      }
      h += '</div>';
      if (s.submitted) h += '<div class="result-banner correct">&#10003; Answer recorded</div>';
    }

    // Solution panel (hidden until Show Solution clicked)
    if (q.Solution && s.submitted) {
      h += '<div class="sol-panel" id="sol-'+qid+'"><h4>Solution</h4><div class="sol-text">'+this.md(q.Solution)+'</div>';
      if (svc) h += this.img(svc);
      h += '</div>';
    }
    return h;
  },

  renderSub(name, data) {
    const scqs = Object.entries(data.SCQs || {});
    const subjs = Object.entries(data.SubjectiveTypes || {});
    const exs = Object.entries(data.Examples || {});
    const srcQ = [...scqs,...subjs].filter(([k,q])=>q._source!=='generated').length;
    const genQ = [...scqs,...subjs].filter(([k,q])=>q._source==='generated').length;

    let h = '<h2 style="font-size:1.4rem;font-weight:700;color:var(--navy);margin-bottom:4px">'+name+'</h2>';
    h += '<p style="font-size:0.82rem;color:var(--text2);margin-bottom:20px">'+(scqs.length+subjs.length)+' Questions ('+srcQ+' source + '+genQ+' generated) &bull; '+exs.length+' Examples</p>';

    // Theory
    if (data.Summary?.Theory) {
      h += '<div class="card"><div class="card-header"><div class="section-title"><span class="section-icon" style="background:var(--blue)">T</span>Theory</div></div>';
      h += '<div class="card-body"><div class="theory-text">'+this.md(data.Summary.Theory)+'</div>';
      h += this.img(data.Summary.VisualContent);
      h += '</div></div>';
    }

    // SCQs
    if (scqs.length) {
      h += '<div class="section-title"><span class="section-icon" style="background:var(--green)">Q</span>Single Choice Questions ('+scqs.length+')</div>';
      for (const [key, q] of scqs) {
        const qid = 'scq_'+name.replace(/[^a-zA-Z0-9]/g,'_')+'_'+key.replace(/[^a-zA-Z0-9]/g,'_');
        h += '<div class="card"><div class="card-body" id="q-'+qid+'" data-q=\\''+JSON.stringify(q).replace(/'/g,"&#39;").replace(/\\\\/g,"\\\\\\\\")+'\\'>'+this.renderQuestionInner(qid, q)+'</div></div>';
      }
    }

    // Subjective
    if (subjs.length) {
      h += '<div class="section-title"><span class="section-icon" style="background:#F57F17">S</span>Subjective Questions ('+subjs.length+')</div>';
      for (const [key, q] of subjs) {
        const qid = 'subj_'+name.replace(/[^a-zA-Z0-9]/g,'_')+'_'+key.replace(/[^a-zA-Z0-9]/g,'_');
        h += '<div class="card"><div class="card-body" id="q-'+qid+'" data-q=\\''+JSON.stringify(q).replace(/'/g,"&#39;").replace(/\\\\/g,"\\\\\\\\")+'\\'>'+this.renderQuestionInner(qid, q)+'</div></div>';
      }
    }

    // Examples
    if (exs.length) {
      h += '<div class="section-title"><span class="section-icon" style="background:#7E57C2">E</span>Solved Examples ('+exs.length+')</div>';
      for (const [key, ex] of exs) {
        const src = ex.isFromNCERT || ex._source==='ncert' ? '<span class="label label-source">NCERT</span>' : '<span class="label label-generated">Generated</span>';
        const diff = '<span class="label label-'+(ex.Difficulty||'Medium').toLowerCase()+'">'+(ex.Difficulty||'Medium')+'</span>';
        h += '<div class="card"><div class="card-body">';
        h += '<div style="display:flex;gap:4px;margin-bottom:8px">'+src+diff+'</div>';
        h += '<div class="q-text">'+this.md(ex.Question||'')+'</div>';
        h += this.img(ex.VisualContent);
        if (ex.Solution) {
          h += '<details style="margin-top:12px" ontoggle="if(this.open&&window.MathJax){if(MathJax.typesetClear)MathJax.typesetClear([this]);if(MathJax.typesetPromise)setTimeout(()=>MathJax.typesetPromise([this]),80)}"><summary style="cursor:pointer;color:var(--green);font-weight:600;font-size:0.88rem">Show Solution</summary>';
          h += '<div class="sol-panel visible" style="margin-top:8px"><div class="sol-text">'+this.md(ex.Solution)+'</div></div></details>';
        }
        h += '</div></div>';
      }
    }
    return h;
  },

  toggleMode() {
    currentMode = currentMode === 'ncert' ? 'competitive' : 'ncert';
    const btn = document.getElementById('modeToggle');
    if (currentMode === 'competitive') {
      btn.textContent = 'NCERT Mode';
      btn.style.background = 'var(--accent)';
      btn.style.color = '#fff';
      this.buildCompSidebar();
    } else {
      btn.textContent = 'Competitive Mode';
      btn.style.background = 'var(--surface)';
      btn.style.color = 'var(--accent)';
      this.buildSidebar();
    }
    document.getElementById('welcome').style.display = 'block';
    document.getElementById('subView').style.display = 'none';
  },

  buildCompSidebar() {
    const sb = document.getElementById('sidebar');
    let h = '<h3 style="color:var(--accent)">Competitive Mode</h3>';
    h += '<p style="font-size:0.7rem;color:var(--text3);padding:0 8px 8px">Foundation content mapped to NCERT</p>';
    if (!COMP_TOPOLOGY.concepts) { sb.innerHTML = h + '<p style="padding:8px;color:var(--text3)">No competitive data loaded</p>'; return; }

    // Build lookup for fast access
    const mappingLookup = {};
    COMP_MAPPING.forEach(m => { mappingLookup[m.comp] = m; });

    for (const concept of COMP_TOPOLOGY.concepts) {
      const isConn = concept.is_connecting_topic;
      const badge = isConn ? ' <span style="font-size:0.6rem;background:#7E57C2;color:#fff;padding:1px 5px;border-radius:3px">EXTRA</span>' : '';
      h += '<div class="sidebar-group">';
      h += '<div class="sidebar-concept" style="cursor:pointer" data-expand="1">' + concept.name + badge + '</div>';
      h += '<div class="comp-subs" style="display:none">';
      for (const sub of concept.subconcepts) {
        const m = mappingLookup[sub.id] || {};
        const status = m.status || 'unknown';
        const statusBadge = status === 'overlap'
          ? '<span style="font-size:0.55rem;background:var(--green-light);color:var(--green);padding:1px 4px;border-radius:3px">NCERT</span>'
          : '<span style="font-size:0.55rem;background:#EDE7F6;color:#5E35B1;padding:1px 4px;border-radius:3px">NEW</span>';
        const connBadge = sub.is_connecting_topic ? ' <span style="font-size:0.55rem;background:#FFF3E8;color:var(--accent);padding:1px 4px;border-radius:3px">ADV</span>' : '';
        h += '<div class="sidebar-sub" data-comp-id="'+sub.id+'" data-label="'+concept.name.replace(/"/g,'&quot;')+' &mdash; '+sub.name.replace(/"/g,'&quot;')+'" data-ncert="'+(m.ncert_sub||'').replace(/"/g,'&quot;')+'" data-status="'+status+'">';
        h += '<span>' + sub.name + connBadge + '</span>' + statusBadge;
        h += '</div>';
      }
      h += '</div></div>';
    }
    sb.innerHTML = h;

    // Bind click events (safer than inline onclick with complex strings)
    sb.querySelectorAll('[data-expand]').forEach(el => {
      el.addEventListener('click', () => {
        const subs = el.nextElementSibling;
        subs.style.display = subs.style.display === 'none' ? 'block' : 'none';
      });
    });
    sb.querySelectorAll('[data-comp-id]').forEach(el => {
      el.addEventListener('click', () => {
        app.selectCompSub(el.dataset.compId, el.dataset.label, el.dataset.ncert, el.dataset.status, el);
      });
    });
  },

  selectCompSub(compId, label, ncertSub, status, el) {
    document.querySelectorAll('.sidebar-sub').forEach(e => e.classList.remove('active'));
    if (el) el.classList.add('active');
    document.getElementById('welcome').style.display = 'none';
    const v = document.getElementById('subView');
    v.style.display = 'block';

    let h = '<h2 style="font-size:1.3rem;font-weight:700;color:var(--navy);margin-bottom:4px">' + label + '</h2>';

    if (status === 'overlap' && ncertSub) {
      h += '<div style="display:flex;gap:6px;margin-bottom:16px;flex-wrap:wrap">';
      h += '<span class="label label-source">Mapped to NCERT</span>';
      h += '<span class="label label-format">' + ncertSub + '</span>';
      h += '</div>';

      // Find NCERT content for this subconcept
      const sk = 'Subconcept: ' + ncertSub;
      let ncertData = null;
      for (const [ck, subs] of Object.entries(CONTENT)) {
        if (subs[sk]) { ncertData = subs[sk]; break; }
      }

      if (ncertData) {
        // Show NCERT theory
        if (ncertData.Summary && ncertData.Summary.Theory) {
          h += '<div class="card"><div class="card-header"><div class="section-title"><span class="section-icon" style="background:var(--blue)">T</span>Theory (from NCERT)</div></div>';
          h += '<div class="card-body"><div class="theory-text">' + this.md(ncertData.Summary.Theory) + '</div></div></div>';
        }
        // Show counts
        const scqCount = Object.keys(ncertData.SCQs || {}).length;
        const subjCount = Object.keys(ncertData.SubjectiveTypes || {}).length;
        const exCount = Object.keys(ncertData.Examples || {}).length;
        if (scqCount + subjCount + exCount > 0) {
          h += '<div style="display:flex;gap:12px;flex-wrap:wrap;margin:12px 0">';
          if (scqCount) h += '<div class="card" style="flex:1;min-width:120px;text-align:center;padding:16px"><div style="font-size:1.5rem;font-weight:800;color:var(--green)">' + scqCount + '</div><div style="font-size:0.75rem;color:var(--text2)">SCQs</div></div>';
          if (subjCount) h += '<div class="card" style="flex:1;min-width:120px;text-align:center;padding:16px"><div style="font-size:1.5rem;font-weight:800;color:#F57F17">' + subjCount + '</div><div style="font-size:0.75rem;color:var(--text2)">Subjective</div></div>';
          if (exCount) h += '<div class="card" style="flex:1;min-width:120px;text-align:center;padding:16px"><div style="font-size:1.5rem;font-weight:800;color:#7E57C2">' + exCount + '</div><div style="font-size:0.75rem;color:var(--text2)">Examples</div></div>';
          h += '</div>';
          h += '<p style="font-size:0.82rem;color:var(--text2);margin:8px 0">Content inherited from NCERT mode. Competitive questions from Exercises 1-4 will be added in next draft.</p>';
        }
      } else {
        h += '<div class="card"><div class="card-body" style="text-align:center;padding:32px"><p style="color:var(--text3)">NCERT content mapping pending verification</p></div></div>';
      }
    } else {
      // Competitive-only subconcept
      h += '<div style="display:flex;gap:6px;margin-bottom:16px">';
      h += '<span class="label" style="background:#EDE7F6;color:#5E35B1">Competitive Only</span>';
      h += '<span class="label" style="background:#FFF3E8;color:var(--accent)">Beyond NCERT</span>';
      h += '</div>';
      h += '<div class="card"><div class="card-body" style="text-align:center;padding:40px 20px">';
      h += '<div style="font-size:2rem;margin-bottom:12px">&#128218;</div>';
      h += '<h3 style="color:var(--navy);margin-bottom:8px">Advanced Topic</h3>';
      h += '<p style="color:var(--text2);font-size:0.88rem;max-width:400px;margin:0 auto">This topic extends beyond NCERT syllabus for competitive exam preparation (NTSE/KVPY/JEE Foundation).</p>';
      h += '<p style="color:var(--text3);font-size:0.78rem;margin-top:16px">Theory, questions, and examples — to be processed in next draft</p>';
      h += '</div></div>';
    }

    v.innerHTML = h;
    if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([v]);
    document.getElementById('sidebar').classList.remove('mobile-open');
    document.getElementById('mobileOverlay').classList.remove('visible');
  },
};

document.addEventListener('DOMContentLoaded', () => app.init());
</script>
</body>
</html>'''

out_path = os.path.join(BASE, 'review/index.html')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Interactive Review HTML built: {os.path.getsize(out_path) // 1024}KB")
print(f"Content: {total_scq} SCQs, {total_subj} Subjective, {total_ex} Examples")
print(f"Features: option cards, submit/reset, numeric input, text area, score tracker, sidebar toggle, mobile responsive")
