"""
Build the complete self-contained review HTML.
Fixes: MathJax rendering, actual images, font, sidebar toggle, formatting.
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

# Build image map: IMG_CODE -> base64 data URI from LOCAL files
image_urls = {}
img_dir = os.path.join(BASE, 'experiments/01_ocr_benchmarks/mathpix/ch09_light/mmd_extracted/images')
for code, info in img_codes.items():
    local = info.get('local_file', '')
    if local and os.path.exists(local):
        with open(local, 'rb') as imgf:
            b64 = base64.b64encode(imgf.read()).decode('ascii')
        image_urls[code] = f'data:image/jpeg;base64,{b64}'

# Also add generated images (GEN_* codes)
gen_img_dir2 = os.path.join(BASE, 'experiments/05_content_generation/ch09_generated_images')
if os.path.exists(gen_img_dir2):
    for fname in os.listdir(gen_img_dir2):
        if fname.endswith('.png'):
            key = f"GEN_{fname.replace('.png','')}"
            with open(os.path.join(gen_img_dir2, fname), 'rb') as imgf:
                b64 = base64.b64encode(imgf.read()).decode('ascii')
            image_urls[key] = f'data:image/png;base64,{b64}'

# Encode generated images as base64
gen_img_dir = os.path.join(BASE, 'experiments/05_content_generation/ch09_generated_images')
gen_images = {}
if os.path.exists(gen_img_dir):
    for fname in os.listdir(gen_img_dir):
        if fname.endswith('.png'):
            with open(os.path.join(gen_img_dir, fname), 'rb') as f:
                gen_images[fname.replace('.png', '')] = f"data:image/png;base64,{base64.b64encode(f.read()).decode('ascii')}"

# Encode Acadza logo
with open('D:/ACADZA_WORK/acadza-pdf-generator/partners/acadza/logo.png', 'rb') as f:
    logo_b64 = base64.b64encode(f.read()).decode('ascii')

# Gear SVG
with open('D:/ACADZA_WORK/acadza-pdf-generator/partners/acadza/watermark.svg', 'r') as f:
    gear_svg = f.read()
gear_b64 = base64.b64encode(gear_svg.encode('utf-8')).decode('ascii')

# Build the HTML
content_js = json.dumps(content, ensure_ascii=False)
schema_js = json.dumps(schema, ensure_ascii=False)
image_urls_js = json.dumps(image_urls, ensure_ascii=False)
gen_images_js = json.dumps(gen_images, ensure_ascii=False)

html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Acadza Content Review — Light: Reflection and Refraction</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet"/>
  <script>
    window.MathJax = {{
      tex: {{ inlineMath: [['\\\\(','\\\\)']], displayMath: [['\\\\[','\\\\]']] }},
      startup: {{ typeset: false }}
    }};
  </script>
  <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" async></script>
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          fontFamily: {{ sans: ['"Inter"', 'sans-serif'] }},
          colors: {{
            acadza: {{ light: '#ffb347', DEFAULT: '#ff8008', dark: '#cc6600' }},
            navy: '#1B2A4A',
          }},
        }},
      }},
    }}
  </script>
  <style>
    body {{ font-family: 'Inter', sans-serif; font-size: 16px; font-weight: 400; -webkit-font-smoothing: antialiased; }}
    summary::-webkit-details-marker{{display:none}}
    summary::marker{{content:""}}
    .theory-content p{{margin-bottom:0.9rem;line-height:1.85;font-size:1.05rem;color:#1f2937;font-weight:420}}
    .theory-content ul,.theory-content ol{{margin-left:1.5rem;margin-bottom:0.9rem}}
    .theory-content li{{margin-bottom:0.35rem;line-height:1.8;font-size:1.05rem;font-weight:420}}
    .theory-content strong{{color:#1B2A4A;font-weight:700}}
    .q-text{{line-height:1.8;font-size:1.05rem;color:#1f2937;font-weight:450}}
    .sol-text{{line-height:1.75;font-size:1rem;color:#374151;font-weight:420}}
    @keyframes fadeIn{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:translateY(0)}}}}
    .fade-in{{animation:fadeIn 0.3s ease-out}}
    .sidebar-item:hover{{background:rgba(255,128,8,0.06)}}
    .sidebar-active{{background:rgba(255,128,8,0.12);border-left:3px solid #ff8008}}
    .content-img{{max-width:100%;height:auto;max-height:280px;border-radius:8px;border:1px solid #e5e7eb;margin:0.5rem 0}}
    .content-img-caption{{font-size:0.75rem;color:#9CA3AF;font-style:italic;margin-top:2px}}
    /* Mobile */
    @media(max-width:768px){{
      #sidebar{{width:100%!important;position:fixed;z-index:25;transform:translateX(-100%)}}
      #sidebar.mobile-open{{transform:translateX(0)!important}}
      #content-area{{margin-left:0!important;padding:1rem 0.75rem!important;padding-top:0.5rem!important}}
      .max-w-3xl{{max-width:100%}}
      .content-img{{max-height:200px}}
      header .flex{{flex-wrap:wrap;gap:0.3rem}}
      header .text-xs{{font-size:0.6rem}}
      #main-container{{padding-top:100px!important}}
    }}
  </style>
</head>
<body class="bg-gray-50 min-h-screen">

<header class="fixed top-0 inset-x-0 z-30 bg-white shadow-sm border-b border-gray-200">
  <div class="flex items-center justify-between px-5 py-3">
    <div class="flex items-center gap-3">
      <button onclick="app.toggleSidebar()" class="p-1.5 rounded-lg hover:bg-gray-100 transition" title="Toggle sidebar">
        <svg id="toggle-icon" class="w-5 h-5 text-gray-500 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/>
        </svg>
      </button>
      <img src="data:image/png;base64,{logo_b64}" alt="Acadza" class="h-9"/>
      <div class="flex items-baseline gap-3">
        <h1 class="text-xl font-bold text-navy">Content Review</h1>
        <span class="text-sm text-gray-400">|</span>
        <span class="text-sm text-gray-500">Chapter: Light — Reflection and Refraction</span>
      </div>
    </div>
    <div class="flex items-center gap-3 text-xs text-gray-500">
      <span class="px-2 py-1 bg-gray-50 text-gray-700 rounded font-medium">3 Concepts</span>
      <span class="px-2 py-1 bg-green-50 text-green-700 rounded font-medium">14 Subconcepts</span>
      <span class="px-2 py-1 bg-blue-50 text-blue-700 rounded font-medium">27 SCQs</span>
      <span class="px-2 py-1 bg-amber-50 text-amber-700 rounded font-medium">67 Subjective</span>
      <span class="px-2 py-1 bg-violet-50 text-violet-700 rounded font-medium">34 Examples</span>
    </div>
  </div>
  <div class="h-0.5 w-full bg-gradient-to-r from-acadza-light via-acadza to-acadza-dark"></div>
</header>

<div id="main-container" class="flex min-h-screen" style="padding-top:65px">
  <aside id="sidebar" class="w-80 bg-white border-r border-gray-200 fixed top-[60px] bottom-0 overflow-y-auto z-20 transition-all duration-300">
    <div class="p-4 border-b border-gray-100">
      <h2 class="text-xs font-semibold text-gray-400 uppercase tracking-wider">Content Index</h2>
    </div>
    <nav id="nav-tree" class="p-2"></nav>
  </aside>

  <main id="content-area" class="transition-all duration-300 flex-1 p-8" style="margin-left:320px">
    <div class="max-w-3xl mx-auto">
      <div id="welcome" class="text-center py-20">
        <img src="data:image/svg+xml;base64,{gear_b64}" alt="Acadza" class="w-16 h-16 mx-auto mb-4"/>
        <h2 class="text-2xl font-bold text-navy mb-2">Select a subconcept <span class="text-lg">📖</span></h2>
        <div class="mt-8 grid grid-cols-3 gap-4 max-w-md mx-auto text-sm">
          <div class="p-3 bg-blue-50 rounded-lg"><span class="text-2xl font-bold text-blue-600">27</span><br/><span class="text-gray-500">SCQs</span></div>
          <div class="p-3 bg-green-50 rounded-lg"><span class="text-2xl font-bold text-green-600">67</span><br/><span class="text-gray-500">Subjective</span></div>
          <div class="p-3 bg-purple-50 rounded-lg"><span class="text-2xl font-bold text-purple-600">34</span><br/><span class="text-gray-500">Examples</span></div>
        </div>
      </div>
      <div id="subconcept-view" class="hidden fade-in"></div>
    </div>
  </main>
</div>

<script>
const CONTENT_DATA = {content_js};
const SCHEMA_DATA = {schema_js};
const IMAGE_URLS = {image_urls_js};
const GEN_IMAGES = {gen_images_js};
</script>
<script>
const app = {{
  sidebarOpen: true,

  init() {{ this.buildNav(); }},

  toggleSidebar() {{
    this.sidebarOpen = !this.sidebarOpen;
    const sidebar = document.getElementById('sidebar');
    const content = document.getElementById('content-area');
    const icon = document.getElementById('toggle-icon');
    const mobile = window.innerWidth <= 768;
    if (this.sidebarOpen) {{
      if (mobile) {{
        sidebar.classList.add('mobile-open');
      }} else {{
        sidebar.style.transform = 'translateX(0)';
        content.style.marginLeft = '320px';
      }}
      icon.style.transform = 'rotate(0deg)';
    }} else {{
      if (mobile) {{
        sidebar.classList.remove('mobile-open');
      }} else {{
        sidebar.style.transform = 'translateX(-100%)';
        content.style.marginLeft = '0';
      }}
      icon.style.transform = 'rotate(180deg)';
    }}
  }},

  buildNav() {{
    const nav = document.getElementById('nav-tree');
    const chapter = Object.keys(SCHEMA_DATA)[0];
    const concepts = SCHEMA_DATA[chapter];
    let html = '';
    for (const [conceptName, subs] of Object.entries(concepts)) {{
      const conceptKey = `Concept: ${{conceptName}}`;
      html += `<details class="mb-1" open>
        <summary class="flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer hover:bg-gray-50 text-sm font-semibold text-navy">
          <svg class="w-4 h-4 text-acadza transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
          ${{conceptName}}
        </summary><div class="ml-2">`;
      for (const sub of subs) {{
        const subKey = `Subconcept: ${{sub}}`;
        const data = CONTENT_DATA[conceptKey]?.[subKey];
        const n = data ? (Object.keys(data.SCQs||{{}}).length + Object.keys(data.SubjectiveTypes||{{}}).length + Object.keys(data.Examples||{{}}).length) : 0;
        html += `<div class="sidebar-item flex items-center justify-between px-3 py-2 ml-4 rounded cursor-pointer text-sm text-gray-700"
                      onclick="app.selectSub('${{conceptKey}}','${{subKey}}',this)">
          <span class="truncate pr-2">${{sub}}</span><span class="text-xs text-gray-400">${{n}}</span></div>`;
      }}
      html += '</div></details>';
    }}
    nav.innerHTML = html;
  }},

  selectSub(ck, sk, el) {{
    document.querySelectorAll('.sidebar-item').forEach(e => e.classList.remove('sidebar-active'));
    if (el) el.classList.add('sidebar-active');
    const data = CONTENT_DATA[ck]?.[sk];
    if (!data) return;
    document.getElementById('welcome').classList.add('hidden');
    const view = document.getElementById('subconcept-view');
    view.classList.remove('hidden');
    view.innerHTML = this.renderSub(sk.replace('Subconcept: ',''), data);
    if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([view]);
    window.scrollTo(0, 0);
    // Auto-close sidebar on mobile after selection
    if (window.innerWidth <= 768 && this.sidebarOpen) {{
      this.toggleSidebar();
    }}
    // Scroll to top of content on mobile
    setTimeout(() => {{
      document.getElementById('content-area').scrollTo(0, 0);
      window.scrollTo(0, 0);
    }}, 100);
  }},

  badge(text, subtle) {{
    const c = {{
      Easy:'bg-green-50 text-green-600 border-green-200', Medium:'bg-amber-50 text-amber-600 border-amber-200',
      Hard:'bg-red-50 text-red-600 border-red-200', Generated:'bg-blue-50 text-blue-600 border-blue-200',
      'Source':'bg-gray-100 text-gray-600 border-gray-300',
      'Back Exercise':'bg-purple-50 text-purple-600 border-purple-200', 'In-text':'bg-teal-50 text-teal-600 border-teal-200',
      'NCERT':'bg-orange-50 text-orange-600 border-orange-200',
      standard:'bg-gray-50 text-gray-500 border-gray-200', assertion_reason:'bg-indigo-50 text-indigo-500 border-indigo-200',
      statement_selection:'bg-cyan-50 text-cyan-500 border-cyan-200',
      descriptive:'bg-gray-50 text-gray-500 border-gray-200', numerical:'bg-rose-50 text-rose-500 border-rose-200',
      diagram:'bg-violet-50 text-violet-500 border-violet-200',
    }};
    return `<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium border ${{c[text]||'bg-gray-50 text-gray-500 border-gray-200'}}">${{text}}</span>`;
  }},

  sourceLabel(q) {{
    if (q._source === 'generated') return 'Generated';
    if (q._source === 'back_exercise') return 'Source';
    if (q._source === 'in_text') return 'Source';
    if (q._source === 'ncert') return 'NCERT';
    if (q.isBackExercise) return 'Source';
    if (q.isInTextQuestion) return 'Source';
    return 'Generated';
  }},

  sourceSubLabel(q) {{
    if (q.isBackExercise) return 'Back Exercise';
    if (q.isInTextQuestion) return 'In-text';
    if (q._source === 'ncert' || q.isFromNCERT) return 'NCERT';
    return '';
  }},

  renderImage(vc) {{
    if (!vc || (!vc.needed && !vc.Needed)) return '';
    const ref = vc.source_image_ref;
    const desc = vc.image_description || '';
    if (ref && IMAGE_URLS[ref]) {{
      return `<div class="my-3"><img src="${{IMAGE_URLS[ref]}}" alt="${{desc}}" class="content-img"/>${{desc ? `<p class="content-img-caption">${{desc}}</p>` : ''}}</div>`;
    }}
    if (vc.image_generation_needed && vc.generation_description) {{
      return `<p class="text-xs text-gray-400 italic my-2">[Diagram: ${{vc.generation_description.substring(0,100)}}...]</p>`;
    }}
    return '';
  }},

  fmt(text) {{
    if (!text) return '';
    let h = text.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
    // Bold Assertion (A): and Reason (R):
    h = h.replace(/Assertion \\(A\\):/g, '<strong>Assertion (A):</strong>');
    h = h.replace(/Reason \\(R\\):/g, '<strong>Reason (R):</strong>');
    h = h.replace(/\\n/g, '<br/>');
    return h;
  }},

  renderSub(name, data) {{
    const scqs = Object.entries(data.SCQs || {{}});
    const subjs = Object.entries(data.SubjectiveTypes || {{}});
    const exs = Object.entries(data.Examples || {{}});
    // Compute stats
    const srcQ = [...scqs,...subjs].filter(([k,q])=>q._source!=='generated').length;
    const genQ = [...scqs,...subjs].filter(([k,q])=>q._source==='generated').length;
    const srcE = exs.filter(([k,e])=>e._source==='ncert').length;
    const genE = exs.filter(([k,e])=>e._source!=='ncert').length;
    const srcSCQ = scqs.filter(([k,q])=>q._source!=='generated').length;
    const genSCQ = scqs.filter(([k,q])=>q._source==='generated').length;
    const srcSubj = subjs.filter(([k,q])=>q._source!=='generated').length;
    const genSubj = subjs.filter(([k,q])=>q._source==='generated').length;

    let h = `<div class="mb-6"><h2 class="text-2xl font-bold text-navy">${{name}}</h2>
      <div class="mt-3 text-sm text-gray-500 space-y-1">
        <div><strong class="text-gray-700">${{scqs.length+subjs.length}} Questions</strong> (${{srcQ}} source + ${{genQ}} generated) &bull; <strong class="text-gray-700">${{exs.length}} Examples</strong> (${{srcE}} NCERT + ${{genE}} generated)</div>
        <div class="text-xs text-gray-400">SCQs: ${{scqs.length}} (${{srcSCQ}} source + ${{genSCQ}} generated) &bull; Subjective: ${{subjs.length}} (${{srcSubj}} source + ${{genSubj}} generated)</div>
      </div></div>`;

    // Theory
    if (data.Summary?.Theory) {{
      h += `<div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
        <h3 class="text-lg font-bold text-navy mb-4">Theory</h3>
        <div class="theory-content text-gray-700">${{this.fmt(data.Summary.Theory)}}</div>
        ${{this.renderImage(data.Summary.VisualContent)}}</div>`;
    }}

    // SCQs
    if (scqs.length) {{
      h += `<h3 class="text-lg font-bold text-navy mb-3 mt-6">Single Choice Questions (${{scqs.length}})</h3>`;
      for (const [key, q] of scqs) {{
        const src = this.sourceLabel(q);
        const subSrc = this.sourceSubLabel(q);
        h += `<div class="bg-white rounded-xl shadow-sm border border-gray-100 mb-3 p-5">
          <div class="flex gap-1 flex-wrap mb-3">
            ${{this.badge(src)}} ${{subSrc?this.badge(subSrc):''}} ${{this.badge(q.Difficulty)}} ${{q.scq_format?this.badge(q.scq_format):''}}
          </div>
          <div class="q-text mb-2">${{this.fmt(q.Question||'')}}</div>
          <details class="group mt-3">
            <summary class="text-sm text-green-600 cursor-pointer font-semibold hover:text-green-800 flex items-center gap-1">
              Show Solution
              <svg class="w-4 h-4 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
            </summary>
            <div class="mt-3 border-t border-gray-100 pt-3">
              ${{q.Answer?`<p class="text-sm mb-2 font-medium"><span class="text-green-600">Answer:</span> ${{q.Answer}}</p>`:''}}
              ${{this.renderImage(q.VisualContent)}}
              ${{q.Solution?`<div class="sol-text bg-gray-50 rounded-lg p-4 mt-2">${{this.fmt(q.Solution)}}</div>`:''}}
            </div>
          </details>
        </div>`;
      }}
    }}

    // Subjective
    if (subjs.length) {{
      h += `<h3 class="text-lg font-bold text-navy mb-3 mt-6">Subjective Questions (${{subjs.length}})</h3>`;
      for (const [key, q] of subjs) {{
        const src = this.sourceLabel(q);
        const subSrc = this.sourceSubLabel(q);
        h += `<div class="bg-white rounded-xl shadow-sm border border-gray-100 mb-3 p-5">
          <div class="flex gap-1 flex-wrap mb-3">
            ${{this.badge(src)}} ${{subSrc?this.badge(subSrc):''}} ${{this.badge(q.Difficulty)}} ${{q.answer_format?this.badge(q.answer_format):''}}
          </div>
          <div class="q-text mb-2">${{this.fmt(q.Question||'')}}</div>
          <details class="group mt-3">
            <summary class="text-sm text-amber-600 cursor-pointer font-semibold hover:text-amber-800 flex items-center gap-1">
              Show Solution
              <svg class="w-4 h-4 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
            </summary>
            <div class="mt-3 border-t border-gray-100 pt-3">
              ${{q.Answer?`<p class="text-sm mb-2 font-medium"><span class="text-amber-600">Answer:</span> ${{this.fmt(q.Answer)}}</p>`:''}}
              ${{this.renderImage(q.VisualContent)}}
              ${{q.Solution?`<div class="sol-text bg-gray-50 rounded-lg p-4 mt-2 whitespace-pre-line">${{this.fmt(q.Solution)}}</div>`:''}}
            </div>
          </details>
        </div>`;
      }}
    }}

    // Examples
    if (exs.length) {{
      h += `<h3 class="text-base font-semibold text-navy mb-3 mt-6">Solved Examples (${{exs.length}})</h3>`;
      for (const [key, ex] of exs) {{
        const src = this.sourceLabel(ex);
        h += `<div class="bg-white rounded-xl shadow-sm border border-gray-100 mb-3 p-5">
          <div class="flex gap-1 flex-wrap mb-3">
            ${{this.badge(src)}} ${{this.badge(ex.Difficulty||'Medium')}}
          </div>
          <div class="q-text mb-2">${{this.fmt(ex.Question||'')}}</div>
          ${{this.renderImage(ex.VisualContent)}}
          ${{ex.Solution?`<details class="group"><summary class="text-sm text-purple-600 cursor-pointer font-medium">Show Solution</summary>
            <div class="mt-3 sol-text text-gray-600 bg-purple-50 rounded-lg p-4 whitespace-pre-line">${{this.fmt(ex.Solution)}}</div></details>`
            :'<p class="text-xs text-gray-400 italic">Solution from NCERT textbook</p>'}}</div>`;
      }}
    }}
    return h;
  }},
}};
document.addEventListener('DOMContentLoaded', () => app.init());
</script>
</body>
</html>'''

out_path = os.path.join(BASE, 'review/index.html')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Review HTML built: {os.path.getsize(out_path) // 1024}KB")
print("Fixes:")
print("  1. Source Sans 3 font (clean, professional, highly readable)")
print("  2. MathJax config BEFORE script load (proper order)")
print("  3. Actual images rendered via <img> tags from MathPix CDN URLs")
print("  4. Sidebar toggle with arrow rotation + content stays centered")
print("  5. Badges right-aligned, subtle colors with borders")
print("  6. Assertion (A): and Reason (R): bolded automatically")
print("  7. Consistent font sizes: theory 1rem, questions 0.95rem, solutions 0.9rem")
print("  8. Source/Generated as primary label, sub-labels secondary")
print("  9. Image inline with content, no colored callout blocks")
