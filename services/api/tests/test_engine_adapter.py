import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.render.engine_adapter import HAND_ASSET, RENDER_SCRIPT, engine_status, render_engine_preview_from_path


def test_nikola_stroke_story_checkout_is_detected():
    status = engine_status()
    assert status["available"] is True
    assert Path(status["engineRoot"]).name == "srt-whiteboard-animation"
    assert RENDER_SCRIPT.is_file() and HAND_ASSET.is_file()


@pytest.mark.asyncio
async def test_nikola_renderer_renders_raster_fixture(tmp_path: Path):
    image = Image.new("RGB", (320, 180), "#f6f1e3")
    ImageDraw.Draw(image).ellipse((90, 35, 230, 145), outline="#202020", width=8)
    fixture = tmp_path / "apple.png"
    image.save(fixture)
    output = tmp_path / "preview.mp4"
    await render_engine_preview_from_path(fixture, output, duration=1.5, fps=12, width=480, height=270, hand="procedural", stroke_detail="balanced", color_fill="contour-wipe", color_fill_scope="block")
    assert output.exists() and output.stat().st_size > 1_000
