#!/usr/bin/env python3
"""Deterministic ExplainFlow storyboard quality scoring."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "services" / "api"))

from src.planner.models import Storyboard
from src.planner.render_contract import validate_storyboard_contract


def score_storyboard(storyboard: Storyboard) -> dict:
    issues = validate_storyboard_contract(storyboard)
    errors = [item for item in issues if item.severity == "error"]
    warnings = [item for item in issues if item.severity == "warning"]
    scenes = storyboard.scenes
    complete = sum(bool(scene.learning_goal and scene.narration and scene.visual_beats and scene.render_elements) for scene in scenes)
    text_free = sum(
        not scene.image_description
        or "text-free" in scene.image_description.lower()
        or "no readable" in scene.image_description.lower()
        for scene in scenes
    )
    varied_modes = len({scene.visual_mode for scene in scenes if scene.visual_mode})
    scores = {
        "render_contract": max(0, 30 - len(errors) * 10 - len(warnings) * 2),
        "scene_completeness": round(25 * complete / max(1, len(scenes))),
        "text_control": round(15 * text_free / max(1, len(scenes))),
        "visual_mode_variety": min(10, varied_modes * 5),
        "timing": 10 if storyboard.total_duration_estimate > 0 and all(scene.duration_estimate >= 1 for scene in scenes) else 0,
        "publishable_structure": 10 if 1 <= len(scenes) <= 12 else 4,
    }
    return {
        "score": sum(scores.values()),
        "scores": scores,
        "issues": [item.__dict__ for item in issues],
        "sceneCount": len(scenes),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("storyboard", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-score", type=int, default=75)
    args = parser.parse_args()
    storyboard = Storyboard.model_validate_json(args.storyboard.read_text(encoding="utf-8"))
    result = score_storyboard(storyboard)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload)
    return 0 if result["score"] >= args.min_score else 1


if __name__ == "__main__":
    raise SystemExit(main())
