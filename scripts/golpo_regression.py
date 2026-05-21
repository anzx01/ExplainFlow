#!/usr/bin/env python3
"""Run Golpo storyboard regression cases against a running ExplainFlow API."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TOPICS = [
    "如何制作好吃的麻婆豆腐，要求图文并茂",
    "高效能人士的七个习惯",
    "梯度下降原理",
    "MOSFET 工作原理",
    "给投资人讲一个 SaaS 产品如何增长",
]

STYLES = ["whiteboard", "editorial", "technical_blueprint", "sharpie"]
HARD_TRANSLATION_BLACKLIST = ["互赖", "相互依赖赖"]


def post_json(api_url: str, path: str, payload: dict[str, Any], timeout: int = 180) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        api_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def storyboard_text(storyboard: dict[str, Any]) -> str:
    return json.dumps(storyboard, ensure_ascii=False)


def validate_storyboard(storyboard: dict[str, Any], topic: str, style: str) -> list[str]:
    errors: list[str] = []
    scenes = storyboard.get("scenes") if isinstance(storyboard.get("scenes"), list) else []
    if not scenes:
        return ["storyboard has no scenes"]

    for idx, scene in enumerate(scenes):
        sid = scene.get("id") or f"scene_{idx}"
        video_style = scene.get("video_style") or scene.get("videoStyle")
        pen_style = scene.get("pen_style") or scene.get("penStyle")
        if not video_style:
            errors.append(f"{sid}: missing video_style")
        if not pen_style:
            errors.append(f"{sid}: missing pen_style")
        desc = str(scene.get("image_description") or scene.get("imageDescription") or "").lower()
        if desc and "text-free" not in desc and "no readable" not in desc:
            errors.append(f"{sid}: image_description missing text-free/no-readable constraint")

    blob = storyboard_text(storyboard)
    for term in HARD_TRANSLATION_BLACKLIST:
        if term in blob:
            errors.append(f"hard translation blacklist term found: {term}")

    if "麻婆" in topic or "豆腐" in topic:
        prompt_blob = " ".join(
            str(scene.get("title") or "")
            + " "
            + str(scene.get("image_description") or scene.get("imageDescription") or "")
            for scene in scenes
        ).lower()
        required = ["wok", "red", "tofu"]
        missing = [term for term in required if term not in prompt_blob]
        if missing:
            errors.append(f"mapo visual terms missing: {', '.join(missing)}")

    if style != "auto" and storyboard.get("video_style") not in {style, None}:
        errors.append(f"storyboard video_style {storyboard.get('video_style')} != requested {style}")
    return errors


def run_case(api_url: str, topic: str, style: str, target_duration: int) -> dict[str, Any]:
    graph = post_json(api_url, "/explain/graph", {"prompt": topic}).get("graph")
    if not graph:
        raise RuntimeError("graph response missing graph")
    storyboard = post_json(
        api_url,
        "/planner/storyboard",
        {
            "graph": graph,
            "target_duration": target_duration,
            "video_style": style,
            "pen_style": "marker",
        },
    ).get("storyboard")
    if not storyboard:
        raise RuntimeError("storyboard response missing storyboard")
    errors = validate_storyboard(storyboard, topic, style)
    return {
        "topic": topic,
        "style": style,
        "status": "ok" if not errors else "failed",
        "scene_count": len(storyboard.get("scenes", [])),
        "errors": errors,
        "storyboard": storyboard,
    }


def case_matrix() -> list[dict[str, str]]:
    return [{"topic": topic, "style": style} for topic in TOPICS for style in STYLES]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--target-duration", type=int, default=120)
    parser.add_argument("--dry-run", action="store_true", help="Only write the fixed regression matrix")
    parser.add_argument("--output", type=Path, default=Path("evals/golpo_regression_results.json"))
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    cases = case_matrix()
    if args.dry_run:
        payload = {"cases": cases}
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[golpo] wrote dry-run matrix: {args.output}")
        return 0

    results = []
    for index, case in enumerate(cases, 1):
        topic = case["topic"]
        style = case["style"]
        print(f"[golpo] {index}/{len(cases)} {style} · {topic}", flush=True)
        try:
            results.append(run_case(args.api_url, topic, style, args.target_duration))
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            results.append(
                {
                    "topic": topic,
                    "style": style,
                    "status": "error",
                    "errors": [str(exc)],
                }
            )

    failed = [item for item in results if item["status"] != "ok"]
    summary = {
        "total": len(results),
        "ok": len(results) - len(failed),
        "failed": len(failed),
        "results": results,
    }
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[golpo] wrote results: {args.output}")
    print(f"[golpo] ok={summary['ok']} failed={summary['failed']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
