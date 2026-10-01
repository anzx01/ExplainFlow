import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.render.engine_adapter import ENGINE_ROOT, engine_status, render_engine_preview_from_path


def test_engine_checkout_is_detected():
    status = engine_status()
    assert status["available"] is True
    assert Path(status["engineRoot"]) == ENGINE_ROOT


@pytest.mark.asyncio
async def test_engine_renders_svg_fixture(tmp_path: Path):
    fixture = ENGINE_ROOT / "tests" / "fixtures" / "apple.svg"
    output = tmp_path / "preview.mp4"
    await render_engine_preview_from_path(
        fixture,
        output,
        duration=1.2,
        fps=12,
        width=480,
        height=270,
        hand="procedural",
        stroke_detail="balanced",
        color_fill="contour-wipe",
        color_fill_scope="block",
    )
    assert output.exists()
    assert output.stat().st_size > 5_000
