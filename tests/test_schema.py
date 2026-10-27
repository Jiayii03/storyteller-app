"""Schema tests: enum rejection, slug ids, allowed-values error message."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from storyteller.schema import Project, format_validation_error

EXAMPLE = Path(__file__).parent.parent / "examples" / "rainy_cafe" / "project.json"


def test_example_project_parses():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    Project.model_validate(data)


def test_bad_enum_rejected_with_allowed_values():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["style_bible"]["medium"] = "oil_painting"
    with pytest.raises(ValidationError) as exc:
        Project.model_validate(data)
    lines = format_validation_error(exc.value)
    assert any("style_bible" in l or "medium" in l for l in lines)


def test_non_slug_id_rejected():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["characters"][0]["id"] = "Mia Prime"
    with pytest.raises(ValidationError):
        Project.model_validate(data)


def test_extra_fields_allowed():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["project"]["future_field"] = "kept"
    p = Project.model_validate(data)
    assert p.project.model_extra["future_field"] == "kept"
