"""Resolver tests: auto job list, topo order, cycle detection, validation."""

import json
from pathlib import Path

import pytest

from storyteller import resolver
from storyteller.schema import AssetJob, AssetType, FrameRole, Project

EXAMPLE = Path(__file__).parent.parent / "examples" / "rainy_cafe" / "project.json"


def _project() -> Project:
    return Project.model_validate(json.loads(EXAMPLE.read_text(encoding="utf-8")))


def test_topo_order_references_before_keyframe(example_project):
    order = [a.asset_id for a in resolver.topo_order(example_project)]
    assert order.index("char_mia") < order.index("kf_S01_start")
    assert order.index("loc_cafe") < order.index("kf_S01_start")
    assert order.index("prop_mug") < order.index("kf_S01_start")
    assert order.index("kf_S01_start") < order.index("clip_S01")
    assert order.index("kf_S01_start") < order.index("kf_S01_end")
    assert order[-1] == "storyboard"


def test_cycle_detection():
    p = _project()
    p.assets = [
        AssetJob(asset_id="a", asset_type=AssetType.keyframe, target_id="S01",
                 input_asset_ids=["b"]),
        AssetJob(asset_id="b", asset_type=AssetType.keyframe, target_id="S01",
                 input_asset_ids=["a"]),
    ]
    with pytest.raises(ValueError, match="cycle"):
        resolver.topo_order(p)


def test_validate_missing_character_id():
    p = _project()
    p.shots[0].subjects[0].character_id = "nobody"
    errors, _w = resolver.validate_project(p)
    assert any("does not exist in characters[]" in e for e in errors)


def test_validate_unknown_input_asset(example_project):
    example_project.assets[3].input_asset_ids = ["ghost_asset"]
    errors, _ = resolver.validate_project(example_project)
    assert any("ghost_asset" in e for e in errors)


def test_end_requires_start():
    p = _project()
    p.assets = [a for a in p.assets if a.asset_id != "kf_S01_start"]
    errors, _ = resolver.validate_project(p)
    assert any("requires a 'start' keyframe" in e for e in errors)


def test_motion_clip_requires_keyframe_input():
    p = _project()
    p.assets = [a for a in p.assets if a.asset_id != "kf_S01_start"]
    errors, _ = resolver.validate_project(p)
    assert any("motion_clip requires a keyframe" in e for e in errors)


def test_branding_warning():
    p = _project()
    p.props[0].branding_text = "Coca Cola"
    _errors, warnings = resolver.validate_project(p)
    assert any("branding_text" in w for w in warnings)


def test_auto_assets_when_omitted():
    p = _project()
    p.assets = []
    jobs = resolver.auto_assets(p)
    ids = [a.asset_id for a in jobs]
    assert "char_mia" in ids and "loc_cafe" in ids and "prop_mug" in ids
    assert "kf_S01_start" in ids and "storyboard" in ids
