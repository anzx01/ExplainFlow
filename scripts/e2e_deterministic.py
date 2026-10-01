"""Offline ExplainFlow E2E: contract -> codegen -> render -> QA."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx


API = "http://127.0.0.1:8000"
RENDER = "http://127.0.0.1:3001"


def storyboard() -> dict:
    return {
        "topic": f"Deterministic E2E {int(time.time())}",
        "total_duration_estimate": 14,
        "video_style": "whiteboard",
        "pen_style": "marker",
        "scenes": [{
            "id": "e2e_live_scene",
            "order": 1,
            "title": "Input to result",
            "narration": "First draw the input, then reveal the result.",
            "duration_estimate": 14,
            "learning_goal": "Show a transformation",
            "visual_mode": "trace",
            "render_strategy": "trace",
            "board_mode": "whiteboard",
            "visual_style": "teacher_whiteboard",
            "visual_anchor": "Input transforms into result",
            "canvasWidth": 1920,
            "canvasHeight": 1080,
            "annotation_plan": [
                {"type": "label", "label": "Input", "target": "input", "beat_id": "beat_0", "layer": "renderer"},
                {"type": "arrow", "label": "Transform", "target": "path", "beat_id": "beat_0", "layer": "renderer"},
                {"type": "label", "label": "Result", "target": "result", "beat_id": "beat_0", "layer": "renderer"},
            ],
            "animations": [
                {"type": "draw_box", "duration": 3, "content": "Input", "x": 260, "y": 260},
                {"type": "draw_arrow", "duration": 2, "content": "Transform", "x": 940, "y": 520},
                {"type": "draw_box", "duration": 3, "content": "Result", "x": 1080, "y": 260},
            ],
            "renderElements": [
                {"id": "input", "sequence": 1, "narrativeRole": "setup", "subtitle": "Input", "region": {"x": 260, "y": 260, "width": 680, "height": 520}, "reveal": {"startMs": 0, "durationMs": 5000, "protectedRegions": []}, "points": [[260, 260], [940, 780]], "source": "authored"},
                {"id": "result", "sequence": 2, "narrativeRole": "result", "subtitle": "Result", "region": {"x": 1080, "y": 260, "width": 680, "height": 520}, "reveal": {"startMs": 5000, "durationMs": 8500, "protectedRegions": []}, "points": [[1080, 260], [1760, 780]], "source": "authored"},
            ],
        }],
    }


def main() -> int:
    sb = storyboard()
    with httpx.Client(timeout=30) as client:
        validation = client.post(f"{API}/planner/validate-storyboard", json={"storyboard": sb, "fps": 30})
        validation.raise_for_status()
        if not validation.json().get("ok"):
            raise RuntimeError("storyboard contract rejected")
        code = client.post(f"{API}/planner/remotion-code", json={"storyboard": sb, "fps": 30, "width": 1920, "height": 1080, "subtitles_enabled": True})
        code.raise_for_status()
        start = client.post(f"{RENDER}/render", json={"storyboard": sb, "voice": "xiaoxiao", "subtitlesEnabled": True})
        start.raise_for_status()
        job_id = start.json()["jobId"]
        deadline = time.time() + 180
        while time.time() < deadline:
            job = client.get(f"{RENDER}/job/{job_id}")
            job.raise_for_status()
            payload = job.json()
            if payload.get("status") in {"done", "failed"}:
                break
            time.sleep(2)
    qa = payload.get("qa") or {}
    result = {"jobId": job_id, "status": payload.get("status"), "qaOk": qa.get("ok"), "duration": payload.get("actualDurationSeconds"), "fileSize": qa.get("fileSizeBytes"), "checks": {item["id"]: item["ok"] for item in qa.get("checks", [])}}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if payload.get("status") == "done" and qa.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
