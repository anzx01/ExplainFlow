import sys
import io
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.core.config import settings
from src.imagegen.service import SceneImageRequest, _build_local_prompt, _local_prompt, _local_seed, _semantic_prompt_diagnostics, compose_action_board, local_imagegen_status
from src.imagegen.quality import inspect_generated_image, normalize_whiteboard_image


def test_local_imagegen_status_reports_missing_components(monkeypatch, tmp_path: Path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"model")
    monkeypatch.setattr(settings, "local_imagegen_runtime", str(tmp_path / "missing.exe"))
    monkeypatch.setattr(settings, "local_imagegen_model", str(model))
    monkeypatch.setattr(settings, "local_imagegen_vae", str(tmp_path / "missing-vae"))
    monkeypatch.setattr(settings, "local_imagegen_clip_l", str(tmp_path / "missing-clip"))
    monkeypatch.setattr(settings, "local_imagegen_t5xxl", str(tmp_path / "missing-t5"))
    status = local_imagegen_status()
    assert not status["available"]
    assert status["missing"] == ["runtime", "vae", "clip_l", "t5xxl"]


def test_local_prompt_removes_cloud_negative_prompt_and_caps_length():
    prompt = "useful subject " + ("detail " * 300) + "Negative prompt: cloud-only exclusions"
    result = _local_prompt(prompt)
    assert len(result) <= 1000
    assert "Negative prompt" not in result
    assert "cloud-only" not in result
    assert "no artist signature" in result


def test_local_scene_prompt_keeps_action_before_style_noise(monkeypatch):
    monkeypatch.setattr(settings, "imagegen_provider", "local")
    request = SceneImageRequest(
        "boiling", "dumplings", "Boil dumplings",
        "three-stage action: lower dumplings into clear boiling water, pour cold water into the same pot, then scoop floating dumplings with a slotted spoon",
    )
    prompt = _build_local_prompt(request)
    assert len(prompt) < 1100
    assert prompt.index("lower") < prompt.index("realistic instructional")
    assert "slotted spoon" in prompt
    assert "dense infographic" not in prompt


def test_local_scene_prompt_keeps_topic_specific_visual_subject():
    request = SceneImageRequest(
        "attention", "看短视频的坏处", "注意力碎片化",
        "a text-free educational illustration with one large central subject and generous margins",
    )
    prompt = _build_local_prompt(request)
    assert "smartphone" in prompt
    assert "scattered attention" in prompt
    assert "generic geometric icons" in prompt


def test_local_scene_prompt_changes_subject_by_short_video_scene():
    request = SceneImageRequest(
        "sleep", "看短视频的坏处", "睡眠与情绪",
        "a text-free educational illustration with one large central subject and generous margins",
    )
    prompt = _build_local_prompt(request)
    assert "tired person in bed" in prompt
    assert "no brain network" in prompt


def test_local_seed_is_stable_and_prompt_specific():
    assert _local_seed("one") == _local_seed("one")
    assert _local_seed("one") != _local_seed("two")


def test_cooking_semantic_prompt_contract_distinguishes_stages_and_negatives():
    prep = SceneImageRequest(
        "prep", "dumplings", "Dough preparation",
        "flour, water, mixing dough, dough ball; no noodles, no soup, no finished dumplings",
    )
    prep_diag = _semantic_prompt_diagnostics(prep)
    assert prep_diag["stage"] == "dough_prep"
    assert prep_diag["requiredTerms"] == []
    assert prep_diag["forbiddenTerms"] == []

    wrapping = SceneImageRequest(
        "wrapping", "dumplings", "Wrap dumpling",
        "wrapper, filling, pleats; no rolling pin, no boiling pot",
    )
    wrapping_diag = _semantic_prompt_diagnostics(wrapping)
    assert wrapping_diag["stage"] == "wrapping"
    assert wrapping_diag["requiredTerms"] == []
    assert wrapping_diag["forbiddenTerms"] == []


def test_cooking_semantic_prompt_contract_rejects_generic_stage_prompt():
    request = SceneImageRequest("prep", "dumplings", "Dough preparation", "a nice food illustration")
    diagnostics = _semantic_prompt_diagnostics(request)
    assert diagnostics["stage"] == "dough_prep"
    assert diagnostics["requiredTerms"]


def test_wrappers_semantic_prompt_contract_requires_visible_actions():
    request = SceneImageRequest(
        "wrappers", "dumplings", "Make dumpling wrappers",
        "dough, rolling pin, wrapper; no noodles, no boiling pot, no finished meal",
    )
    diagnostics = _semantic_prompt_diagnostics(request)
    assert diagnostics["stage"] == "wrappers"
    assert set(diagnostics["requiredTerms"]) == {"hands", "knife", "cut"}

    complete = SceneImageRequest(
        "wrappers", "dumplings", "Make dumpling wrappers",
        "left-to-right three-stage action strip: hands rolling dough rope, knife cut dough pieces, rolling pin rolling dough into a round wrapper; no noodles, no boiling pot, no finished meal",
    )
    complete_diag = _semantic_prompt_diagnostics(complete)
    assert complete_diag["requiredTerms"] == []
    assert complete_diag["forbiddenTerms"] == []


def test_boiling_semantic_prompt_contract_requires_water_cooking_actions():
    request = SceneImageRequest(
        "boiling", "dumplings", "Boil dumplings",
        "boiling water, dumplings, floating, slotted spoon, cold water, submerged; no steamer, no steamed buns",
    )
    diagnostics = _semantic_prompt_diagnostics(request)
    assert diagnostics["stage"] == "boiling"
    assert diagnostics["requiredTerms"] == []
    assert diagnostics["forbiddenTerms"] == []

    generic = SceneImageRequest("boiling", "dumplings", "Boil dumplings", "dumplings in a steamer")
    generic_diag = _semantic_prompt_diagnostics(generic)
    assert "cold water" in generic_diag["requiredTerms"]
    assert "steamer" in generic_diag["forbiddenTerms"]


def test_boiling_action_panels_have_distinct_required_actions():
    drop = SceneImageRequest(
        "boil_drop", "boiling dumplings", "Drop dumplings into boiling water",
        "boiling water, dumplings, submerged, slotted spoon; no steamer, no steamed buns",
    )
    add_water = SceneImageRequest(
        "boil_add_water", "boiling dumplings", "Add cold water",
        "boiling water, dumplings, cold water, ladle; no steamer, no steamed buns",
    )
    float_scoop = SceneImageRequest(
        "boil_float_scoop", "boiling dumplings", "Floating dumplings are scooped out",
        "boiling water, dumplings, floating, slotted spoon; no steamer, no steamed buns",
    )
    assert _semantic_prompt_diagnostics(drop)["requiredTerms"] == []
    assert _semantic_prompt_diagnostics(add_water)["requiredTerms"] == []
    assert _semantic_prompt_diagnostics(float_scoop)["requiredTerms"] == []


def test_negative_comma_list_does_not_trigger_forbidden_term():
    request = SceneImageRequest(
        "boil_drop", "boiling dumplings", "Drop dumplings",
        "boiling water, dumplings, submerged, slotted spoon; no steamer, round buns, baozi, mantou, noodles",
    )
    assert _semantic_prompt_diagnostics(request)["forbiddenTerms"] == []


def _png(draw_fn=None) -> bytes:
    image = Image.new("RGB", (512, 512), "white")
    if draw_fn:
        draw_fn(ImageDraw.Draw(image))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_quality_gate_rejects_blank_image():
    result = inspect_generated_image(_png(), use_ocr=False)
    assert not result["ok"]
    assert "blank_or_flat" in result["errors"]


def test_action_board_composes_ordered_images_without_labels():
    first = _png(lambda draw: draw.rectangle((80, 80, 220, 220), outline="black", width=8))
    second = _png(lambda draw: draw.ellipse((280, 120, 430, 270), outline="black", width=8))
    board = Image.open(io.BytesIO(compose_action_board([first, second], columns=2))).convert("RGB")
    assert board.size == (984, 480)
    assert board.getpixel((0, 0)) == (255, 255, 255)
    assert board.getpixel((480, 10)) == (255, 255, 255)


def test_final_action_board_preserves_full_resolution_panels():
    first = _png(lambda draw: draw.rectangle((120, 120, 760, 760), outline="black", width=16))
    second = _png(lambda draw: draw.ellipse((220, 220, 800, 800), outline="black", width=16))
    board = Image.open(io.BytesIO(compose_action_board(
        [first, second], columns=2, panel_size=(1024, 1024), gap=32,
    ))).convert("RGB")
    assert board.size == (2080, 1024)


def test_quality_gate_accepts_centered_whiteboard_drawing():
    result = inspect_generated_image(
        _png(lambda draw: (draw.ellipse((130, 100, 380, 350), outline="black", width=8), draw.line((180, 390, 330, 390), fill="black", width=8))),
        use_ocr=False,
    )
    assert result["ok"], result


def test_quality_gate_rejects_border_signature():
    result = inspect_generated_image(
        _png(lambda draw: (draw.ellipse((140, 100, 370, 350), outline="black", width=8), draw.rectangle((445, 480, 505, 503), fill="black"))),
        use_ocr=False,
    )
    assert not result["ok"]
    assert "border_signature_or_watermark" in result["errors"]


def test_normalizer_restores_safe_whiteboard_margins():
    dirty = _png(lambda draw: (draw.ellipse((80, 80, 430, 430), outline="black", width=8), draw.rectangle((445, 480, 511, 511), fill="black")))
    normalized = normalize_whiteboard_image(dirty)
    result = inspect_generated_image(normalized, use_ocr=False)
    assert result["metrics"]["borderForegroundRatio"] == 0
