import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.planner.models import RenderElement, RenderRegion, RenderReveal, Scene, Storyboard
from src.planner.render_contract import (
    compile_scene_timeline,
    ensure_scene_contract_defaults,
    validate_scene_contract,
    validate_storyboard_contract,
)


def element(element_id: str, sequence: int, start: int, duration: int, x: int = 0) -> RenderElement:
    return RenderElement(
        id=element_id,
        sequence=sequence,
        region=RenderRegion(x=x, y=0, width=200, height=100),
        reveal=RenderReveal(startMs=start, durationMs=duration),
    )


def test_compile_scene_timeline_is_frame_deterministic():
    scene = Scene(
        id="scene-1",
        order=0,
        title="test",
        narration="test",
        duration_estimate=4,
        render_elements=[element("a", 1, 0, 1000)],
    )
    timeline = compile_scene_timeline(scene, fps=30)
    assert timeline[0]["startFrame"] == 0
    assert timeline[0]["endFrame"] == 30


def test_contract_rejects_overlap_and_out_of_bounds():
    scene = Scene(
        id="scene-1",
        order=0,
        title="test",
        narration="test",
        duration_estimate=2,
        render_elements=[element("a", 1, 0, 1200), element("b", 2, 900, 1200, x=300)],
    )
    issues = validate_scene_contract(scene, total_duration_ms=2000)
    assert {issue.code for issue in issues} >= {"timeline_overlap", "timeline_out_of_bounds"}


def test_defaults_create_regions_for_legacy_scene():
    scene = Scene(
        id="scene-legacy",
        order=0,
        title="legacy",
        narration="legacy",
        duration_estimate=5,
        animations=[{"type": "write_text", "content": "hello", "duration": 1}],
    )
    ensure_scene_contract_defaults(scene)
    assert len(scene.render_elements) == 1
    assert not validate_scene_contract(scene, total_duration_ms=5000)


def test_storyboard_warns_when_final_hold_is_short():
    scene = Scene(
        id="scene-1",
        order=0,
        title="test",
        narration="test",
        duration_estimate=2,
        render_elements=[element("a", 1, 0, 1700)],
    )
    issues = validate_storyboard_contract(Storyboard(topic="t", total_duration_estimate=2, scenes=[scene]))
    assert any(issue.code == "missing_hold" for issue in issues)


def test_explicit_parallel_group_allows_overlap():
    first = element("a", 1, 0, 1200)
    second = element("b", 2, 0, 900, x=300)
    first.parallel_group = "intro"
    second.parallel_group = "intro"
    scene = Scene(
        id="scene-parallel", order=0, title="test", narration="test",
        duration_estimate=2, render_elements=[first, second],
    )
    issues = validate_scene_contract(scene, total_duration_ms=2000)
    assert not any(issue.code == "timeline_overlap" for issue in issues)


def test_parallel_group_uses_latest_group_end_for_following_elements():
    first = element("a", 1, 0, 1200)
    second = element("b", 2, 0, 700, x=300)
    third = element("c", 3, 900, 500, x=600)
    first.parallel_group = "intro"
    second.parallel_group = "intro"
    scene = Scene(
        id="scene-parallel-end", order=0, title="test", narration="test",
        duration_estimate=2, render_elements=[first, second, third],
    )
    issues = validate_scene_contract(scene, total_duration_ms=2000)
    assert any(issue.code == "timeline_overlap" and issue.element_id == "c" for issue in issues)
