"""Deterministic multi-scene local-image ExplainFlow E2E."""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import httpx

API = "http://127.0.0.1:8000"
RENDER = "http://127.0.0.1:3001"
OUTPUT = Path(__file__).parents[1] / "outputs" / "e2e-local-full"


def _scene(scene_id: str, order: int, title: str, narration: str, description: str) -> dict:
    return {
        "id": scene_id, "order": order, "title": title, "narration": narration,
        "duration_estimate": 10, "learning_goal": title,
        "image_description": description, "visual_mode": "direct_reference",
        "render_strategy": "direct", "visual_complexity": "reference",
        "board_mode": "reference", "hand_usage": "annotate",
        "video_style": "whiteboard", "visual_style": "marketing_doodle",
        "visual_anchor": title, "canvasWidth": 1920, "canvasHeight": 1080,
        "visual_beats": [{"id": "beat_0", "draw_intent": title, "narration": narration, "required_labels": [title], "duration_estimate": 9}],
        "annotation_plan": [
            {"type": "label", "label": "输入", "target": "subject", "beat_id": "beat_0", "layer": "renderer"},
            {"type": "arrow", "label": "变化", "target": "motion", "beat_id": "beat_0", "layer": "renderer"},
            {"type": "highlight", "label": "结果", "target": "result", "beat_id": "beat_0", "layer": "renderer"},
        ],
        "animations": [{"type": "whiteboard_draw", "duration": 7, "content": title}],
        "renderElements": [{
            "id": f"{scene_id}-art", "sequence": 1, "narrativeRole": "content",
            "subtitle": narration, "region": {"x": 180, "y": 100, "width": 1560, "height": 820},
            "reveal": {"startMs": 0, "durationMs": 8000, "protectedRegions": []},
            "points": [[180, 500], [1740, 500]], "source": "authored",
        }],
    }


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    storyboard = {
        "topic": "Local full E2E", "total_duration_estimate": 20,
        "video_style": "whiteboard", "pen_style": "marker",
        "scenes": [
            _scene("idea", 1, "产生想法", "先看见灯泡和齿轮代表想法形成。", "one large light bulb meshing with two gears, bold hand-drawn whiteboard illustration, yellow and blue accents, generous blank margins, text-free artwork, no logo, no watermark"),
            _scene("result", 2, "形成结果", "随后齿轮推动箭头，形成清晰结果。", "three simple gears driving one upward arrow toward a bright target, bold hand-drawn whiteboard illustration, green and yellow accents, generous blank margins, text-free artwork, no logo, no watermark"),
        ],
    }
    report: dict = {"stages": {}}
    with httpx.Client(timeout=420) as client:
        validation = client.post(f"{API}/planner/validate-storyboard", json={"storyboard": storyboard, "fps": 30})
        validation.raise_for_status()
        report["stages"]["contract"] = validation.json()["ok"]
        image_response = client.post(f"{API}/imagegen/scenes", json={"scenes": [{
            "scene_id": scene["id"], "topic": storyboard["topic"], "title": scene["title"],
            "image_description": scene["image_description"], "board_mode": scene["board_mode"],
            "hand_usage": scene["hand_usage"], "video_style": scene["video_style"],
            "visual_style": scene["visual_style"], "pen_style": "marker", "quality": "preview",
        } for scene in storyboard["scenes"]]})
        image_response.raise_for_status()
        image_payload = image_response.json()
        report["imageDiagnostics"] = image_payload["diagnostics"]
        for scene in storyboard["scenes"]:
            encoded = image_payload["images"].get(scene["id"])
            if not encoded:
                raise RuntimeError(f"local image rejected for {scene['id']}: {image_payload['diagnostics'].get(scene['id'])}")
            data = base64.b64decode(encoded)
            (OUTPUT / f"{scene['id']}.png").write_bytes(data)
            scene["image_url"] = f"data:image/png;base64,{encoded}"
        report["stages"]["localImages"] = True
        code = client.post(f"{API}/planner/remotion-code", json={"storyboard": storyboard, "fps": 30, "width": 1920, "height": 1080, "subtitles_enabled": True})
        code.raise_for_status()
        report["stages"]["codegen"] = len(code.json()["tsx"]) > 1000
        start = client.post(f"{RENDER}/render", json={"storyboard": storyboard, "voice": "xiaoxiao", "subtitlesEnabled": True})
        start.raise_for_status()
        job_id = start.json()["jobId"]
        deadline = time.time() + 300
        while time.time() < deadline:
            job = client.get(f"{RENDER}/job/{job_id}")
            job.raise_for_status()
            status = job.json()
            if status["status"] in {"done", "failed"}:
                break
            time.sleep(2)
    report.update({"jobId": job_id, "status": status["status"], "qa": status.get("qa")})
    checks = {item["id"]: item["ok"] for item in status.get("qa", {}).get("checks", [])}
    report["stages"]["renderQa"] = (
        status["status"] == "done"
        and bool(status.get("qa", {}).get("ok"))
        and checks.get("sampled_frames") is True
        and checks.get("render_contract") is True
        and checks.get("final_artwork_hold") is True
    )
    (OUTPUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(report["stages"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
