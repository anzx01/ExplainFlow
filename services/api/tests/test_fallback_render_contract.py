import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.planner.fallback.spec import _build_fallback_scene_spec
from src.planner.fallback.tsx_template import _build_fallback_remotion_tsx
from src.planner.models import AnimationInstruction, AssetBounds, RenderElement, RenderRegion, RenderReveal, Scene, SceneAssetContract, Storyboard
from src.planner.render_contract import finalize_storyboard_contract, validate_scene_contract


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


def test_raster_trace_partitions_regions_and_schedules_ink_then_color():
    scene = Scene(
        id="scene-raster",
        order=0,
        title="Raster",
        narration="Raster contract",
        duration_estimate=10,
        animations=[AnimationInstruction(type="whiteboard_draw", content="reference")],
        renderElements=[
            RenderElement(
                id="left", sequence=1,
                region=RenderRegion(x=0, y=0, width=960, height=1080),
                reveal=RenderReveal(startMs=0, durationMs=4000),
            ),
            RenderElement(
                id="right", sequence=2,
                region=RenderRegion(x=960, y=0, width=960, height=1080),
                reveal=RenderReveal(startMs=4200, durationMs=4800),
            ),
        ],
        referenceImageAsset="generated/job/scene.png",
        rasterReveal={
            "asset": "generated/job/scene.png",
            "inkAsset": "generated/job/scene.png",
            "colorAsset": "generated/job/scene-color.png",
            "imageWidth": 512,
            "imageHeight": 512,
            "strokes": [
                {"points": [{"x": 0.1, "y": 0.2}, {"x": 0.2, "y": 0.3}, {"x": 0.3, "y": 0.4}], "revealWidth": 0.03},
                {"points": [{"x": 0.7, "y": 0.2}, {"x": 0.8, "y": 0.3}, {"x": 0.9, "y": 0.4}], "revealWidth": 0.03},
            ],
        },
    )

    spec = _build_fallback_scene_spec(scene, 0, 30, 1920, 1080)
    raster_strokes = spec["rasterReveal"]["strokes"]
    ops = {op["id"]: op for op in spec["drawOps"]}

    assert all(stroke.get("colorOpId") for stroke in raster_strokes)
    assert ops[raster_strokes[0]["opId"]]["contractElementId"] == "left"
    assert ops[raster_strokes[1]["opId"]]["contractElementId"] == "right"
    for stroke in raster_strokes:
        ink = ops[stroke["opId"]]
        color = ops[stroke["colorOpId"]]
        assert ink["phase"] == "ink"
        assert color["phase"] == "color"
        assert ink["startFrame"] == color["startFrame"]
        assert ink["endFrame"] == color["endFrame"]


def test_raster_trace_keeps_all_strokes_and_pairs_color_with_pen_timing():
    strokes = [
        {
            "points": [
                {"x": 0.05 + (index % 10) * 0.09, "y": 0.05 + (index // 10) * 0.14},
                {"x": 0.08 + (index % 10) * 0.09, "y": 0.08 + (index // 10) * 0.14},
            ],
            "revealWidth": 0.03,
        }
        for index in range(60)
    ]
    scene = Scene(
        id="scene-raster-smooth", order=0, title="Raster", narration="Raster",
        duration_estimate=10,
        animations=[AnimationInstruction(type="whiteboard_draw", content="reference")],
        referenceImageAsset="generated/job/scene.png",
        rasterReveal={
            "asset": "generated/job/scene.png", "inkAsset": "generated/job/scene-ink.png",
            "colorAsset": "generated/job/scene-color.png", "imageWidth": 512,
            "imageHeight": 512, "strokes": strokes,
        },
    )
    spec = _build_fallback_scene_spec(scene, 0, 30, 1920, 1080)
    raster_paths = spec["rasterReveal"]["strokes"]
    ops = {op["id"]: op for op in spec["drawOps"]}

    assert len(raster_paths) == 60
    paired_spans = []
    for stroke in raster_paths:
        ink = ops[stroke["opId"]]
        color = ops[stroke["colorOpId"]]
        assert ink["startFrame"] == color["startFrame"]
        assert ink["endFrame"] == color["endFrame"]
        paired_spans.append(ink["endFrame"] - ink["startFrame"])
    assert min(paired_spans) >= 1


def test_raster_template_applies_contract_masks_and_cropped_hand_anchor():
    scene = Scene(
        id="scene-raster-template", order=0, title="Raster", narration="Raster",
        duration_estimate=8,
        animations=[AnimationInstruction(type="whiteboard_draw", content="reference")],
        referenceImageAsset="generated/job/scene.png",
        rasterReveal={
            "asset": "generated/job/scene.png", "inkAsset": "generated/job/scene.png",
            "colorAsset": "generated/job/scene-color.png", "imageWidth": 512, "imageHeight": 512,
            "strokes": [{"points": [{"x": 0.2, "y": 0.2}, {"x": 0.8, "y": 0.8}], "revealWidth": 0.03}],
        },
    )
    storyboard = finalize_storyboard_contract(Storyboard(topic="raster", total_duration_estimate=8, scenes=[scene]))
    tsx, _ = _build_fallback_remotion_tsx(storyboard, 30, 1920, 1080)

    assert "colorOpId" in tsx
    assert "mask={maskIdForOp(scene, op)" in tsx
    assert "opacity={1}" in tsx
    assert "finalCoverageOpacity" not in tsx
    color_mask = tsx.split("const RasterColorMaskStroke", 1)[1].split("const RasterRevealImage", 1)[0]
    assert "strokeWidth={Math.max(4, Math.min(spec.revealWidth, length * 0.6))}" in color_mask
    assert "spec.revealWidth * 4.5" not in color_mask
    assert "const HAND_WIDTH = 282" in tsx
    assert 'staticFile("hand-real-pen.png")' in tsx
    assert "const PEN_TIP_X = 198" in tsx
    assert "const PEN_TIP_Y = 197" in tsx
    assert "if (frame <= op.startFrame) return null;" in tsx
    assert "const colorStartFrame = spec.colorOpId ? op.startFrame : (spec.colorStartFrame ?? fallbackStart);" in tsx


def test_trace_raster_final_overlay_waits_for_all_strokes_and_uses_transparent_layers():
    scene = Scene(
        id="scene-trace-overlay", order=0, title="Trace", narration="Trace",
        duration_estimate=5,
        animations=[AnimationInstruction(type="whiteboard_draw", content="reference")],
        referenceImageAsset="generated/job/scene.png",
        rasterReveal={
            "asset": "generated/job/scene.png", "inkAsset": "generated/job/scene-ink.png",
            "colorAsset": "generated/job/scene-color.png", "renderMode": "trace",
            "imageWidth": 512, "imageHeight": 512,
            "strokes": [{"points": [{"x": 0.2, "y": 0.2}, {"x": 0.8, "y": 0.8}], "revealWidth": 0.03}],
        },
    )
    storyboard = finalize_storyboard_contract(Storyboard(topic="trace", total_duration_estimate=5, scenes=[scene]))
    tsx, _ = _build_fallback_remotion_tsx(storyboard, 30, 1920, 1080)

    overlay = tsx.split("const RasterFinalOverlay", 1)[1].split("const AnimeDoodle", 1)[0]
    assert 'const direct = reveal.renderMode === "direct";' in overlay
    assert "inkOp?.endFrame ?? 0" in overlay
    assert "colorOp?.endFrame ?? 0" in overlay
    assert "[reveal.inkAsset!, reveal.colorAsset!]" in overlay
    assert "[finishFrame, finishFrame + (direct ? 10 : 8)]" in overlay
    assert "if (frame <= finishFrame || opacity <= 0) return null;" in overlay
    assert "zIndex: 11" in overlay
    assert "mask={`url(#${maskId})`}" in tsx


def test_trace_asset_contract_requires_derivatives_and_preserves_metadata():
    scene = Scene(
        id="scene-assets", order=0, title="Assets", narration="Assets", duration_estimate=5,
        assetContract=SceneAssetContract(
            mode="trace", masterAsset="master.png", inkAsset="ink.png", colorAsset="color.png",
            width=1024, height=1024, sourceHash="abc", promptHash="def",
            observedContentBounds=AssetBounds(x=10, y=20, width=900, height=800),
            layers=["ink", "color"],
        ),
    )
    assert validate_scene_contract(scene) == []
    assert scene.asset_contract is not None
    assert scene.asset_contract.source_hash == "abc"


def test_full_asset_contract_rejects_extra_layers_and_out_of_bounds_content():
    scene = Scene(
        id="scene-full", order=0, title="Full", narration="Full", duration_estimate=5,
        assetContract=SceneAssetContract(
            mode="full", colorAsset="master.png", width=800, height=600,
            observedContentBounds=AssetBounds(x=700, y=0, width=200, height=100),
            layers=["ink", "color"],
        ),
    )
    codes = {issue.code for issue in validate_scene_contract(scene)}
    assert "full_asset_layers_invalid" in codes
    assert "asset_bounds_out_of_bounds" in codes


def test_storyboard_style_and_character_locks_get_stable_fingerprints():
    storyboard = Storyboard(
        topic="locks", total_duration_estimate=5, scenes=[],
        styleLock="marker on whiteboard", characterLock="same teacher and student",
    )
    finalized = finalize_storyboard_contract(storyboard)
    assert finalized.style_fingerprint == "78d481b57dae9462"
    assert finalized.character_fingerprint == "e512935684770e4f"
