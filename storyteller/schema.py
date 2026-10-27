"""Pydantic models and enums. Single source of truth for project.json."""

from __future__ import annotations

from enum import Enum
from typing import Any, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------- enums


class Medium(str, Enum):
    photorealistic = "photorealistic"
    cinematic_film_still = "cinematic_film_still"
    render_3d = "3d_render"
    anime = "anime"
    illustration = "illustration"
    watercolor = "watercolor"
    claymation = "claymation"
    other = "other"


ASPECT_RATIOS = ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9")
IMAGE_ASPECT_RATIOS = ASPECT_RATIOS + ("3:2", "2:3", "4:5", "5:4")
VIDEO_ASPECT_RATIOS = ("16:9", "9:16")


class AspectRatio(str, Enum):
    a16_9 = "16:9"
    a9_16 = "9:16"
    a1_1 = "1:1"
    a4_3 = "4:3"
    a3_4 = "3:4"
    a21_9 = "21:9"


class TimeOfDay(str, Enum):
    dawn = "dawn"
    morning = "morning"
    midday = "midday"
    afternoon = "afternoon"
    golden_hour = "golden_hour"
    dusk = "dusk"
    night = "night"


class LocationType(str, Enum):
    interior = "interior"
    exterior = "exterior"
    mixed = "mixed"


class ShotSize(str, Enum):
    extreme_wide = "extreme_wide"
    wide = "wide"
    full = "full"
    medium_wide = "medium_wide"
    medium = "medium"
    medium_close = "medium_close"
    close_up = "close_up"
    extreme_close_up = "extreme_close_up"
    insert = "insert"


class Angle(str, Enum):
    eye_level = "eye_level"
    low_angle = "low_angle"
    high_angle = "high_angle"
    birds_eye = "birds_eye"
    worms_eye = "worms_eye"
    dutch = "dutch"
    overhead = "overhead"


class Perspective(str, Enum):
    neutral = "neutral"
    over_the_shoulder = "over_the_shoulder"
    pov = "pov"
    two_shot = "two_shot"
    profile = "profile"
    three_quarter = "three_quarter"
    from_behind = "from_behind"


class DepthOfField(str, Enum):
    deep = "deep"
    medium = "medium"
    shallow = "shallow"


class Movement(str, Enum):
    static = "static"
    push_in = "push_in"
    pull_out = "pull_out"
    pan_left = "pan_left"
    pan_right = "pan_right"
    tilt_up = "tilt_up"
    tilt_down = "tilt_down"
    tracking = "tracking"
    orbit = "orbit"
    handheld = "handheld"
    crane_up = "crane_up"
    crane_down = "crane_down"
    dolly_zoom = "dolly_zoom"


class MovementSpeed(str, Enum):
    very_slow = "very_slow"
    slow = "slow"
    medium = "medium"
    fast = "fast"


class LightQuality(str, Enum):
    hard = "hard"
    soft = "soft"
    diffused = "diffused"


class Contrast(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TransitionOut(str, Enum):
    cut = "cut"
    dissolve = "dissolve"
    fade_black = "fade_black"
    match_cut = "match_cut"
    whip = "whip"


class AssetType(str, Enum):
    style_reference = "style_reference"
    character_reference = "character_reference"
    location_reference = "location_reference"
    prop_reference = "prop_reference"
    keyframe = "keyframe"
    motion_clip = "motion_clip"
    storyboard_sheet = "storyboard_sheet"


class FrameRole(str, Enum):
    start = "start"
    end = "end"
    single = "single"


class Status(str, Enum):
    pending = "pending"
    generated = "generated"
    approved = "approved"
    failed = "failed"
    skipped = "skipped"


class Pacing(str, Enum):
    slow = "slow"
    natural = "natural"
    quick = "quick"


# ---------------------------------------------------------------- helpers


class _Flexible(BaseModel):
    """Base: unknown keys are kept, not rejected (forward compatibility)."""

    model_config = ConfigDict(extra="allow")


def _slug(value: str) -> str:
    import re

    if not re.fullmatch(r"[A-Za-z0-9_]+", value or ""):
        raise ValueError(
            f"id must be a slug (letters, digits, underscores): {value!r}"
        )
    return value


# ---------------------------------------------------------------- entities


class Skin(_Flexible):
    tone: str = ""
    texture: str = ""
    marks: str = ""


class EyeSpec(_Flexible):
    color: str = ""
    shape: str = ""


class Face(_Flexible):
    shape: str = ""
    eyes: Union[str, EyeSpec] = ""
    eyebrows: str = ""
    nose: str = ""
    lips: str = ""
    facial_hair: str = ""
    distinguishing_features: str = ""


class Hair(_Flexible):
    length: str = ""
    style: str = ""
    color: str = ""
    texture: str = ""


class Wardrobe(_Flexible):
    top: str = ""
    bottom: str = ""
    outerwear: str = ""
    footwear: str = ""
    accessories: str = ""
    colors: str = ""
    fabrics: str = ""


class Character(_Flexible):
    id: str
    name: str
    role: str = ""
    gender: str = ""
    age: Union[int, str] = ""
    ethnicity_or_heritage: str = ""
    height_build: str = ""
    skin: Skin = Field(default_factory=Skin)
    face: Face = Field(default_factory=Face)
    hair: Hair = Field(default_factory=Hair)
    default_expression: str = ""
    wardrobe: Wardrobe = Field(default_factory=Wardrobe)
    wardrobe_variants: dict[str, Wardrobe] = Field(default_factory=dict)
    demeanor_body_language: str = ""
    input_reference_images: list[str] = Field(default_factory=list)
    consistency_notes: str = ""
    reference_views: list[str] = Field(default_factory=list)  # e.g. ["turnaround", "face_closeup"]

    @field_validator("id")
    @classmethod
    def _id_slug(cls, v: str) -> str:
        return _slug(v)


class Location(_Flexible):
    id: str
    name: str
    type: LocationType = LocationType.interior
    description: str = ""
    architecture_layout: str = ""
    key_elements: list[str] = Field(default_factory=list)
    materials_textures: list[str] = Field(default_factory=list)
    default_time_of_day: TimeOfDay | None = None
    default_weather: str = ""
    default_lighting: str = ""
    ambient_details: list[str] = Field(default_factory=list)
    input_reference_images: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_slug(cls, v: str) -> str:
        return _slug(v)


class Prop(_Flexible):
    id: str
    name: str
    description: str = ""
    size_scale: str = ""
    materials: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    condition: str = ""
    branding_text: str = ""
    input_reference_images: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_slug(cls, v: str) -> str:
        return _slug(v)


# ---------------------------------------------------------------- style bible


class StyleBible(_Flexible):
    medium: Medium | None = None
    genre_mood: str = ""
    color_palette: list[str] = Field(default_factory=list)
    color_grade: str = ""
    film_stock_or_look: str = ""
    default_lens_mm: float | None = None
    lighting_style: str = ""
    texture_detail: str = ""
    era_setting: str = ""
    global_negative_prompt: list[str] = Field(default_factory=list)
    reference_image_paths: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- shot


class Camera(_Flexible):
    shot_size: ShotSize | None = None
    angle: Angle | None = None
    perspective: Perspective | None = None
    camera_height: str = ""
    lens_mm: float | None = None
    depth_of_field: DepthOfField | None = None
    aperture_hint: str = ""
    movement: Movement | None = None
    movement_speed: MovementSpeed | None = None


class Lighting(_Flexible):
    key_light: str = ""
    quality: LightQuality | None = None
    contrast: Contrast | None = None
    color_temperature: str = ""
    practical_lights: str = ""
    atmosphere: str = ""
    shadows: str = ""


class Subject(_Flexible):
    character_id: str
    wardrobe_variant: str = ""
    position_in_frame: str = ""
    facing_direction: str = ""
    pose: str = ""
    action: str = ""
    facial_expression: str = ""
    gaze: str = ""
    hands: str = ""
    interaction: str = ""
    emotional_state: str = ""


class PropInShot(_Flexible):
    prop_id: str
    position: str = ""
    state: str = ""


class Background(_Flexible):
    description: str = ""
    depth_layers: str = ""
    extras: str = ""
    focus_state: str = ""


class Composition(_Flexible):
    framing_rule: str = ""
    headroom: str = ""
    negative_space: str = ""
    screen_direction: str = ""


class KeyframeSpec(_Flexible):
    description: str = ""
    overrides: dict[str, Any] = Field(default_factory=dict)


class EndKeyframeSpec(KeyframeSpec):
    changes_from_start: list[str] = Field(default_factory=list)


class KeyframeSet(_Flexible):
    start: KeyframeSpec | None = None
    end: EndKeyframeSpec | None = None


class Motion(_Flexible):
    duration_sec: float = 2.0
    subject_motion: str = ""
    camera_motion: str = ""
    environment_motion: str = ""
    pacing: Pacing = Pacing.natural
    video_prompt: str = ""
    audio_notes: str = ""

    @property
    def prompt_override_text(self) -> str:
        """Hand-written prompt; legacy kling_prompt key still honored."""
        return self.video_prompt or (self.model_extra or {}).get("kling_prompt", "")


class Shot(_Flexible):
    id: str
    sequence_index: int = 0
    duration_sec: float = 4.0
    narrative_purpose: str = ""
    summary: str = ""
    location_id: str = ""
    time_of_day: TimeOfDay | None = None
    weather: str = ""
    set_dressing_notes: str = ""
    camera: Camera = Field(default_factory=Camera)
    lighting: Lighting = Field(default_factory=Lighting)
    subjects: list[Subject] = Field(default_factory=list)
    props_in_shot: list[PropInShot] = Field(default_factory=list)
    background: Background = Field(default_factory=Background)
    composition: Composition = Field(default_factory=Composition)
    color_grade_override: str = ""
    keyframes: KeyframeSet = Field(default_factory=KeyframeSet)
    motion: Motion = Field(default_factory=Motion)
    continuity_notes: str = ""
    transition_out: TransitionOut = TransitionOut.cut
    negative_prompt: list[str] = Field(default_factory=list)
    chain_from_previous: bool = False

    @field_validator("id")
    @classmethod
    def _id_slug(cls, v: str) -> str:
        return _slug(v)


# ---------------------------------------------------------------- job list


class VideoSpec(_Flexible):
    duration_sec: float = 2.0
    resolution: str = "720p"
    use_end_frame: bool = False
    generate_audio: bool | None = None


class AssetJob(_Flexible):
    asset_id: str
    asset_type: AssetType
    target_id: str = ""
    purpose: str = ""
    frame_role: FrameRole = FrameRole.single
    variants: int | None = None
    input_asset_ids: list[str] = Field(default_factory=list)
    input_image_paths: list[str] = Field(default_factory=list)
    prompt_override: str = ""
    prompt_append: str = ""
    negative_prompt_append: list[str] = Field(default_factory=list)
    aspect_ratio: str | None = None
    model_override: str | None = None
    seed: int | None = None
    video: VideoSpec | None = None
    status: Status = Status.pending  # app-managed; state.json is authoritative

    @field_validator("asset_id")
    @classmethod
    def _id_slug(cls, v: str) -> str:
        return _slug(v)


class ModelsConfig(_Flexible):
    image_model: str = ""
    video_model: str = ""
    image_resolution: str = "1K"
    video_resolution: str = "720p"


class ProjectMeta(_Flexible):
    id: str
    title: str = ""
    logline: str = ""
    aspect_ratio: AspectRatio = AspectRatio.a16_9
    target_video_model: str = ""
    target_total_duration_sec: float = 0.0
    language: str = "en"

    @field_validator("id")
    @classmethod
    def _id_slug(cls, v: str) -> str:
        return _slug(v)


class Project(_Flexible):
    """Top-level project.json document."""

    schema_version: str = "0.1"
    project: ProjectMeta
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    style_bible: StyleBible = Field(default_factory=StyleBible)
    characters: list[Character] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    props: list[Prop] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)
    assets: list[AssetJob] = Field(default_factory=list)


# ---------------------------------------------------------------- utilities


def allowed_values(enum_cls: type[Enum]) -> str:
    return ", ".join(e.value for e in enum_cls)


def format_validation_error(exc: Exception) -> list[str]:
    """Turn a pydantic ValidationError into readable, spec-aware messages."""
    from pydantic import ValidationError

    out: list[str] = []
    assert isinstance(exc, ValidationError)
    for err in exc.errors():
        path = ".".join(str(p) for p in err["loc"]) or "<root>"
        msg = err["msg"]
        enum_hints = {
            "Literal": "",
        }
        _ = enum_hints
        # Surface allowed values for enum/enum-value failures.
        if "enum" in msg or "literal_error" == err.get("type"):
            ctx = err.get("ctx", {})
            expected = ctx.get("expected")
            if expected:
                msg = f"{msg} (expected one of: {expected})"
        out.append(f"{path}: {msg} (got: {err.get('input')!r})")
    return out

