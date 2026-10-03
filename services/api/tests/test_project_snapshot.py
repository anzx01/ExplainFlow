import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.planner.project_snapshot import build_project_snapshot, fingerprint


def test_fingerprint_is_stable_and_order_independent():
    assert fingerprint({"b": 2, "a": 1}) == fingerprint({"a": 1, "b": 2})
    assert fingerprint({"a": 1}) != fingerprint({"a": 2})


def test_snapshot_tracks_scene_and_stage_dependencies():
    storyboard = {"topic": "demo", "scenes": [{"id": "scene-1", "narration": "hello"}]}
    snapshot = build_project_snapshot(
        storyboard,
        style_snapshot={"style": "marker"},
        render_config={"fps": 30},
    )
    assert snapshot["snapshotVersion"] == 2
    assert snapshot["sceneFingerprints"]["scene-1"]
    assert snapshot["stages"]["images"] != snapshot["stages"]["render"]
