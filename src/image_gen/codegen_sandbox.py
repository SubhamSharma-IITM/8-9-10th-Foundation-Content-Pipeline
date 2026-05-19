"""
codegen_sandbox.py - AST validator + sandboxed subprocess executor for LLM-generated
matplotlib code.

The Stage 10 LLM produces matplotlib code from a generation_description. Before we
run that code we MUST validate it doesn't do anything dangerous (file I/O outside
savefig, network, subprocess, eval, etc.) and that it'll terminate in bounded time.

Defense layers:
  1. AST walk - rejects forbidden imports, forbidden names, forbidden calls
  2. subprocess exec with timeout - even if AST misses something
  3. output validation - file exists, opens as PNG, non-trivial size
"""
from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ALLOWED_IMPORTS = {"matplotlib", "matplotlib.pyplot", "numpy", "math"}
FORBIDDEN_NAMES = {
    "eval", "exec", "compile", "open", "__import__", "globals", "locals",
    "input", "exit", "quit",
}
FORBIDDEN_MODULES = {
    "os", "sys", "subprocess", "socket", "urllib", "requests", "http",
    "pickle", "ctypes", "io", "pathlib", "shutil", "glob",
}
# Attributes that suggest filesystem / network access
FORBIDDEN_ATTRS = {"system", "popen", "spawn", "remove", "unlink", "rmtree", "mkdir"}

# Allowed savefig calls — the only file I/O permitted
ALLOWED_SAVE_ATTRS = {"savefig"}


@dataclass
class SandboxResult:
    ok: bool
    stage: str = ""             # "ast" | "exec" | "output"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    output_path: Path | None = None
    stdout: str = ""
    stderr: str = ""


def validate_ast(code: str) -> SandboxResult:
    """Parse and walk the AST. Reject anything not on the allow-list."""
    r = SandboxResult(ok=True, stage="ast")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        r.ok = False
        r.errors.append(f"SyntaxError: {e}")
        return r

    has_savefig = False
    for node in ast.walk(tree):
        # imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_MODULES:
                    r.errors.append(f"forbidden import: {alias.name}")
                elif alias.name not in ALLOWED_IMPORTS and root not in {"matplotlib", "numpy", "math"}:
                    r.errors.append(f"non-allowlisted import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            root = mod.split(".")[0]
            if root in FORBIDDEN_MODULES:
                r.errors.append(f"forbidden from-import: from {mod}")
            elif root not in {"matplotlib", "numpy", "math"}:
                r.errors.append(f"non-allowlisted from-import: from {mod}")

        # forbidden names anywhere
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            r.errors.append(f"forbidden name: {node.id}")

        # attribute access
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRS:
                r.errors.append(f"forbidden attribute: .{node.attr}")
            if node.attr in ALLOWED_SAVE_ATTRS:
                has_savefig = True

    if not has_savefig:
        r.warnings.append("no savefig call found - code may not produce a file")

    if r.errors:
        r.ok = False
    return r


_RUNNER_TEMPLATE = """
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# generated code expects this name available in scope
output_path = {OUTPUT_PATH!r}

# === BEGIN LLM-GENERATED CODE ===
{CODE}
# === END LLM-GENERATED CODE ===
# NOTE: no "safety net" savefig - if LLM code did not save, that is a real
# failure caught by validate_output_png(). A safety net would overwrite the
# real image with a blank figure after LLM's plt.close().
"""


def run_sandboxed(code: str, output_path: Path, timeout_sec: float = 5.0) -> SandboxResult:
    """Run validated code in a subprocess with a hard timeout.
    Caller MUST validate AST first; this method does NOT re-validate."""
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Remove any prior file so we can detect whether the code actually wrote one
    if output_path.exists():
        output_path.unlink()

    runner = _RUNNER_TEMPLATE.replace("{OUTPUT_PATH!r}", repr(str(output_path))).replace("{CODE}", code)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(runner)
        runner_path = Path(tf.name)

    r = SandboxResult(ok=True, stage="exec", output_path=output_path)
    try:
        proc = subprocess.run(
            [sys.executable, str(runner_path)],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            encoding="utf-8",
            errors="replace",
        )
        r.stdout = proc.stdout[:2000]
        r.stderr = proc.stderr[:2000]
        if proc.returncode != 0:
            r.ok = False
            r.errors.append(f"non-zero exit {proc.returncode}; stderr: {proc.stderr[:400]}")
    except subprocess.TimeoutExpired:
        r.ok = False
        r.errors.append(f"timeout after {timeout_sec}s - code did not finish")
    except Exception as e:
        r.ok = False
        r.errors.append(f"subprocess failure: {e}")
    finally:
        try:
            runner_path.unlink()
        except Exception:
            pass

    return r


def validate_output_png(p: Path, min_bytes: int = 1024, min_pixel_std: float = 5.0) -> SandboxResult:
    """Validate PNG output. Catches:
    - missing file
    - undersized file
    - missing PNG header
    - uniform/blank images (pixel std below threshold)
    """
    r = SandboxResult(ok=True, stage="output", output_path=p)
    if not p.exists():
        r.ok = False
        r.errors.append(f"output PNG missing: {p}")
        return r
    if p.stat().st_size < min_bytes:
        r.ok = False
        r.errors.append(f"output PNG too small: {p.stat().st_size} bytes (< {min_bytes})")
        return r
    head = p.read_bytes()[:8]
    if not head.startswith(b"\x89PNG\r\n\x1a\n"):
        r.ok = False
        r.errors.append("output file does not have PNG header")
        return r
    # Variance check — catches blank/uniform images that pass header check
    try:
        from PIL import Image
        import numpy as np
        arr = np.array(Image.open(p).convert("RGB"))
        std = float(arr.std())
        if std < min_pixel_std:
            r.ok = False
            r.errors.append(f"output PNG appears blank/uniform: pixel std={std:.2f} (< {min_pixel_std})")
    except ImportError:
        r.warnings.append("PIL/numpy not available - skipping blank-image check")
    except Exception as e:
        r.warnings.append(f"blank-check failed: {e}")
    return r


def codegen_and_render(
    code: str, output_path: Path, timeout_sec: float = 5.0
) -> tuple[bool, list[str]]:
    """Full pipeline: AST validate -> exec sandboxed -> validate PNG.
    Returns (success, list of errors)."""
    errors: list[str] = []
    ast_r = validate_ast(code)
    if not ast_r.ok:
        return False, [f"[ast] {e}" for e in ast_r.errors]
    if ast_r.warnings:
        errors.extend(f"[ast-warn] {w}" for w in ast_r.warnings)

    exec_r = run_sandboxed(code, output_path, timeout_sec=timeout_sec)
    if not exec_r.ok:
        errors.extend(f"[exec] {e}" for e in exec_r.errors)
        if exec_r.stderr:
            errors.append(f"[exec-stderr] {exec_r.stderr[:300]}")
        return False, errors

    out_r = validate_output_png(output_path)
    if not out_r.ok:
        errors.extend(f"[output] {e}" for e in out_r.errors)
        return False, errors

    return True, errors


if __name__ == "__main__":
    # Smoke tests
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=== TEST 1: valid matplotlib code ===")
    good = """
import matplotlib.pyplot as plt
import numpy as np

fig, ax = plt.subplots(figsize=(6, 4))
x = np.linspace(0, 10, 50)
ax.plot(x, np.sin(x), 'b-')
ax.set_title("Test plot")
plt.savefig(output_path, dpi=100, bbox_inches="tight")
plt.close()
"""
    ok, errs = codegen_and_render(good, Path("test_good.png"))
    print(f"  ok={ok}, errs={errs}")
    assert ok, "good code should succeed"
    Path("test_good.png").unlink(missing_ok=True)

    print("\n=== TEST 2: forbidden import (os) ===")
    bad1 = "import os\nos.system('echo hi')"
    ok, errs = codegen_and_render(bad1, Path("test_bad1.png"))
    print(f"  ok={ok}, errs={errs}")
    assert not ok

    print("\n=== TEST 3: eval / exec usage ===")
    bad2 = "import matplotlib.pyplot as plt\neval('1+1')\nplt.savefig(output_path)"
    ok, errs = codegen_and_render(bad2, Path("test_bad2.png"))
    print(f"  ok={ok}, errs={errs}")
    assert not ok

    print("\n=== TEST 4: subprocess via attribute ===")
    bad3 = "import matplotlib.pyplot as plt\nplt.gcf().system('rm -rf /')\nplt.savefig(output_path)"
    ok, errs = codegen_and_render(bad3, Path("test_bad3.png"))
    print(f"  ok={ok}, errs={errs}")
    assert not ok

    print("\n=== TEST 5: syntax error ===")
    bad4 = "import matplotlib.pyplot as plt\ndef broken(\nplt.savefig(output_path)"
    ok, errs = codegen_and_render(bad4, Path("test_bad4.png"))
    print(f"  ok={ok}, errs={errs}")
    assert not ok

    print("\nALL SANDBOX TESTS PASSED")
