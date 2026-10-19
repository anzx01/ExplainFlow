import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.planner.models import Scene, Storyboard
from src.planner.storyboard_gen.narration_quality import audit_narration


def _scene(sid: str, title: str, narration: str, dur: float = 20.0, key_points=None) -> Scene:
    return Scene(
        id=sid,
        order=0,
        title=title,
        narration=narration,
        duration_estimate=dur,
        key_points=key_points or ["要点"],
    )


def _storyboard(scenes: list[Scene]) -> Storyboard:
    return Storyboard(topic="测试主题", total_duration_estimate=sum(s.duration_estimate for s in scenes), scenes=scenes)


def test_thin_narration_flagged():
    thin = [_scene(f"scene_{i}", f"场景{i}", "很短的旁白。", 20.0) for i in range(5)]
    audit = audit_narration(_storyboard(thin), 100)
    assert not audit["ok"]
    codes = {issue["code"] for issue in audit["issues"]}
    assert "narration_too_thin" in codes
    assert "scene_narration_thin" in codes


def test_dense_clean_narration_passes():
    good = _scene(
        "scene_0",
        "开场",
        "你有没有想过,同样一公里,电动车只要一毛钱,油车要七毛?" * 6,
        20.0,
        key_points=["电费vs油费对比"],
    )
    audit = audit_narration(_storyboard([good]), 20)
    assert audit["ok"], audit["issues"]


def test_announcer_and_image_description_flagged():
    scene = _scene("scene_1", "机制", "接下来我们看图中电池的结构。" + "电池放电时锂离子从负极穿过隔膜到达正极。" * 6, 20.0)
    audit = audit_narration(_storyboard([scene]), 20)
    codes = {issue["code"] for issue in audit["issues"]}
    assert "announcer_opening" in codes
    assert "describes_image" in codes


def test_mid_wrapup_scene_flagged():
    scenes = [
        _scene("scene_0", "钩子", "开场旁白。" * 20, 15.0),
        _scene("scene_1", "流程总览", "中途总览旁白。" * 20, 15.0),
        _scene("scene_2", "总结", "结尾总结旁白。" * 20, 15.0),
    ]
    audit = audit_narration(_storyboard(scenes), 45)
    codes = {issue["code"] for issue in audit["issues"]}
    assert "mid_wrapup_scene" in codes


def test_near_duplicate_scenes_flagged():
    body = "电流通过灯丝,灯丝发热发光,这就是白炽灯的原理。" * 6
    scenes = [
        _scene("scene_0", "A", body, 20.0),
        _scene("scene_1", "B", body, 20.0),
    ]
    audit = audit_narration(_storyboard(scenes), 40)
    codes = {issue["code"] for issue in audit["issues"]}
    assert "near_duplicate_narration" in codes
