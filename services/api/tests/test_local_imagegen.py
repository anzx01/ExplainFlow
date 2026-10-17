import sys
import io
import asyncio
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.core.config import settings
from src.imagegen.service import SceneImageRequest, _build_local_prompt, _comfy_workflow, _flux_prompt_with_lora, _local_prompt, _local_seed, _semantic_prompt_diagnostics, compose_action_board, local_imagegen_status
from src.imagegen.quality import inspect_generated_image, normalize_whiteboard_image


def test_explicit_flux_retries_rejected_image_with_a_new_seed(monkeypatch):
    from src.imagegen import service

    monkeypatch.setattr(settings, "local_imagegen_max_attempts", 3)
    monkeypatch.setattr(service, "local_imagegen_status", lambda: {"modes": {"flux": {"missing": []}}})
    calls = []

    async def generate(prompt, *, quality, attempt):
        calls.append(attempt)
        return b"test-image"

    monkeypatch.setattr(service, "_call_local_flux", generate)
    monkeypatch.setattr(service, "normalize_whiteboard_image", lambda image: image)
    monkeypatch.setattr(service, "inspect_generated_image", lambda image: {"ok": len(calls) > 1, "errors": [] if len(calls) > 1 else ["possible_readable_text_or_signature"]})
    monkeypatch.setattr(service, "_asset_contract_metadata", lambda *args: {})
    image, diagnostics = asyncio.run(service.generate_scene_image_result(SceneImageRequest("retry", "food", "food", "a plate", image_mode="flux"), None))
    assert image
    assert calls == [0, 1]
    assert diagnostics["selectedAttempt"] == 2


def test_chinese_renderer_labels_are_not_sent_as_image_text():
    from src.imagegen.service import _normalize_image_description

    description = _normalize_image_description("画带皮五花肉，用短标签标出皮、肥肉、瘦肉; 右侧画冷水锅，旁边写冷水下锅; 右下角画短结论框。")
    assert "带皮五花肉" in description
    assert "冷水锅" in description
    assert "标出皮" not in description
    assert "写冷水" not in description
    assert "结论框" not in description


def test_explicit_flux_stops_after_configured_attempts(monkeypatch):
    from src.imagegen import service

    monkeypatch.setattr(settings, "local_imagegen_max_attempts", 2)
    monkeypatch.setattr(service, "local_imagegen_status", lambda: {"modes": {"flux": {"missing": []}}})
    calls = []

    async def generate(prompt, *, quality, attempt):
        calls.append(attempt)
        return b"test-image"

    monkeypatch.setattr(service, "_call_local_flux", generate)
    monkeypatch.setattr(service, "normalize_whiteboard_image", lambda image: image)
    monkeypatch.setattr(service, "inspect_generated_image", lambda image: {"ok": False, "errors": ["possible_readable_text_or_signature"]})
    monkeypatch.setattr(service, "_asset_contract_metadata", lambda *args: {})
    image, diagnostics = asyncio.run(service.generate_scene_image_result(SceneImageRequest("retry", "food", "food", "a plate", image_mode="flux"), None))
    assert image is None
    assert calls == [0, 1]
    assert diagnostics["selectedAttempt"] is None


def test_local_imagegen_status_reports_missing_components(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "imagegen_provider", "local")
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
    assert status["timeoutSeconds"] == settings.local_imagegen_timeout_s
    assert status["maxAttempts"] == settings.local_imagegen_max_attempts


def test_local_prompt_preserves_late_scene_requirements():
    prompt = "scene details " * 100 + "person lying on their side, glowing phone, spinning clock"
    result = _local_prompt(prompt + "Negative prompt: cloud-only exclusions")
    assert "person lying on their side, glowing phone, spinning clock" in result
    assert "cloud-only" not in result


def test_flux_lora_adds_trigger_and_cli_lora_tag(monkeypatch, tmp_path: Path):
    lora = tmp_path / "chalkboard-flux.safetensors"
    lora.write_bytes(b"lora")
    monkeypatch.setattr(settings, "local_imagegen_lora_dir", str(tmp_path))
    monkeypatch.setattr(settings, "local_imagegen_lora", lora.name)
    monkeypatch.setattr(settings, "local_imagegen_lora_strength", 0.65)
    monkeypatch.setattr(settings, "local_imagegen_lora_trigger", "ChalkBoardDrawing")

    prompt = _flux_prompt_with_lora("a text-free lesson drawing of a brain")

    assert prompt.startswith("ChalkBoardDrawing, <lora:chalkboard-flux:0.65>,")
    assert "a text-free lesson drawing of a brain" in prompt


def test_local_scene_prompt_preserves_authored_action_without_topic_override():
    description = "A person lying on their side, glowing smartphone, rapidly spinning clock. " + "detail " * 160 + "Blue light on pillow."
    request = SceneImageRequest("sleep", "short video harms", "sleep", description)
    prompt = _build_local_prompt(request)
    assert description in prompt
    assert "Blue light on pillow" in _local_prompt(prompt)
    assert "no brain, clock, or checklist" not in prompt
    assert "solid filled color shapes" in prompt


def test_local_seed_is_stable_and_prompt_specific():
    assert _local_seed("one") == _local_seed("one")
    assert _local_seed("one") != _local_seed("two")


def test_comfy_workflow_applies_configured_lora_and_trigger(monkeypatch, tmp_path: Path):
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(
        '{"1":{"class_type":"CheckpointLoaderSimple","inputs":{"ckpt_name":"__EXPLAINFLOW_CHECKPOINT__"}},'
        '"8":{"class_type":"LoraLoader","inputs":{"lora_name":"__EXPLAINFLOW_LORA__",'
        '"strength_model":"__EXPLAINFLOW_LORA_STRENGTH__","strength_clip":"__EXPLAINFLOW_LORA_STRENGTH__"}},'
        '"2":{"class_type":"CLIPTextEncode","inputs":{"text":"__EXPLAINFLOW_PROMPT__","clip":["8",1]}},'
        '"5":{"class_type":"KSampler","inputs":{"model":["8",0]}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "comfyui_workflow", str(workflow_path))
    monkeypatch.setattr(settings, "comfyui_checkpoint", "base.safetensors")
    monkeypatch.setattr(settings, "comfyui_lora", "doodle.safetensors")
    monkeypatch.setattr(settings, "comfyui_lora_strength", 0.8)
    monkeypatch.setattr(settings, "comfyui_lora_trigger", "doodle, crayons")

    workflow = _comfy_workflow("a hand drawn apple", "text", seed=1, width=512, height=512)

    assert workflow["8"]["inputs"]["lora_name"] == "doodle.safetensors"
    assert workflow["8"]["inputs"]["strength_model"] == 0.8
    assert workflow["2"]["inputs"]["text"].startswith("doodle, crayons,")
    assert workflow["5"]["inputs"]["model"] == ["8", 0]


def test_comfy_workflow_bypasses_lora_when_not_configured(monkeypatch, tmp_path: Path):
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(
        '{"1":{"class_type":"CheckpointLoaderSimple","inputs":{}},'
        '"8":{"class_type":"LoraLoader","inputs":{}},'
        '"2":{"class_type":"CLIPTextEncode","inputs":{"text":"__EXPLAINFLOW_PROMPT__","clip":["8",1]}},'
        '"5":{"class_type":"KSampler","inputs":{"model":["8",0]}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "comfyui_workflow", str(workflow_path))
    monkeypatch.setattr(settings, "comfyui_lora", "")
    workflow = _comfy_workflow("plain prompt", "", seed=1, width=512, height=512)

    assert "8" not in workflow
    assert workflow["2"]["inputs"]["clip"] == ["1", 1]
    assert workflow["5"]["inputs"]["model"] == ["1", 0]


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


def test_finished_dish_semantics_accept_chinese_storyboard_terms():
    request = SceneImageRequest(
        "scene_1", "mapo tofu", "\u6210\u54c1\u88c5\u76d8",
        "\u6210\u54c1\u9ebb\u5a46\u8c46\u8150\u88c5\u76d8\u4e0a\u684c\uff0c\u767d\u8272\u8c46\u8150\u5757\u3001\u7ea2\u6cb9\u548c\u8471\u82b1\u6e05\u6670\u53ef\u89c1",
    )
    diagnostics = _semantic_prompt_diagnostics(request)
    assert diagnostics["stage"] == "finished_dish"
    assert diagnostics["requiredTerms"] == []


def test_non_cooking_finished_scene_does_not_activate_cooking_contract():
    request = SceneImageRequest(
        "scene_1", "attention", "Finished workflow",
        "A finished workflow diagram with the final result highlighted",
    )
    diagnostics = _semantic_prompt_diagnostics(request)
    assert diagnostics == {"stage": None, "requiredTerms": [], "forbiddenTerms": []}


def test_chinese_cooking_actions_satisfy_stage_contracts():
    prep = SceneImageRequest("prep", "dumplings", "", "\u9762\u7c89\u52a0\u6c34\uff0c\u548c\u9762\u5e76\u63c9\u6210\u9762\u56e2")
    prep_diag = _semantic_prompt_diagnostics(prep)
    assert prep_diag["stage"] == "dough_prep"
    assert prep_diag["requiredTerms"] == []

    boil = SceneImageRequest("boiling", "dumplings", "", "\u997a\u5b50\u5728\u6cb8\u6c34\u4e2d\u6d6e\u8d77\uff0c\u7528\u6f0f\u52fa\u634e\u51fa\uff0c\u52a0\u51b7\u6c34")
    boil_diag = _semantic_prompt_diagnostics(boil)
    assert boil_diag["stage"] == "boiling"
    assert boil_diag["requiredTerms"] == []






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


def test_quality_gate_rejects_coherent_generated_labels(monkeypatch):
    from types import SimpleNamespace
    from src.imagegen import quality
    monkeypatch.setattr(quality.shutil, "which", lambda _: "tesseract")
    monkeypatch.setattr(quality.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="Sutenn attention fractentine"))
    result = inspect_generated_image(_png(lambda draw: draw.ellipse((130, 100, 380, 350), outline="black", width=8)))
    assert not result["ok"]
    assert "possible_readable_text_or_signature" in result["errors"]


def test_quality_gate_does_not_reject_isolated_doodle_ocr_noise(monkeypatch):
    from types import SimpleNamespace
    from src.imagegen import quality
    monkeypatch.setattr(quality.shutil, "which", lambda _: "tesseract")
    monkeypatch.setattr(quality.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="4 3) Yh"))
    result = inspect_generated_image(_png(lambda draw: draw.ellipse((130, 100, 380, 350), outline="black", width=8)))
    assert result["ok"]


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
