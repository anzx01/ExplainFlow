import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.planner.fallback.tsx_template import _build_fallback_remotion_tsx
from src.planner.models import AnimationInstruction, Scene, Storyboard
from src.planner.render_contract import finalize_storyboard_contract


def test_fallback_tsx_contains_contract_masks_and_bound_draw_ops():
    scene = Scene(
        id="scene-mask",
        order=0,
        title="Mask",
        narration="Mask contract",
        duration_estimate=5,
        node_ids=[],
        animations=[
            AnimationInstruction(type="write_text", content="first"),
            AnimationInstruction(type="draw_arrow", content="second"),
        ],
    )
    storyboard = finalize_storyboard_contract(
        Storyboard(topic="mask", total_duration_estimate=5, scenes=[scene])
    )
    tsx, duration = _build_fallback_remotion_tsx(storyboard, 30, 1920, 1080)
    assert duration > 0
    assert "ContractMasks" in tsx
    assert "contractElementId" in tsx
    assert "laterRegions" in tsx
    assert "protectedRegions" in tsx
