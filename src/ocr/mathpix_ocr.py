"""
MathPix OCR — PDF -> MMD conversion for the pipeline.
Forked from: D:\\ACADZA_WORK\\Question Uploading App\\app\\pipeline\\stage1_mathpix.py

Two invocation modes:

  (A) Chapter-driven (preferred for the pipeline):
      python src/ocr/mathpix_ocr.py run --chapter ch12_magnetic_ncert
      python src/ocr/mathpix_ocr.py run --chapter ch12_magnetic_ncert --dry-run

      All paths resolved from src.common.chapter_config. Cost gated via cost_gate.

  (B) Manual one-off (backward compat, retained for ad-hoc use):
      python src/ocr/mathpix_ocr.py upload "path/to/file.pdf" --label my_label [--pages 1-76]
      python src/ocr/mathpix_ocr.py status --label my_label
      python src/ocr/mathpix_ocr.py download --label my_label
"""
import argparse
import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests

# Make src.common importable when run as a script
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.common import chapter_config
from src.common.cost_gate import CostEstimate, confirm_spend, log_spend
from src.common.stage_validators import validate_mmd

# MathPix API
MATHPIX_UPLOAD_URL = "https://api.mathpix.com/v3/pdf"
MATHPIX_STATUS_URL = "https://api.mathpix.com/v3/pdf/{pdf_id}"
MATHPIX_DOWNLOAD_URL = "https://api.mathpix.com/v3/pdf/{pdf_id}.mmd.zip"

MATHPIX_OPTIONS = {
    "conversion_formats": {"docx": False, "tex.zip": False},
    "rm_spaces": True,
    "math_inline_delimiters": ["$", "$"],
    "math_display_delimiters": ["$$", "$$"],
}

# Empirical cost from Ch1 Light (76 pages cost Rs 50)
INR_PER_PAGE = 50.0 / 76.0  # ~Rs 0.66/page

APP_ID = os.environ.get('MATHPIX_APP_ID', 'acadzatechnologies_344ef3_d65d3b')
APP_KEY = os.environ.get('MATHPIX_APP_KEY', '516aa36646afa35df5899c4059dec9d2bf90d18aa92c4b9595ee4e3959936e14')


# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------
def _safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


def _page_count(pdf_path: Path) -> int:
    """Count pages in a PDF without needing fitz at import time."""
    import fitz
    doc = fitz.open(str(pdf_path))
    try:
        return doc.page_count
    finally:
        doc.close()


def _resolve_label_paths(label: str) -> tuple[Path, Path]:
    """Return (output_dir, status_path) for a given label."""
    out = PROJECT_ROOT / 'experiments' / '01_ocr_benchmarks' / 'mathpix' / label
    out.mkdir(parents=True, exist_ok=True)
    return out, out / 'mathpix_status.json'


def _load_status(label: str) -> dict:
    _, status_path = _resolve_label_paths(label)
    if status_path.exists():
        return json.loads(status_path.read_text(encoding='utf-8'))
    return {}


def _save_status(label: str, status: dict) -> None:
    _, status_path = _resolve_label_paths(label)
    status_path.write_text(json.dumps(status, indent=2), encoding='utf-8')


# ---------------------------------------------------------------------
# core api wrappers (do not gate cost - the caller does)
# ---------------------------------------------------------------------
def _api_upload(pdf_path: Path, label: str, page_ranges: str | None = None) -> str | None:
    """POST the PDF to MathPix. Returns pdf_id or None on failure."""
    headers = {'app_id': APP_ID, 'app_key': APP_KEY}
    options = dict(MATHPIX_OPTIONS)
    if page_ranges:
        options['page_ranges'] = page_ranges
        _safe_print(f"  page_ranges: {page_ranges}")

    _safe_print(f"  uploading {pdf_path.name} ({pdf_path.stat().st_size / 1024 / 1024:.1f} MB)...")
    with pdf_path.open('rb') as f:
        files = {'file': (pdf_path.name, f, 'application/pdf')}
        data = {'options_json': json.dumps(options)}
        resp = requests.post(MATHPIX_UPLOAD_URL, headers=headers, files=files, data=data, timeout=600)

    if resp.status_code != 200:
        _safe_print(f"  ERROR HTTP {resp.status_code}: {resp.text[:300]}")
        return None
    pdf_id = resp.json().get('pdf_id')
    if not pdf_id:
        _safe_print(f"  ERROR no pdf_id in response: {resp.text[:200]}")
        return None
    _safe_print(f"  pdf_id: {pdf_id}")
    return pdf_id


def _api_poll(pdf_id: str, interval: int = 15) -> bool:
    """Poll until completed or errored. Returns True on completion."""
    headers = {'app_id': APP_ID, 'app_key': APP_KEY}
    url = MATHPIX_STATUS_URL.format(pdf_id=pdf_id)
    while True:
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.status_code != 200:
            _safe_print(f"  ERROR polling HTTP {resp.status_code}: {resp.text[:200]}")
            return False
        data = resp.json()
        st = data.get('status', 'unknown')
        pct = data.get('percent_done', 0)
        pages = data.get('num_pages_completed', 0)
        total = data.get('num_pages', 0)
        _safe_print(f"  [{time.strftime('%H:%M:%S')}] {st} - {pct}% ({pages}/{total} pages)")
        if st == 'completed':
            return True
        if st == 'error':
            _safe_print(f"  ERROR mathpix processing failed: {data}")
            return False
        time.sleep(interval)


def _api_download_and_extract(pdf_id: str, out_dir: Path, label: str) -> Path | None:
    """Download zip, extract, copy MMD to out_dir/<label>.mmd. Returns mmd path."""
    headers = {'app_id': APP_ID, 'app_key': APP_KEY}
    url = MATHPIX_DOWNLOAD_URL.format(pdf_id=pdf_id)
    zip_path = out_dir / f'{pdf_id}.mmd.zip'

    _safe_print(f"  downloading...")
    resp = requests.get(url, headers=headers, stream=True, timeout=600)
    if resp.status_code != 200:
        _safe_print(f"  ERROR HTTP {resp.status_code}: {resp.text[:200]}")
        return None
    with zip_path.open('wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    _safe_print(f"  zip: {zip_path.name} ({zip_path.stat().st_size / 1024:.0f} KB)")

    extract_dir = out_dir / 'mmd_extracted'
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(zip_path), 'r') as zf:
        zf.extractall(str(extract_dir))

    mmd_path = next(extract_dir.rglob('*.mmd'), None)
    if not mmd_path:
        _safe_print("  ERROR no .mmd file inside zip")
        return None

    top_mmd = out_dir / f'{label}.mmd'
    shutil.copy2(mmd_path, top_mmd)
    return top_mmd


# ---------------------------------------------------------------------
# CHAPTER-DRIVEN RUN (preferred entrypoint)
# ---------------------------------------------------------------------
def run_for_chapter(chapter_key: str, dry_run: bool = False, yes: bool = False, poll_interval: int = 15) -> int:
    """
    End-to-end OCR for one chapter:
      resolve config -> cost gate -> upload -> poll -> download -> validate -> log.

    Returns 0 on success, non-zero on failure.
    """
    cfg = chapter_config.load(chapter_key)

    _safe_print("")
    _safe_print(f"=== MathPix OCR for {chapter_key} ===")
    _safe_print(f"  source PDF : {cfg.source_pdf}")
    _safe_print(f"  output MMD : {cfg.mmd_path}")
    _safe_print(f"  label      : {cfg.source_slug}")

    if not cfg.source_pdf.exists():
        _safe_print(f"FATAL: source PDF missing: {cfg.source_pdf}")
        return 2

    pages = _page_count(cfg.source_pdf)
    est_inr = round(pages * INR_PER_PAGE, 2)
    _safe_print(f"  page count : {pages}")

    est = CostEstimate(
        stage='ocr_mathpix',
        chapter_key=chapter_key,
        item_count=pages,
        inr_estimate=est_inr,
        model='mathpix-pdf-api',
        notes=f"OCR {pages} pages of {cfg.source_pdf.name}",
    )

    proceed = confirm_spend(est, yes=yes, dry_run=dry_run)
    if dry_run:
        _safe_print("\n[dry-run] paths resolved, cost gated. No API call made.")
        return 0
    if not proceed:
        _safe_print("\nAborted by user gate.")
        return 1

    # already-uploaded short-circuit
    label = cfg.source_slug
    status = _load_status(label)
    pdf_id = status.get('pdf_id')
    if pdf_id and status.get('status') == 'completed' and cfg.mmd_path.exists():
        _safe_print(f"  MMD already exists at {cfg.mmd_path} - skipping API call")
        log_spend(est, actual_inr=0.0, status='skipped_existing')
        return 0

    # upload (if not already uploaded)
    if not pdf_id:
        out_dir, _ = _resolve_label_paths(label)
        page_ranges = None
        if cfg.foundation_page_range:
            page_ranges = f"{cfg.foundation_page_range[0]}-{cfg.foundation_page_range[1]}"

        pdf_id = _api_upload(cfg.source_pdf, label, page_ranges)
        if not pdf_id:
            log_spend(est, actual_inr=0.0, status='upload_failed')
            return 3
        status = {
            'pdf_id': pdf_id,
            'status': 'uploaded',
            'input_file': cfg.source_pdf.name,
            'page_ranges': page_ranges,
        }
        _save_status(label, status)

    # poll
    _safe_print(f"  polling every {poll_interval}s...")
    completed = _api_poll(pdf_id, interval=poll_interval)
    if not completed:
        log_spend(est, actual_inr=0.0, status='poll_failed')
        return 4

    # download + extract
    out_dir, _ = _resolve_label_paths(label)
    mmd_path = _api_download_and_extract(pdf_id, out_dir, label)
    if not mmd_path:
        log_spend(est, actual_inr=0.0, status='download_failed')
        return 5

    # update status
    images = list((out_dir / 'mmd_extracted').rglob('*.jpg')) + list((out_dir / 'mmd_extracted').rglob('*.png'))
    mmd_lines = mmd_path.read_text(encoding='utf-8', errors='replace').count('\n')
    status['status'] = 'completed'
    status['mmd_path'] = str(mmd_path)
    status['mmd_lines'] = mmd_lines
    status['images_count'] = len(images)
    _save_status(label, status)

    _safe_print(f"\n  OCR complete:")
    _safe_print(f"    MMD: {mmd_path} ({mmd_lines} lines)")
    _safe_print(f"    images: {len(images)}")

    # validate
    _safe_print("\n  running stage validator...")
    vr = validate_mmd(mmd_path)
    _safe_print("  " + vr.report().replace("\n", "\n  "))
    if not vr.ok:
        log_spend(est, actual_inr=est_inr, status='validator_failed', error="; ".join(vr.errors))
        return 6

    log_spend(est, actual_inr=est_inr, status='ok')
    _safe_print(f"\n  cost logged: Rs {est_inr:.2f}")
    return 0


# ---------------------------------------------------------------------
# Legacy actions (backward compat for ad-hoc use)
# ---------------------------------------------------------------------
def legacy_upload(pdf_path_str: str, label: str, page_ranges: str | None = None) -> None:
    pdf = Path(pdf_path_str)
    if not pdf.exists():
        _safe_print(f"ERROR: PDF not found: {pdf}")
        return
    status = _load_status(label)
    if status.get('pdf_id'):
        _safe_print(f"Already uploaded - pdf_id: {status['pdf_id']}")
        return
    pdf_id = _api_upload(pdf, label, page_ranges)
    if pdf_id:
        _save_status(label, {
            'pdf_id': pdf_id, 'status': 'uploaded',
            'input_file': pdf.name, 'page_ranges': page_ranges,
        })


def legacy_status(label: str) -> None:
    status = _load_status(label)
    pdf_id = status.get('pdf_id')
    if not pdf_id:
        _safe_print("No upload found.")
        return
    headers = {'app_id': APP_ID, 'app_key': APP_KEY}
    url = MATHPIX_STATUS_URL.format(pdf_id=pdf_id)
    resp = requests.get(url, headers=headers, timeout=60)
    if resp.status_code == 200:
        data = resp.json()
        _safe_print(f"Status: {data.get('status')}, {data.get('percent_done')}%")
    else:
        _safe_print(f"ERROR HTTP {resp.status_code}: {resp.text[:200]}")


def legacy_download(label: str) -> None:
    status = _load_status(label)
    pdf_id = status.get('pdf_id')
    if not pdf_id:
        _safe_print("No upload found.")
        return
    out_dir, _ = _resolve_label_paths(label)
    mmd_path = _api_download_and_extract(pdf_id, out_dir, label)
    if mmd_path:
        _safe_print(f"MMD: {mmd_path}")


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='MathPix OCR for the pipeline')
    parser.add_argument('action', choices=['run', 'upload', 'status', 'download'],
                        help='run = chapter-driven full flow; others = legacy ad-hoc actions')
    parser.add_argument('--chapter', help='Chapter key from chapter_config registry (for action=run)')
    parser.add_argument('pdf', nargs='?', help='PDF path (for legacy upload action)')
    parser.add_argument('--label', help='Output folder label (for legacy actions)')
    parser.add_argument('--pages', help='Page range e.g. "1-76" (for legacy upload)')
    parser.add_argument('--dry-run', action='store_true', help='Skip API call, just print resolved paths + cost')
    parser.add_argument('--yes', action='store_true', help='Auto-confirm cost gate (use with care)')
    parser.add_argument('--interval', type=int, default=15, help='Poll interval seconds')
    args = parser.parse_args()

    if args.action == 'run':
        if not args.chapter:
            _safe_print("ERROR: 'run' requires --chapter <key>")
            _safe_print(f"Known: {', '.join(chapter_config.list_keys())}")
            sys.exit(1)
        sys.exit(run_for_chapter(args.chapter, dry_run=args.dry_run, yes=args.yes, poll_interval=args.interval))

    if args.action == 'upload':
        if not args.pdf or not args.label:
            _safe_print("ERROR: legacy upload needs pdf path + --label")
            sys.exit(1)
        legacy_upload(args.pdf, args.label, args.pages)
    elif args.action == 'status':
        if not args.label:
            _safe_print("ERROR: --label required"); sys.exit(1)
        legacy_status(args.label)
    elif args.action == 'download':
        if not args.label:
            _safe_print("ERROR: --label required"); sys.exit(1)
        legacy_download(args.label)
