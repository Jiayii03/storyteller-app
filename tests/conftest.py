"""Shared test fixtures."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from storyteller.schema import Project  # noqa: E402

EXAMPLE = ROOT / "examples" / "rainy_cafe" / "project.json"


@pytest.fixture()
def example_project() -> Project:
    return Project.model_validate(json.loads(EXAMPLE.read_text(encoding="utf-8")))
