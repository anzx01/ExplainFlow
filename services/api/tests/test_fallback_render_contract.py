import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.planner.fallback.spec import _build_fallback_scene_spec
from src.planner.fallback.tsx_template import _build_fallback_remotion_tsx
from src.planner.fallback.draw_ops import _retime_draw_ops_to_audio_segments, _retime_draw_ops_to_subtitle_cues
from src.planner.models import AnimationInstruction, AssetBounds, RenderElement, RenderRegion, RenderReveal, Scene, SceneAssetContract, Storyboard
from src.planner.render_contract import finalize_storyboard_contract, validate_scene_contract


def test_fallback_tsx_contains_contract_masks_and_bound_draw_ops():
    from src.planner.remotion_codegen.validator import _validate_handwritten_whiteboard_style
    from src.planner.remotion_codegen.tsx_validator import _validate_generated_tsx
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
    _validate_handwritten_whiteboard_style(tsx)
    _validate_generated_tsx(tsx)
    with pytest.raises(ValueError, match="HAND_WIDTH >= 180"):
        _validate_generated_tsx(tsx.replace("const HAND_WIDTH = 180;", "const HAND_WIDTH = 160;"))
    assert "ContractMasks" in tsx
    assert "contractElementId" in tsx
    assert "laterRegions" in tsx
    assert "protectedRegions" in tsx
    assert "showHand && pen.visible" in tsx
    assert "showHand && !scene.rasterReveal" not in tsx
    assert "opacity={0.28}" not in tsx
    assert "const PEN_TIP_X = 10;" in tsx


def test_draw_ops_fill_the_spoken_audio_window_without_preroll_or_hold():
    draw_ops = [
        {"id": "first", "kind": "path", "startFrame": 0, "endFrame": 4, "points": []},
        {"id": "second", "kind": "path", "startFrame": 5, "endFrame": 9, "points": []},
    ]
    segments = [{
        "id": "beat_0", "startFrame": 0, "endFrame": 100,
        "audioStartFrame": 20, "audioEndFrame": 80,
    }]

    _retime_draw_ops_to_audio_segments(draw_ops, segments, 100)

    assert draw_ops[0]["beatId"] == draw_ops[1]["beatId"] == "beat_0"
    assert draw_ops[0]["startFrame"] == 20
    assert draw_ops[-1]["endFrame"] == 80


def test_draw_ops_cover_every_spoken_subtitle_cue():
    draw_ops = [
        {"id": f"path-{index}", "kind": "path", "beatId": f"cue_{index // 2}", "startFrame": index, "endFrame": index + 1, "points": []}
        for index in range(6)
    ]
    cues = [
        {"text": "第一句", "startFrame": 0, "endFrame": 60},
        {"text": "第二句", "startFrame": 60, "endFrame": 120},
        {"text": "第三句", "startFrame": 120, "endFrame": 180},
    ]

    assert _retime_draw_ops_to_subtitle_cues(draw_ops, cues, 180)
    for index, cue in enumerate(cues):
        cue_ops = [op for op in draw_ops if op["beatId"] == f"cue_{index}"]
        assert cue_ops
        assert min(op["startFrame"] for op in cue_ops) == cue["startFrame"]
        assert max(op["endFrame"] for op in cue_ops) == cue["endFrame"]


def test_spoken_recap_writes_the_actual_cues_without_a_static_overlay_or_audio_shift():
    cues = [
        {"text": "保护注意力。", "startFrame": 0, "endFrame": 120},
        {"text": "保证睡眠。", "startFrame": 120, "endFrame": 240},
    ]
    scene = Scene(
        id="recap", order=0, title="总结", narration="保护注意力。保证睡眠。",
        duration_estimate=8, summaryPoints=["注意力", "睡眠"], subtitleCues=cues,
        renderElements=[RenderElement(id="legacy", sequence=1,
                                     region=RenderRegion(x=0, y=0, width=960, height=540),
                                     reveal=RenderReveal(startMs=1000, durationMs=3000))],
        audioSegments=[{"id": "continuous", "startFrame": 0, "endFrame": 240,
                        "audioDurationFrames": 240, "audioUrl": "recap.wav"}],
    )
    spec = _build_fallback_scene_spec(scene, 0, 30, 960, 540)

    assert spec["summaryPoints"] == []
    assert [text["text"] for text in spec["texts"]] == [cue["text"] for cue in cues]
    assert spec["duration"] == 240
    assert spec["audioSegments"][0]["audioStartFrame"] == 0
    assert spec["drawOps"][0]["startFrame"] == 0
    assert spec["drawOps"][-1]["endFrame"] == 240


def test_unbound_paths_are_not_assumed_to_match_spoken_cues():
    ops = [{"id": str(i), "startFrame": i, "endFrame": i + 1} for i in range(10)]
    original = [dict(op) for op in ops]
    assert not _retime_draw_ops_to_subtitle_cues(ops, [{"text": "把手机放远", "startFrame": 0, "endFrame": 100}], 100)
    assert ops == original


def test_subtitles_preserve_already_spoken_directions_and_technical_terms():
    from src.planner.storyboard_gen.normalizer import _subtitle_text, _clean_narration_text
    spoken = "先看左边的手机。现在我们看 attention，再写 V_G。"
    assert _subtitle_text(spoken) == spoken
    directions = "先看左边，汤汁还是稀的。再看右边，浓汁裹住肉。"
    assert _clean_narration_text(directions) == directions


def test_render_rejects_missing_words_and_overlapping_subtitle_cues():
    import pytest
    scene = Scene(id="invalid-captions", order=0, title="字幕", narration="先看手机。再做练习。",
                  duration_estimate=8,
                  audioSegments=[{"id": "speech", "startFrame": 0, "endFrame": 240,
                                  "subtitleText": "先看手机。再做练习。"}],
                  subtitleCues=[{"text": "先看手机。", "startFrame": 0, "endFrame": 240}])
    with pytest.raises(ValueError, match="omit or change"):
        _build_fallback_scene_spec(scene, 0, 30, 960, 540)
    scene.subtitleCues = [{"text": "先看手机。", "startFrame": 0, "endFrame": 150},
                          {"text": "再做练习。", "startFrame": 100, "endFrame": 240}]
    with pytest.raises(ValueError, match="overlapping"):
        _build_fallback_scene_spec(scene, 0, 30, 960, 540)


def test_semantic_contract_uses_spoken_cue_not_estimated_reveal_time():
    from types import SimpleNamespace
    from src.planner.fallback.scene_builder_main import _apply_render_contract
    element = RenderElement(id="phone", sequence=1, subtitle="把手机放远。",
                            region=RenderRegion(x=0, y=0, width=960, height=540),
                            reveal=RenderReveal(startMs=0, durationMs=8000))
    builder = SimpleNamespace(
        scene=SimpleNamespace(render_elements=[element], duration_estimate=8, canvas_width=960, canvas_height=540),
        duration=240, fps=30, width=960, height=540, raster_reveal_spec=None,
        subtitle_cues=[{"text": "先完成任务。", "startFrame": 0, "endFrame": 180},
                       {"text": "把手机放远。", "startFrame": 180, "endFrame": 240}],
        draw_ops=[{"id": "phone-path", "kind": "path", "points": []}],
    )
    specs = _apply_render_contract(builder)
    assert specs[0]["startFrame"] == builder.draw_ops[0]["startFrame"] == 180
    assert specs[0]["endFrame"] == builder.draw_ops[0]["endFrame"] == 240


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
        assert ink["endFrame"] <= color["startFrame"]


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
        assert ink["endFrame"] <= color["startFrame"]
        paired_spans.append(ink["endFrame"] - ink["startFrame"])
    assert min(paired_spans) > 0


def test_generated_text_rows_never_clip_or_retime_reference_artwork():
    scene = Scene(
        id="image-not-text", order=0, title="选肉", narration="挑选五花肉。",
        duration_estimate=10,
        animations=[AnimationInstruction(type="whiteboard_draw", content="画五花肉")],
        referenceImageAsset="generated/job/ink.png",
        rasterReveal={"imageWidth": 512, "imageHeight": 512,
                      "inkAsset": "generated/job/ink.png", "colorAsset": "generated/job/color.png",
                      "strokes": [{"points": [{"x": .2, "y": .3}, {"x": .8, "y": .8}]}]},
    )
    finalize_storyboard_contract(Storyboard(topic="选肉", total_duration_estimate=10, scenes=[scene]))
    assert scene.render_elements and all(item.source == "generated" for item in scene.render_elements)
    spec = _build_fallback_scene_spec(scene, 0, 24, 960, 540)
    assert spec["renderElements"] == []
    assert all(not op.get("contractElementId") for op in spec["drawOps"])
    assert spec["rasterReveal"]["strokes"]
    assert spec["keywords"] == []


def test_two_point_paint_sweep_is_split_into_actual_spoken_object_windows():
    scene = Scene(
        id="comparison", order=0, title="收汁对照", narration="先看稀汤。再看浓汁。", duration_estimate=10,
        canvasWidth=960, canvasHeight=540,
        subtitleCues=[{"text": "先看稀汤。", "startFrame": 0, "endFrame": 100},
                      {"text": "再看浓汁。", "startFrame": 100, "endFrame": 240}],
        renderElements=[RenderElement(id=name, sequence=index+1, subtitle=text,
                        region=RenderRegion(x=index*480,y=0,width=480,height=540),
                        reveal=RenderReveal(startMs=index*5000,durationMs=5000))
                        for index,(name,text) in enumerate([("thin","先看稀汤。"),("thick","再看浓汁。")])],
        referenceImageAsset="ink.png",
        rasterReveal={"imageWidth":512,"imageHeight":512,"inkAsset":"ink.png","colorAsset":"color.png",
                      "strokes":[{"points":[{"x":.1,"y":.5},{"x":.9,"y":.5}]}]},
    )
    spec = _build_fallback_scene_spec(scene,0,24,960,540)
    ops = {op["id"]:op for op in spec["drawOps"]}
    paths = [ops[stroke["opId"]] for stroke in spec["rasterReveal"]["strokes"]]
    assert {op["contractElementId"] for op in paths} == {"thin","thick"}
    assert all(op["endFrame"]<=100 for op in paths if op["contractElementId"]=="thin")
    assert all(op["startFrame"]>=100 for op in paths if op["contractElementId"]=="thick")
    colors = [ops[stroke["colorOpId"]] for stroke in spec["rasterReveal"]["strokes"]]
    first_thick = min(op["startFrame"] for op in paths if op["contractElementId"]=="thick")
    first_color = min(op["startFrame"] for op in colors if op["contractElementId"]=="thick")
    assert first_color-first_thick<10


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
    assert "const HAND_WIDTH = 180" in tsx
    assert 'staticFile("hand-real-pen.png")' in tsx
    assert "const PEN_TIP_X = 10" in tsx
    assert "const PEN_TIP_Y = 48" in tsx
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


@pytest.mark.parametrize("width,height", [(1920, 1080), (960, 540)])
def test_trace_labels_are_readable_and_close_to_portrait_artwork(width, height):
    labels = ["先站稳", "再转腰"]
    scene = Scene(
        id="labels", order=0, title="动作", narration="先站稳。再转腰。", duration_estimate=10,
        referenceImageAsset="ink.png",
        rasterReveal={"imageWidth": 512, "imageHeight": 512, "inkAsset": "ink.png",
                      "strokes": [{"points": [{"x": .2, "y": .2}, {"x": .8, "y": .8}]}]},
        annotation_plan=[{"type": "side_label", "label": label, "target": "主体"} for label in labels],
    )
    spec = _build_fallback_scene_spec(scene, 0, 24, width, height)
    notes = [item for item in spec["texts"] if item["text"] in labels]
    assert len(notes) == 2
    art = spec["rasterReveal"]
    assert art["width"] == pytest.approx(art["height"], abs=1)
    left, right = notes
    for note in notes:
        assert note["fontSize"] >= height * .047
        assert 0 <= note["x"] <= width - note["maxWidth"]
    assert 0 <= art["x"] - left["x"] - left["maxWidth"] <= width * .03
    assert 0 <= right["x"] - art["x"] - art["width"] <= width * .03


def test_direct_route_annotation_renders_without_stretching_the_artwork():
    scene = Scene(
        id="route", order=0, title="发力路线", narration="从脚到手。", duration_estimate=10,
        referenceImageAsset="master.png",
        rasterReveal={"imageWidth": 512, "imageHeight": 512, "renderMode": "direct"},
        annotation_plan=[{"type": "route_trace", "label": "从脚到手", "target": "主体"}],
    )
    spec = _build_fallback_scene_spec(scene, 0, 24, 1920, 1080)
    assert any(stroke["role"] == "annotation_route_trace" for stroke in spec["strokes"])
    assert spec["rasterReveal"]["fit"] == "contain"
    tsx, _ = _build_fallback_remotion_tsx(Storyboard(topic="route", total_duration_estimate=10, scenes=[scene]), 24, 1920, 1080)
    overlay = tsx.split("const RasterFinalOverlay", 1)[1].split("const AnimeDoodle", 1)[0]
    assert 'objectFit: reveal.fit ?? "fill"' in overlay
