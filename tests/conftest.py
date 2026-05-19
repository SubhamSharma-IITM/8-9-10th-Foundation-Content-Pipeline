"""Shared pytest fixtures for pipeline tests."""
from __future__ import annotations

import sys
from pathlib import Path

# Make src.common.* importable when running pytest from the project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def tmp_chapter_dir(tmp_path: Path) -> Path:
    """Throwaway directory mimicking a chapter content_dir layout."""
    d = tmp_path / "chapter_test_dummy" / "ncert"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def minimal_topology_data() -> dict:
    """A dual-shaped topology that should pass validate_dual_topology."""
    return {
        "Magnetic Effects of Electric Current": {
            "Magnetic Field and Field Lines": [
                "Magnetic Field",
                "Magnetic Field Lines",
            ],
            "Magnetic Effect of Current": [
                "Field due to a Current-carrying Conductor",
                "Right-Hand Thumb Rule",
            ],
        }
    }


@pytest.fixture
def minimal_content_data() -> dict:
    """A dual-shaped content that should pass validate_dual_content."""
    return {
        "Magnetic Effects of Electric Current": {
            "Magnetic Field and Field Lines": {
                "Magnetic Field": {
                    "Summary": {
                        "Theory": "A magnetic field is a region around a magnet where its force can be detected.",
                        "VisualContent": {"Needed": False},
                    },
                    "SCQs": {
                        "Question 1": {
                            "isBackExercise": False,
                            "Difficulty": "Easy",
                            "Question": "What is a magnetic field?",
                            "Options": {"A": "Force region", "B": "Mass region", "C": "Sound region", "D": "Light region"},
                            "Correct Option": "A",
                            "Solution": "A magnetic field is a region of magnetic force.",
                            "VisualContent": {"Needed": False},
                        }
                    },
                    "SubjectiveTypes": {
                        "Question 1": {
                            "isBackExercise": False,
                            "Difficulty": "Medium",
                            "Question": "Define magnetic field and describe its properties.",
                            "Solution": "Detailed answer...",
                            "VisualContent": {"Needed": False},
                        }
                    },
                    "Examples": {
                        "Example 1": {
                            "isSolvedExample": True,
                            "Question": "Sample example",
                            "Solution": "Sample solution",
                            "VisualContent": {"Needed": False},
                        }
                    },
                }
            }
        }
    }
