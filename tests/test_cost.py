"""Cost computation tests: pricing table lookup, image and video costs."""

from types import SimpleNamespace

from storyteller.cost import image_cost, video_cost


def test_image_cost_per_image_plus_input():
    usage = SimpleNamespace(prompt_token_count=1000)
    r = image_cost("gemini-3.1-flash-image", "1K", usage, 1)
    assert r["cost_usd"] == round(0.067 + 1000 / 1e6 * 0.50, 4)
    assert r["breakdown"]["image_output"] == 0.067


def test_image_cost_lite():
    usage = SimpleNamespace(prompt_token_count=111)
    r = image_cost("gemini-3.1-flash-lite-image", "1K", usage, 1)
    assert r["cost_usd"] == round(0.034 + 111 / 1e6 * 0.25, 4)


def test_image_cost_unknown_model_returns_none():
    assert image_cost("totally-unknown", "1K", None, 1) is None


def test_image_cost_prefix_match():
    r = image_cost("gemini-3.1-flash-image-preview-today", "2K", None, 1)
    assert r is not None and abs(r["cost_usd"] - 0.101) < 1e-9


def test_video_cost_omni():
    r = video_cost("gemini-omni-1.1-flash", "720p", True, 3)
    assert r["cost_usd"] == round(0.1013 * 3, 4)


def test_video_cost_unknown_model_returns_none():
    assert video_cost("totally-unknown", "720p", False, 4) is None


def test_video_cost_veo_kept_for_enterprise():
    r = video_cost("veo-3.1-generate-preview", "720p", True, 4)
    assert r["cost_usd"] == 1.6


def test_higgsfield_video_cost():
    from storyteller.cost import higgsfield_video_cost
    c = higgsfield_video_cost("seedance-2-5", "480p", 8, None)
    assert c["cost_usd"] == round(0.174 * 8, 4)
    assert c["rate_per_sec"] == 0.174
    assert higgsfield_video_cost("totally-unknown", "480p", 8, None) is None


def test_higgsfield_video_cost_unknown_resolution_is_none():
    from storyteller.cost import higgsfield_video_cost
    # 1080p has no verified rate in the seed catalog: unknown, never guessed
    assert higgsfield_video_cost("seedance-2-5", "1080p", 8, None) is None
