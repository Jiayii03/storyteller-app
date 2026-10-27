"""Prompt builder tests: pure functions, no API calls."""

import json
from pathlib import Path

from storyteller import prompt_builder, resolver
from storyteller.schema import AssetJob, AssetType, FrameRole, Project

EXAMPLE = Path(__file__).parent.parent / "examples" / "rainy_cafe" / "project.json"


def _project() -> Project:
    return Project.model_validate(json.loads(EXAMPLE.read_text(encoding="utf-8")))


def test_keyframe_prompt_sections(example_project):
    p = example_project
    asset = next(a for a in p.assets if a.asset_id == "kf_S01_start")
    built = prompt_builder.build_prompt(p, asset, [])
    text = built["prompt_text"]
    assert "cinematic film still" in text
    assert "medium close" in text
    assert "50mm lens" in text
    assert "Mia" in text
    assert "both hands wrapped around a ceramic mug" in text
    assert "steaming, half full" in text
    assert "bokeh" in text
    assert "Avoid:" in text
    assert "distorted face" in text


def test_prompt_override_replaces_body(example_project):
    p = example_project
    asset = AssetJob(asset_id="kf_S01_start", asset_type=AssetType.keyframe,
                     target_id="S01", prompt_override="A single red balloon.")
    built = prompt_builder.build_prompt(p, asset, [])
    assert "A single red balloon." in built["prompt_text"]
    # style bible still applied unless skip_style_bible
    assert "Color palette:" in built["prompt_text"]
    asset_extra = AssetJob(asset_id="kf_S01_x", asset_type=AssetType.keyframe,
                           target_id="S01", prompt_override="A single red balloon.",
                           skip_style_bible=True)
    built = prompt_builder.build_prompt(p, asset_extra, [])
    assert built["prompt_text"] == "A single red balloon."


def test_end_keyframe_changes_only(example_project):
    from storyteller.schema import EndKeyframeSpec

    p = example_project
    p.assets.append(AssetJob(asset_id="kf_S01_end", asset_type=AssetType.keyframe,
                             target_id="S01", frame_role=FrameRole.end))
    p.shots[0].keyframes.end = EndKeyframeSpec(
        description="door open", changes_from_start=["door now open"])
    asset = next(a for a in p.assets if a.asset_id == "kf_S01_end")
    built = prompt_builder.build_prompt(p, asset, [])
    assert "Change only: door now open" in built["prompt_text"]
    assert "Same scene, same character, same lighting" in built["prompt_text"]


def test_character_reference_anchor(example_project):
    p = example_project
    asset = next(a for a in p.assets if a.asset_id == "char_mia")
    built = prompt_builder.build_prompt(p, asset, [])
    text = built["prompt_text"]
    assert "full-body character reference sheet" in text
    assert "plain light-grey background" in text
    assert "small mole under left eye" in text


def test_motion_prompt_does_not_redescribe(example_project):
    p = example_project
    asset = next(a for a in p.assets if a.asset_id == "clip_S01")
    built = prompt_builder.build_prompt(p, asset, [])
    text = built["prompt_text"]
    assert "identical to the first frame" in text
    assert "rain streaks down glass" in text


def test_legend_block():
    from pathlib import Path as P
    inputs = [(P("a.png"), "the identity reference for Mia: keep face, hair and build identical")]
    block = prompt_builder.legend_block(inputs)
    assert block == "Image 1 is the identity reference for Mia: keep face, hair and build identical."
