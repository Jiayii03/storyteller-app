"""Pure prompt builder: (project, asset, resolved_inputs) -> prompt text,
negative prompt and labelled input images. Unit-testable, no API calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .schema import (
    AssetJob, AssetType, Character, FrameRole, Location, Project, Prop, Shot,
)


# ---------------------------------------------------------------- helpers


def _identity_paragraph(ch: Character) -> str:
    parts: list[str] = []
    if ch.gender:
        parts.append(f"{ch.gender}")
    if ch.age not in ("", None):
        parts.append(f"aged {ch.age}")
    if ch.ethnicity_or_heritage:
        parts.append(ch.ethnicity_or_heritage)
    if ch.height_build:
        parts.append(ch.height_build)
    head = f"{ch.name} ({', '.join(parts)})" if parts else ch.name
    lines = [f"{head}."]
    if ch.skin.tone:
        lines.append(f"Skin: {ch.skin.tone}")
    if ch.skin.texture:
        lines.append(f"Skin texture: {ch.skin.texture}")
    if ch.skin.marks:
        lines.append(f"Skin marks: {ch.skin.marks}")
    f = ch.face
    face_bits: list[str] = []
    if f.shape:
        face_bits.append(f"{f.shape} face")
    if isinstance(f.eyes, str) and f.eyes:
        face_bits.append(f"{f.eyes} eyes")
    elif not isinstance(f.eyes, str):
        bits = []
        if getattr(f.eyes, "color", ""):
            bits.append(str(f.eyes.color))
        if getattr(f.eyes, "shape", ""):
            bits.append(str(f.eyes.shape))
        if bits:
            face_bits.append(", ".join(bits) + " eyes")
    if f.eyebrows:
        face_bits.append(f"{f.eyebrows} eyebrows")
    if f.nose:
        face_bits.append(f"{f.nose} nose")
    if f.lips:
        face_bits.append(f"{f.lips} lips")
    if f.facial_hair:
        face_bits.append(f.facial_hair)
    if f.distinguishing_features:
        face_bits.append(f.distinguishing_features)
    if face_bits:
        lines.append("Face: " + ", ".join(face_bits) + ".")
    h = ch.hair
    hair_bits = [str(h.length), str(h.style), str(h.color), str(h.texture)]
    hair_bits = [b for b in hair_bits if b and b != "None"]
    if hair_bits:
        lines.append("Hair: " + ", ".join(hair_bits) + ".")
    w = ch.wardrobe
    w_bits = [str(getattr(w, k, "")) for k in
              ("top", "bottom", "outerwear", "footwear", "accessories", "colors", "fabrics")]
    w_bits = [b for b in w_bits if b and b != "None"]
    if w_bits:
        lines.append("Wearing: " + ", ".join(w_bits) + ".")
    if ch.demeanor_body_language:
        lines.append(f"Demeanor: {ch.demeanor_body_language}.")
    if ch.consistency_notes:
        lines.append(f"Consistency: {ch.consistency_notes}")
    return "\n".join(lines)


def _wardrobe_for(ch: Character, variant: str) -> str:
    if variant and variant in ch.wardrobe_variants:
        w = ch.wardrobe_variants[variant]
        bits = [str(getattr(w, k, "")) for k in
                ("top", "bottom", "outerwear", "footwear", "accessories", "colors", "fabrics")]
        bits = [b for b in bits if b and b != "None"]
        return ", ".join(bits)
    return ""


def _style_paragraph(project: Project) -> str:
    sb = project.style_bible
    lines: list[str] = []
    medium = sb.medium.value.replace("_", " ") if sb.medium else ""
    first = " ".join(x for x in (medium, sb.genre_mood) if x)
    if first:
        lines.append(f"Style: {first}.")
    if sb.era_setting:
        lines.append(f"Setting: {sb.era_setting}.")
    if sb.color_palette:
        lines.append("Color palette: " + ", ".join(sb.color_palette) + ".")
    if sb.color_grade:
        lines.append(f"Color grade: {sb.color_grade}.")
    if sb.film_stock_or_look:
        lines.append(f"Look: {sb.film_stock_or_look}.")
    if sb.lighting_style:
        lines.append(f"Lighting: {sb.lighting_style}.")
    if sb.texture_detail:
        lines.append(f"Texture detail: {sb.texture_detail}.")
    return "\n".join(lines)


def _apply_overrides(shot: Shot, overrides: dict[str, Any]) -> Shot:
    """Shallow overrides for simple shot fields from keyframes.<role>.overrides."""
    allowed = {"time_of_day", "weather", "set_dressing_notes", "camera", "lighting",
               "composition", "color_grade_override"}
    upd: dict[str, Any] = {}
    for k, v in overrides.items():
        if k == "time_of_day":
            from .schema import TimeOfDay
            upd[k] = TimeOfDay(v) if v is not None else None
        elif k == "camera":
            from .schema import Camera
            upd[k] = Camera.model_validate(v)
        elif k == "lighting":
            from .schema import Lighting
            upd[k] = Lighting.model_validate(v)
        elif k == "composition":
            from .schema import Composition
            upd[k] = Composition.model_validate(v)
        elif k in ("weather", "set_dressing_notes", "color_grade_override"):
            upd[k] = str(v)
    if not upd:
        return shot
    return shot.model_copy(update=upd)


def _camera_paragraph(shot: Shot) -> str:
    c = shot.camera
    bits: list[str] = []
    if c.shot_size:
        bits.append(str(c.shot_size.value).replace("_", " "))
    if c.angle:
        bits.append(str(c.angle.value).replace("_", " "))
    if c.perspective:
        bits.append(f"{str(c.perspective.value).replace('_', ' ')} perspective")
    if c.camera_height:
        bits.append(f"camera at {c.camera_height}")
    if c.lens_mm is not None:
        bits.append(f"{c.lens_mm:g}mm lens")
    if c.depth_of_field:
        bits.append(f"{c.depth_of_field.value} depth of field")
    if c.aperture_hint:
        bits.append(c.aperture_hint)
    out = "Camera: " + (", ".join(bits) if bits else "unspecified") + "."
    if c.movement:
        speed = f" ({str(c.movement_speed.value).replace('_', ' ')})" if c.movement_speed else ""
        out += f" Movement: {str(c.movement.value).replace('_', ' ')}{speed}."
    return out


def _location_paragraph(project: Project, shot: Shot) -> str:
    loc = next((l for l in project.locations if l.id == shot.location_id), None)
    lines: list[str] = []
    tod = shot.time_of_day.value if shot.time_of_day else (
        loc.default_time_of_day.value if loc and loc.default_time_of_day else "")
    weather = shot.weather or (loc.default_weather if loc else "")
    if loc:
        head = f"Location: {loc.name}"
        if loc.type.value == "interior":
            head += " (interior)"
        elif loc.type.value == "exterior":
            head += " (exterior)"
        lines.append(head + ".")
        if loc.description:
            lines.append(loc.description)
        if loc.architecture_layout:
            lines.append(f"Layout: {loc.architecture_layout}.")
        if loc.key_elements:
            lines.append("Key elements: " + ", ".join(loc.key_elements) + ".")
        if loc.materials_textures:
            lines.append("Materials: " + ", ".join(loc.materials_textures) + ".")
        if loc.ambient_details:
            lines.append("Ambient details: " + ", ".join(loc.ambient_details) + ".")
        if loc.default_lighting and not shot.lighting.key_light:
            lines.append(f"Lighting: {loc.default_lighting}.")
    if tod:
        lines.append(f"Time of day: {str(tod).replace('_', ' ')}.")
    if weather:
        lines.append(f"Weather: {weather}.")
    if shot.set_dressing_notes:
        lines.append(f"Set dressing: {shot.set_dressing_notes}.")
    return "\n".join(lines)


def _subjects_paragraph(project: Project, shot: Shot) -> str:
    lines: list[str] = []
    for subj in shot.subjects:
        ch = next((c for c in project.characters if c.id == subj.character_id), None)
        if ch is None:
            continue
        lines.append(f"Subject: {_identity_paragraph(ch).replace(chr(10), ' | ')}")
        wv = _wardrobe_for(ch, subj.wardrobe_variant)
        if wv:
            lines.append(f"  Wardrobe variant ({subj.wardrobe_variant}): {wv}.")
        s = subj.model_extra or {}
        details: list[str] = []
        for field in ("position_in_frame", "facing_direction", "pose", "action",
                      "facial_expression", "gaze", "hands", "interaction",
                      "emotional_state"):
            val = getattr(subj, field, "") or s.get(field, "")
            if val:
                details.append(f"{field}: {val}")
        if details:
            lines.append("  " + "; ".join(details) + ".")
    return "\n".join(lines)


def _props_paragraph(project: Project, shot: Shot) -> str:
    lines: list[str] = []
    for p in shot.props_in_shot:
        pr = next((x for x in project.props if x.id == p.prop_id), None)
        if pr is None:
            continue
        desc = f"Prop: {pr.name}."
        if pr.description:
            desc += f" {pr.description}"
        if pr.size_scale:
            desc += f" Size: {pr.size_scale}."
        if pr.materials:
            desc += f" Materials: {', '.join(pr.materials)}."
        if pr.colors:
            desc += f" Colors: {', '.join(pr.colors)}."
        if pr.condition:
            desc += f" Condition: {pr.condition}."
        if p.position:
            desc += f" Position: {p.position}."
        if p.state:
            desc += f" State: {p.state}."
        lines.append(desc)
    return "\n".join(lines)


def _background_paragraph(shot: Shot) -> str:
    b = shot.background
    bits: list[str] = []
    if b.description:
        bits.append(b.description)
    if b.depth_layers:
        bits.append(f"depth layers: {b.depth_layers}")
    if b.extras:
        bits.append(f"extras: {b.extras}")
    if b.focus_state:
        bits.append(f"focus: {b.focus_state}")
    return f"Background: {'; '.join(bits)}." if bits else ""


def _lighting_paragraph(project: Project, shot: Shot) -> str:
    li = shot.lighting
    sb = project.style_bible
    lines: list[str] = []
    if li.key_light:
        q = f", {li.quality.value}" if li.quality else ""
        ct = f", {li.color_temperature} color temperature" if li.color_temperature else ""
        lines.append(f"Key light: {li.key_light}{q}{ct}.")
    elif sb.lighting_style:
        lines.append(f"Lighting: {sb.lighting_style}.")
    if li.contrast:
        lines.append(f"Contrast: {li.contrast.value}.")
    if li.practical_lights:
        lines.append(f"Practical lights: {li.practical_lights}.")
    if li.atmosphere:
        lines.append(f"Atmosphere: {li.atmosphere}.")
    if li.shadows:
        lines.append(f"Shadows: {li.shadows}.")
    return "\n".join(lines)


def _composition_paragraph(project: Project, shot: Shot) -> str:
    co = shot.composition
    bits: list[str] = []
    if co.framing_rule:
        bits.append(f"framing: {co.framing_rule}")
    if co.headroom:
        bits.append(f"headroom: {co.headroom}")
    if co.negative_space:
        bits.append(f"negative space: {co.negative_space}")
    if co.screen_direction:
        bits.append(f"screen direction: {co.screen_direction}")
    grade = shot.color_grade_override or project.style_bible.color_grade
    if grade:
        bits.append(f"color grade: {grade}")
    lens = shot.camera.lens_mm if shot.camera.lens_mm is not None else project.style_bible.default_lens_mm
    if lens is not None and shot.camera.lens_mm is None:
        bits.append(f"lens: {lens:g}mm")
    return f"Composition: {'; '.join(bits)}." if bits else ""


def _negative_line(project: Project, asset: AssetJob, shot: Shot | None) -> str:
    items: list[str] = list(project.style_bible.global_negative_prompt)
    if shot is not None:
        items += list(shot.negative_prompt)
    items += list(asset.negative_prompt_append)
    seen: set[str] = set()
    uniq = [x for x in items if x and not (x in seen or seen.add(x))]
    return "Avoid: " + ", ".join(uniq) + "." if uniq else ""


# ---------------------------------------------------------------- public API


def legend_block(inputs: list[tuple[Path, str]]) -> str:
    lines = [f"Image {i + 1} is {legend}."
             for i, (_path, legend) in enumerate(inputs)]
    return "\n".join(lines)


def compose_motion_prompt(shot: Shot) -> str:
    """Motion prompt body: hand-written video_prompt (or legacy kling_prompt)
    if present, else auto-composed from the shot's motion fields."""
    m = shot.motion
    parts: list[str] = []
    if m.camera_motion or shot.camera.movement:
        cm = m.camera_motion or f"{str(shot.camera.movement.value).replace('_', ' ')} camera"
        if shot.camera.movement_speed:
            cm += f", {str(shot.camera.movement_speed.value).replace('_', ' ')}"
        parts.append(f"Camera: {cm}.")
    if m.subject_motion:
        parts.append(f"Subject motion: {m.subject_motion}.")
    if m.environment_motion:
        parts.append(f"Environment motion: {m.environment_motion}.")
    if m.pacing:
        parts.append(f"Pacing: {m.pacing.value}.")
    body = "Animate this frame. Keep the subject and scene identical to the first frame."
    if parts:
        body = f"{body} " + " ".join(parts)
    override = m.prompt_override_text
    return override if override else body


def build_prompt(
    project: Project, asset: AssetJob,
    inputs: list[tuple[Path, str]],
) -> dict[str, Any]:
    """Returns {prompt_text, negative_prompt, input_images: [(path, legend)]}."""
    shots = {s.id: s for s in project.shots}
    chars = {c.id: c for c in project.characters}
    locs = {l.id: l for l in project.locations}
    props = {p.id: p for p in project.props}
    skip_style = bool((asset.model_extra or {}).get("skip_style_bible", False))

    if asset.prompt_override:
        body = asset.prompt_override
        if not skip_style:
            style = _style_paragraph(project)
            body = f"{style}\n{body}" if style else body
        if asset.prompt_append:
            body += f"\n{asset.prompt_append}"
        return {
            "prompt_text": body,
            "negative_prompt": _negative_line(project, asset, None),
            "input_images": inputs,
        }

    if asset.asset_type == AssetType.style_reference:
        sb = project.style_bible
        body = (
            "Create a single style reference image that defines the overall look and mood "
            "for this project. It should show the palette, lighting and texture the whole "
            "video will share."
        )
        style = _style_paragraph(project)
        body = f"{style}\n{body}" if style and not skip_style else body
        if asset.prompt_append:
            body += f"\n{asset.prompt_append}"
        return {"prompt_text": body, "negative_prompt": _negative_line(project, asset, None),
                "input_images": inputs}

    if asset.asset_type == AssetType.character_reference:
        ch = chars.get(asset.target_id)
        if ch is None:
            raise ValueError(f"Asset {asset.asset_id}: character {asset.target_id!r} not found")
        body = (
            f"Create a full-body character reference sheet of {ch.name}. "
            "Neutral standing pose, facing the camera, arms relaxed at the sides, "
            "plain light-grey background, even soft lighting, no props, no other people. "
            "This image is the identity anchor: face, hair, build and wardrobe must be "
            "sharp and clearly visible."
        )
        style = "" if skip_style else _style_paragraph(project)
        identity = _identity_paragraph(ch)
        body = "\n".join(x for x in (style, identity, body) if x)
        if "turnaround" in ch.reference_views:
            body += ("\nAdditionally generate a turnaround sheet: front, three-quarter and "
                     "side view of the same character on one sheet, same background.")
        if "face_closeup" in ch.reference_views:
            body += "\nAlso include a close-up of the face, neutral expression, same lighting."
        if asset.prompt_append:
            body += f"\n{asset.prompt_append}"
        return {"prompt_text": body, "negative_prompt": _negative_line(project, asset, None),
                "input_images": inputs}

    if asset.asset_type == AssetType.location_reference:
        loc = locs.get(asset.target_id)
        if loc is None:
            raise ValueError(f"Asset {asset.asset_id}: location {asset.target_id!r} not found")
        body = (
            f"Create an establishing reference image of {loc.name} with no people in frame."
        )
        if loc.description:
            body += f" {loc.description}"
        if loc.architecture_layout:
            body += f" Layout: {loc.architecture_layout}."
        if loc.key_elements:
            body += " Key elements: " + ", ".join(loc.key_elements) + "."
        if loc.materials_textures:
            body += " Materials: " + ", ".join(loc.materials_textures) + "."
        if loc.ambient_details:
            body += " Ambient details: " + ", ".join(loc.ambient_details) + "."
        if loc.default_time_of_day:
            body += f" Time of day: {str(loc.default_time_of_day.value).replace('_', ' ')}."
        if loc.default_weather:
            body += f" Weather: {loc.default_weather}."
        if loc.default_lighting:
            body += f" Lighting: {loc.default_lighting}."
        style = "" if skip_style else _style_paragraph(project)
        body = "\n".join(x for x in (style, body) if x)
        if asset.prompt_append:
            body += f"\n{asset.prompt_append}"
        return {"prompt_text": body, "negative_prompt": _negative_line(project, asset, None),
                "input_images": inputs}

    if asset.asset_type == AssetType.prop_reference:
        pr = props.get(asset.target_id)
        if pr is None:
            raise ValueError(f"Asset {asset.asset_id}: prop {asset.target_id!r} not found")
        body = (
            f"Create an isolated reference image of the prop {pr.name!r} on a plain "
            "neutral background, centered, evenly lit, no hands, no people."
        )
        if pr.description:
            body += f" {pr.description}"
        if pr.size_scale:
            body += f" Size: {pr.size_scale}."
        if pr.materials:
            body += " Materials: " + ", ".join(pr.materials) + "."
        if pr.colors:
            body += " Colors: " + ", ".join(pr.colors) + "."
        if pr.condition:
            body += f" Condition: {pr.condition}."
        style = "" if skip_style else _style_paragraph(project)
        body = "\n".join(x for x in (style, body) if x)
        if asset.prompt_append:
            body += f"\n{asset.prompt_append}"
        return {"prompt_text": body, "negative_prompt": _negative_line(project, asset, None),
                "input_images": inputs}

    if asset.asset_type == AssetType.keyframe:
        shot = shots.get(asset.target_id)
        if shot is None:
            raise ValueError(f"Asset {asset.asset_id}: shot {asset.target_id!r} not found")
        if asset.frame_role == FrameRole.end:
            kf = shot.keyframes.end
        else:
            kf = shot.keyframes.start
        if kf is not None and kf.overrides:
            shot = _apply_overrides(shot, kf.overrides)

        paragraphs: list[str] = []
        if not skip_style:
            style = _style_paragraph(project)
            if style:
                paragraphs.append(style)
        paragraphs.append(_camera_paragraph(shot))
        loc_para = _location_paragraph(project, shot)
        if loc_para:
            paragraphs.append(loc_para)
        subj_para = _subjects_paragraph(project, shot)
        if subj_para:
            paragraphs.append(subj_para)
        props_para = _props_paragraph(project, shot)
        if props_para:
            paragraphs.append(props_para)
        bg_para = _background_paragraph(shot)
        if bg_para:
            paragraphs.append(bg_para)
        light_para = _lighting_paragraph(project, shot)
        if light_para:
            paragraphs.append(light_para)
        comp_para = _composition_paragraph(project, shot)
        if comp_para:
            paragraphs.append(comp_para)

        desc = kf.description if kf is not None and kf.description else ""
        if asset.frame_role == FrameRole.end:
            changes = shot.keyframes.end.changes_from_start if shot.keyframes.end else []
            body = (
                "Same scene, same character, same lighting. Change only: "
                + "; ".join(changes or [])
                + "."
            )
            if desc:
                body = f"{body} {desc}"
            paragraphs.append(body)
        elif desc:
            paragraphs.append(f"Frame description: {desc}")

        if asset.prompt_append:
            paragraphs.append(asset.prompt_append)
        if shot.continuity_notes:
            paragraphs.append(f"Continuity: {shot.continuity_notes}")

        paragraphs.append(legend_block(inputs))
        neg = _negative_line(project, asset, shot)
        if neg:
            paragraphs.append(neg)
        paragraphs = [p for p in paragraphs if p.strip()]
        return {"prompt_text": "\n\n".join(paragraphs), "negative_prompt": neg,
                "input_images": inputs}

    if asset.asset_type == AssetType.motion_clip:
        shot = shots.get(asset.target_id)
        if shot is None:
            raise ValueError(f"Asset {asset.asset_id}: shot {asset.target_id!r} not found")
        body = compose_motion_prompt(shot)
        if asset.prompt_append:
            body += f"\n{asset.prompt_append}"
        return {"prompt_text": body, "negative_prompt": _negative_line(project, asset, shot),
                "input_images": inputs}

    raise ValueError(f"Asset type {asset.asset_type.value} has no prompt (built locally).")
