"""
backup.py - Timestamped snapshot helper invoked between pipeline stages.

Every pipeline stage that overwrites a previous stage's output MUST call
snapshot() on the output path before writing, so the prior version is preserved
under _backups/<stem>_<YYYYMMDD_HHMMSS>.<ext>. This guarantees we can revert
to any intermediate state if a downstream stage corrupts the file.

Usage:
    from src.common.backup import snapshot, safe_write_json

    # Manual snapshot before overwriting
    snapshot(cfg.topology_path)
    cfg.topology_path.write_text(json.dumps(new_topology), encoding="utf-8")

    # One-liner equivalent
    safe_write_json(cfg.topology_path, new_topology)
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def snapshot(output_path: Path) -> Path | None:
    """
    If output_path exists, copy it into a sibling _backups/ directory with a
    timestamp suffix. Returns the backup path, or None if the file didn't exist
    (first-time write, nothing to back up).

    Backup naming: <stem>_<YYYYMMDD_HHMMSS><suffix>
        topology.json -> _backups/topology_20260511_153045.json
    """
    output_path = Path(output_path)
    if not output_path.exists():
        return None

    backups_dir = output_path.parent / "_backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    stamp = _stamp()
    backup_path = backups_dir / f"{output_path.stem}_{stamp}{output_path.suffix}"
    # Same-second collision: append a counter so back-to-back snapshots both survive
    counter = 1
    while backup_path.exists():
        backup_path = backups_dir / f"{output_path.stem}_{stamp}_{counter}{output_path.suffix}"
        counter += 1
    shutil.copy2(output_path, backup_path)
    return backup_path


def safe_write_text(path: Path, content: str, encoding: str = "utf-8") -> Path | None:
    """Snapshot any existing file at path, then write new text content. Returns the backup path."""
    path = Path(path)
    bak = snapshot(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding)
    return bak


def safe_write_json(path: Path, data: Any, indent: int = 2, ensure_ascii: bool = False) -> Path | None:
    """Snapshot any existing file at path, then write data as JSON. Returns the backup path."""
    payload = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
    return safe_write_text(path, payload, encoding="utf-8")


def list_backups(output_path: Path) -> list[Path]:
    """List existing snapshots for a given output path, newest last."""
    output_path = Path(output_path)
    backups_dir = output_path.parent / "_backups"
    if not backups_dir.exists():
        return []
    stem = output_path.stem
    suffix = output_path.suffix
    matches = [
        p for p in backups_dir.iterdir()
        if p.is_file() and p.name.startswith(f"{stem}_") and p.suffix == suffix
    ]
    return sorted(matches)


if __name__ == "__main__":
    # Sanity check
    import sys, tempfile
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        target = td / "topology.json"

        # First write: no backup
        bak1 = safe_write_json(target, {"version": 1})
        print(f"First write backup: {bak1}")
        assert bak1 is None

        # Second write: backup of v1 created
        bak2 = safe_write_json(target, {"version": 2})
        print(f"Second write backup: {bak2}")
        assert bak2 is not None and bak2.exists()
        assert json.loads(bak2.read_text("utf-8")) == {"version": 1}

        # Third write: backup of v2 created
        bak3 = safe_write_json(target, {"version": 3})
        print(f"Third write backup: {bak3}")
        assert json.loads(bak3.read_text("utf-8")) == {"version": 2}

        # Listing
        all_bks = list_backups(target)
        print(f"Total backups: {len(all_bks)}")
        for b in all_bks:
            print(f"  {b.name}")
        assert len(all_bks) == 2

    print("\nbackup.py sanity check PASSED")
