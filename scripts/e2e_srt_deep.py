"""Focused regression for the srt-whiteboard ink/color/mask pipeline."""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import httpx


ROOT = Path(__file__).parents[1]
API = "http://127.0.0.1:8000"
RENDER = "http://127.0.0.1:3001"
OUT = ROOT / "outputs" / "e2e-srt-deep"
SOURCE_IMAGE = ROOT / "outputs" / "repair-dumpling" / "ingredients.png"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if not SOURCE_IMAGE.exists():
        raise FileNotFoundError(f"Missing fixed local-model fixture: {SOURCE_IMAGE}")
    encoded = base64.b64encode(SOURCE_IMAGE.read_bytes()).decode("ascii")
    narration = "先观察左侧的面粉和水，再看右侧逐渐形成的面团。线稿完成以后，画面才开始添彩。"
    storyboard = {
        "topic": "白板连续笔迹回归",
        "total_duration_estimate": 9,
        "video_style": "whiteboard",
        "pen_style": "marker",
        "scenes": [{
            "id": "ink-color-mask",
            "order": 0,
            "title": "和面步骤",
            "narration": narration,
            "duration_estimate": 9,
            "learning_goal": "验证分区遮罩、连续线稿和随后添彩",
            "image_description": "text-free local-model cooking illustration with bowl, water, chopsticks and dough",
            "image_url": f"data:image/png;base64,{encoded}",
            "visual_mode": "direct_reference",
            "render_strategy": "trace",
            "visual_complexity": "reference",
            "board_mode": "reference",
            "hand_usage": "trace",
            "video_style": "whiteboard",
            "visual_style": "marketing_doodle",
            "visual_anchor": "面粉加水形成面团",
            "canvasWidth": 1920,
            "canvasHeight": 1080,
            "visual_beats": [{
                "id": "beat_0", "draw_intent": "先左后右描出和面过程",
                "narration": narration, "required_labels": [], "duration_estimate": 8,
            }],
            "annotation_plan": [
                {"type": "label", "label": "加水", "target": "左侧材料", "beat_id": "beat_0", "layer": "renderer"},
                {"type": "arrow", "label": "混合", "target": "中间动作", "beat_id": "beat_0", "layer": "renderer"},
                {"type": "highlight", "label": "成团", "target": "右侧结果", "beat_id": "beat_0", "layer": "renderer"},
                {"type": "checkmark", "label": "完成", "target": "最终状态", "beat_id": "beat_0", "layer": "renderer"},
            ],
            "animations": [{"type": "whiteboard_draw", "duration": 7, "content": "和面过程"}],
            "renderElements": [
                {
                    "id": "left-process", "sequence": 1, "narrativeRole": "材料与加水",
                    "subtitle": "先观察左侧的面粉和水。",
                    "region": {"x": 0, "y": 0, "width": 960, "height": 1080},
                    "reveal": {"startMs": 0, "durationMs": 3800, "ink_weight": 2, "color_weight": 1, "protectedRegions": []},
                    "source": "authored",
                },
                {
                    "id": "right-result", "sequence": 2, "narrativeRole": "混合后的面团",
                    "subtitle": "再看右侧逐渐形成的面团。",
                    "region": {"x": 960, "y": 0, "width": 960, "height": 1080},
                    "reveal": {"startMs": 4000, "durationMs": 4500, "ink_weight": 2, "color_weight": 1, "protectedRegions": []},
                    "source": "authored",
                },
            ],
        }],
    }

    report: dict = {"sourceImage": str(SOURCE_IMAGE), "checks": {}}
    with httpx.Client(timeout=420) as client:
        validated = client.post(f"{API}/planner/validate-storyboard", json={"storyboard": storyboard, "fps": 30})
        validated.raise_for_status()
        validation = validated.json()
        storyboard = validation["storyboard"]
        report["checks"]["contract"] = validation["ok"]
        report["contractIssues"] = validation["issues"]

        started = client.post(f"{RENDER}/render", json={
            "storyboard": storyboard, "voice": "xiaoxiao", "subtitlesEnabled": True,
            "backgroundMusicEnabled": False,
        })
        started.raise_for_status()
        job_id = started.json()["jobId"]
        deadline = time.time() + 420
        status = {}
        while time.time() < deadline:
            response = client.get(f"{RENDER}/job/{job_id}")
            response.raise_for_status()
            status = response.json()
            if status.get("status") in {"done", "failed"}:
                break
            time.sleep(2)

    generated_dir = Path(status.get("generatedDir") or "")
    generated_tsx = generated_dir / "GeneratedVideo.tsx"
    tsx = generated_tsx.read_text(encoding="utf-8") if generated_tsx.exists() else ""
    report["checks"]["pairedInkColor"] = '"phase":"ink"' in tsx and '"phase":"color"' in tsx and "colorOpId" in tsx
    report["checks"]["contractMaskedRaster"] = "mask={maskIdForOp(scene, op)" in tsx
    report["checks"]["croppedHand"] = "const HAND_WIDTH = 282" in tsx and "const PEN_TIP_X = 198" in tsx and "hand-real-pen.png" in tsx
    if tsx:
        (OUT / "compiled.tsx").write_text(tsx, encoding="utf-8")

    qa_checks = {item["id"]: item["ok"] for item in status.get("qa", {}).get("checks", [])}
    report.update({"jobId": job_id, "status": status, "qaChecks": qa_checks})
    report["checks"]["render"] = status.get("status") == "done" and status.get("qa", {}).get("ok") is True
    report["checks"]["sampledFrames"] = qa_checks.get("sampled_frames") is True
    report["checks"]["finalHold"] = qa_checks.get("final_artwork_hold") is True
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"jobId": job_id, "checks": report["checks"], "outputPath": status.get("outputPath")}, ensure_ascii=False, indent=2))
    return 0 if all(report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
