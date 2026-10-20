import asyncio
import io
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parents[1]))
from src.imagegen import service
from src.imagegen.quality import normalize_whiteboard_image


@pytest.mark.parametrize("description", [
    "A table tennis player rotating the waist and hitting a ball with a paddle.",
    "A cook holding a wrapper in one hand and pinching its edge with the other.",
    "A listener comparing two orchestral phrases while following a conductor.",
])
@pytest.mark.parametrize("mode", ["flux", "sd15"])
def test_subject_actions_are_not_negated_by_style_rules(description, mode):
    req = service.SceneImageRequest("subject", "lesson", "action", description, image_mode=mode)
    prompt = service._build_prompt(req, description if mode == "sd15" else None)
    assert description.rstrip(".") in prompt
    assert "no people" not in prompt
    assert "no text" in prompt or "no readable words" in prompt


@pytest.mark.parametrize("provider,expected_condensations", [("local", 0), ("ark", 0), ("comfyui", 1)])
def test_default_image_mode_preserves_full_script_except_for_clip(monkeypatch, provider, expected_condensations):
    condensed = []
    prompts = []

    async def condense(req):
        condensed.append(req)
        return "a player hitting a ball"

    async def generate(prompt, *args, **kwargs):
        prompts.append(prompt)
        return b"image"

    monkeypatch.setattr(service, "effective_imagegen_provider", lambda: provider)
    monkeypatch.setattr(service, "_condense_subject_for_clip", condense)
    for name in ("_call_local_flux", "_call_seedream", "_call_comfyui"):
        monkeypatch.setattr(service, name, generate)
    monkeypatch.setattr(service, "normalize_whiteboard_image", lambda value: value)
    monkeypatch.setattr(service, "inspect_generated_image", lambda value: {"ok": True, "errors": []})
    monkeypatch.setattr(service, "_asset_contract_metadata", lambda *args: {})
    req = service.SceneImageRequest("action", "table tennis", "forehand", "A player pushes from the right foot and rotates the waist before hitting the ball.", image_mode="default")
    image, diagnostics = asyncio.run(service.generate_scene_image_result(req, None))
    assert image and diagnostics["ok"]
    assert len(condensed) == expected_condensations
    assert len(prompts) == 1
    if not expected_condensations:
        assert req.image_description in prompts[0]


def test_normalization_preserves_required_parts_at_every_edge():
    source = Image.new("RGB", (512, 512), "white")
    draw = ImageDraw.Draw(source)
    draw.rectangle((110, 120, 400, 390), fill="black")
    draw.rectangle((0, 0, 30, 45), fill="red")
    draw.rectangle((465, 465, 510, 511), fill="blue")
    encoded = io.BytesIO()
    source.save(encoded, format="PNG")
    normalized = Image.open(io.BytesIO(normalize_whiteboard_image(encoded.getvalue())))
    pixels = np.asarray(normalized)
    assert normalized.size == source.size
    assert ((pixels[:, :, 0] > 200) & (pixels[:, :, 1] < 50)).sum() > 300
    assert ((pixels[:, :, 2] > 200) & (pixels[:, :, 0] < 50)).sum() > 300
    assert (pixels[:20] == 255).all()
    assert (pixels[-20:] == 255).all()


def test_transparent_art_is_composited_on_white_before_normalization():
    source = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    ImageDraw.Draw(source).ellipse((150, 150, 360, 360), fill="red")
    encoded = io.BytesIO()
    source.save(encoded, format="PNG")
    pixels = np.asarray(Image.open(io.BytesIO(normalize_whiteboard_image(encoded.getvalue()))))
    assert (pixels[30, 30] == 255).all()
    assert pixels[256, 256, 0] > 200
