"""
llm_client.py - Provider-agnostic LLM client wrapper with automatic fallback.

Tries providers in order:
  1. Gemini AI Studio (cheap, sometimes rate-limited or project-denied)
  2. Vertex AI (paid quota, more reliable, same Gemini model)
  3. Anthropic Claude (different provider, last resort)

Mirrors the dual-provider pattern from Question Uploading App stage 2/9.

Loads credentials via python-dotenv from the QA App's .env file so we don't
have to maintain a parallel .env. Bash sourcing mangles Windows paths
(D:\\ACADZA_WORK -> D:ACADZA_WORK) so we must use dotenv, not shell export.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Load QA App's .env via dotenv (preserves Windows backslash paths).
# This must run before importing google.genai / anthropic since some of
# them read env at import time.
try:
    from dotenv import load_dotenv
    _QA_ENV = Path(r"D:/ACADZA_WORK/Question Uploading App/.env")
    if _QA_ENV.exists():
        load_dotenv(_QA_ENV)
except ImportError:
    pass


# Hardcoded fallback for the Vertex AI service account JSON if .env path
# came through mangled or missing
_VERTEX_SA_FALLBACK = Path(r"D:/ACADZA_WORK/gen-lang-client-0276374344-1f6e8d787e94.json")
_VERTEX_PROJECT_FALLBACK = "gen-lang-client-0276374344"
_VERTEX_LOCATION_FALLBACK = "global"


def _resolve_vertex_credentials_path() -> Path | None:
    """Get a valid path to the Vertex AI service account JSON, preferring env."""
    env_path = os.environ.get("VERTEX_AI_CREDENTIALS", "")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    if _VERTEX_SA_FALLBACK.exists():
        return _VERTEX_SA_FALLBACK
    return None


def _resolve_vertex_project() -> str:
    return os.environ.get("VERTEX_AI_PROJECT", _VERTEX_PROJECT_FALLBACK)


def _resolve_vertex_location() -> str:
    return os.environ.get("VERTEX_AI_LOCATION", _VERTEX_LOCATION_FALLBACK)


def make_gemini_client(prefer_vertex: bool = False):
    """
    Build a google.genai Client. If prefer_vertex=True, route via Vertex AI
    (requires service account credentials). Otherwise use AI Studio API key.
    """
    from google import genai
    from google.genai import types

    if prefer_vertex:
        sa_path = _resolve_vertex_credentials_path()
        if not sa_path:
            raise RuntimeError(
                "Vertex AI requested but service account JSON not found. "
                f"Tried VERTEX_AI_CREDENTIALS env + fallback {_VERTEX_SA_FALLBACK}"
            )
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(sa_path)
        return genai.Client(
            vertexai=True,
            project=_resolve_vertex_project(),
            location=_resolve_vertex_location(),
            http_options=types.HttpOptions(api_version="v1beta1"),
        )

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set. Load QA App .env first.")
    return genai.Client(api_key=api_key)


def is_permission_error(err: Exception) -> bool:
    """Detect Gemini AI Studio 403 / PERMISSION_DENIED / quota-denied errors."""
    s = str(err)
    return any(tag in s for tag in ("PERMISSION_DENIED", "403", "RESOURCE_EXHAUSTED", "429"))


def make_anthropic_client():
    """Last-resort fallback to Anthropic Claude (used if both Gemini paths fail)."""
    import anthropic
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set.")
    return anthropic.Anthropic(api_key=key)


if __name__ == "__main__":
    # Smoke test: which providers are available?
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Provider availability:")
    print(f"  GEMINI_API_KEY        : {'set' if os.environ.get('GEMINI_API_KEY') else 'MISSING'}")
    print(f"  Vertex AI credentials : {_resolve_vertex_credentials_path() or 'MISSING'}")
    print(f"  ANTHROPIC_API_KEY     : {'set' if os.environ.get('ANTHROPIC_API_KEY') else 'MISSING'}")
    print(f"  Vertex project        : {_resolve_vertex_project()}")
    print(f"  Vertex location       : {_resolve_vertex_location()}")
