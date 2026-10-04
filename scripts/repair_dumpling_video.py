"""Generate and render a semantically constrained local-model dumpling tutorial."""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

import httpx


API = "http://127.0.0.1:8000"
RENDER = "http://127.0.0.1:3001"
OUT = Path(__file__).parents[1] / "outputs" / "repair-dumpling"

SCENES = [
    (
        "ingredients", "Dough preparation",
        "Add water to flour, mix shaggy dough, then knead a smooth dough ball.",
        "large centered instructional food illustration of dough preparation: a paper flour bag and a ceramic bowl of white flour, a clear stream of water being poured into the flour, chopsticks mixing shaggy dough, two hands kneading, and one dough ball resting under a cloth; flour-to-dough transformation is the only main action; no noodles, no ramen, no soup, no eating, no finished dumplings, no pleated pastries, no readable text, no logo, no watermark",
    ),
    (
        "roll_rope", "Roll the dough rope",
        "Roll the dough into one long even rope.",
        "close-up of two hands rolling one long cylindrical dough rope on a board; only one rope and hands; no knife, no rolling pin, no wrapper, no dumplings, no noodles, no text",
    ),
    (
        "cut_pieces", "Cut equal dough pieces",
        "Cut the rope into equal dough pieces.",
        "close-up of one hand holding a knife touching one straight dough rope and cutting equal pieces on a board; clear knife contact; no rolling pin, no wrapper, no dumplings, no noodles, no text",
    ),
    (
        "roll_wrapper", "Roll one wrapper",
        "Flatten one dough piece into a round wrapper.",
        "close-up of both hands using a wooden rolling pin on one dough piece to make one round wrapper; clear tool contact; no knife, no filling, no dumpling, no noodles, no text",
    ),
    (
        "wrapping", "Fill and pinch",
        "Place filling in the center, fold the wrapper, and pinch pleats along the edge.",
        "close-up instructional action sequence: spoon places visible filling on a round wrapper, wrapper folds into a half moon, fingers pinch a row of pleats; one dumpling only; no noodles, no pot, no text",
    ),
    (
        "boil_drop", "Boil and add water",
        "Lower dumplings into boiling water, then add cold water once while they cook.",
        "open pot of boiling water, slotted spoon actively lowers crescent-shaped pleated dumplings below water surface; bubbles and water line; no steamer, no buns, no noodles, no text",
    ),
    (
        "boil_add_water", "Add cold water",
        "Add cold water while the dumplings boil.",
        "open pot with submerged pleated dumplings and bubbles, ladle pours a visible stream of cold water into the pot; no steamer, no buns, no noodles, no text",
    ),
    (
        "boil_float_scoop", "Float and scoop out",
        "When dumplings float and swell, scoop them out.",
        "pleated crescent dumplings visibly floating and swelling in clear boiling water while a slotted spoon lifts them out; open pot, bubbles; no steamer, no buns, no noodles, no text",
    ),
    (
        "wrappers", "Make dumpling wrappers",
        "Cut the dough rope into equal pieces, then roll one piece into a round wrapper.",
        "large left-to-right three-stage instructional action strip for making Chinese dumpling wrappers, with three separate large panels and no overhead still-life flat lay: stage one shows two hands actively rolling a long dough rope on a wooden board, stage two shows a knife in contact with the rope actively cutting it into equal dough pieces, stage three shows both hands using a wooden rolling pin in contact with one dough piece to flatten it into a round wrapper; tool-to-dough contact and motion must be unmistakable in every stage; no noodles, no soup, no finished meal, no plated dumplings, no decorative ingredient spread, no readable text, no logo, no watermark",
    ),
    (
        "wrapping", "Wrap and pinch dumplings",
        "Place filling in the center, fold the wrapper, and pinch pleats along the edge.",
        "large close-up instructional food illustration of wrapping one Chinese dumpling: a round wrapper held in one hand, a spoon placing visible vegetable and meat filling in the center, the wrapper folded into a half moon, and fingers pinching a neat row of pleats; active wrapping action; no noodles, no rolling pin, no boiling pot, no plated meal, no readable text, no logo, no watermark",
    ),
    (
        "boiling", "Boil dumplings",
        "Place dumplings in boiling water and remove them when they float and swell.",
        "large left-to-right three-stage instructional action strip for boiling Chinese dumplings in water, with three separate large panels and no steamer: stage one shows a slotted spoon actively lowering several pleated dumplings below the surface of a wide open pot of clear boiling water, stage two shows a ladle pouring a visible stream of cold water into the same pot while dumplings are submerged among bubbles, stage three shows several pleated dumplings visibly floating and swelling while a slotted spoon lifts them out; show water surface, submerged dumplings, bubbles, and tool contact clearly; no bamboo steamer, no steamer basket, no steamed buns, no baozi, no mantou, no dry steam, no lidded steamer, no noodles, no soup bowl, no readable text, no logo, no watermark",
    ),
]


def scene(scene_id: str, order: int, title: str, narration: str, description: str) -> dict:
    return {
        "id": scene_id,
        "order": order,
        "title": title,
        "narration": narration,
        "duration_estimate": 15,
        "learning_goal": title,
        "image_description": f"{description}; text-free artwork; no readable text",
        "visual_mode": "direct_reference",
        "render_strategy": "trace",
        "visual_complexity": "reference",
        "board_mode": "reference",
        "hand_usage": "trace",
        "video_style": "whiteboard",
        "visual_style": "marketing_doodle",
        "pen_style": "marker",
        "visual_anchor": title,
        "canvasWidth": 1920,
        "canvasHeight": 1080,
        "diagram_plan": {"kind": "process", "layout": "one large central cooking action", "required_labels": [title]},
        "visual_beats": [{"id": "beat_0", "draw_intent": title, "narration": narration, "required_labels": [title], "duration_estimate": 12}],
        "annotation_plan": [
            {"type": "label", "label": title, "target": "main action", "beat_id": "beat_0", "layer": "renderer"},
            {"type": "arrow", "label": "action", "target": "motion", "beat_id": "beat_0", "layer": "renderer"},
            {"type": "highlight", "label": "result", "target": "result", "beat_id": "beat_0", "layer": "renderer"},
            {"type": "checkmark", "label": "complete", "target": "final state", "beat_id": "beat_0", "layer": "renderer"},
        ],
        "animations": [{"type": "whiteboard_draw", "duration": 10, "content": title}, {"type": "highlight", "duration": 2, "content": "result"}],
        "renderElements": [{
            "id": f"{scene_id}-art", "sequence": 1, "narrativeRole": "content", "subtitle": narration,
            "region": {"x": 0, "y": 0, "width": 1920, "height": 1080},
            "reveal": {"startMs": 0, "durationMs": 8000, "protectedRegions": []}, "source": "authored",
        }],
    }


def _compose_action_board(client: httpx.Client, board_id: str, topic: str, actions: list[tuple[str, str]]) -> bytes:
    response = client.post(API + "/imagegen/action-board", json={
        "board_id": board_id,
        "topic": topic,
        "columns": len(actions),
        "actions": [{
            "action_id": action_id,
            "title": action_id.replace("_", " "),
            "image_description": f"single close-up action reference, no collage: {description}; no logo, no watermark",
            "quality": "final",
        } for action_id, description in actions],
    })
    response.raise_for_status()
    payload = response.json()
    encoded = payload.get("image")
    if not encoded:
        raise RuntimeError(f"Action board rejected: {board_id}: {payload.get('diagnostics')}")
    return base64.b64decode(encoded.split(",", 1)[1] if encoded.startswith("data:") else encoded)


def _compose_wrapper_action_board(client: httpx.Client, topic: str) -> bytes:
    return _compose_action_board(client, "wrappers", topic, [
        ("roll_rope", "two bare hands roll one straight long cylindrical dough rope directly on a board; only hands, one rope and board; no knife, no rolling pin, no wrapper, no dumplings, no noodles, no bowl, no text"),
        ("cut_pieces", "one hand holds a knife touching one straight dough rope and cuts it into equal pieces; only hand, knife, rope and board; no rolling pin, no wrapper, no dumplings, no noodles, no bowl, no text"),
        ("roll_wrapper", "both hands hold a wooden rolling pin touching one small dough piece and flatten it into one round wrapper; no knife, no filling, no folded dumpling, no noodles, no bowl, no text"),
    ])


def _compose_boiling_action_board(client: httpx.Client, topic: str) -> bytes:
    return _compose_action_board(client, "boiling", topic, [
        ("boil_drop", "a slotted spoon lowers crescent-shaped dumplings with folded edges below the surface of clear boiling water in an open pot; visible bubbles and water line; no steamer, round buns, baozi, mantou, noodles, soup, or text"),
        ("boil_add_water", "a ladle pours a clear stream of cold water into an open pot while crescent-shaped dumplings with folded edges are submerged in boiling water; no steamer, round buns, baozi, mantou, noodles, soup, or text"),
        ("boil_float_scoop", "crescent-shaped dumplings with folded edges float on clear boiling water while a slotted spoon lifts them out; open pot, water line and bubbles; no steamer, round buns, baozi, mantou, noodles, soup, or text"),
    ])


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    requested = {value.strip() for value in os.environ.get("EXPLAINFLOW_SCENES", "").split(",") if value.strip()}
    # The action-level scenes replace the old three-panel wrapper/boiling boards.
    selected_scenes = []
    seen_ids = set()
    for item in SCENES:
        if item[0] in {"wrappers", "boiling", "roll_rope", "boil_add_water"} or item[0] in seen_ids or (requested and item[0] not in requested):
            continue
        selected_scenes.append(item)
        seen_ids.add(item[0])
    storyboard = {
        "topic": "How to make Chinese dumplings: flour to boiling",
        "total_duration_estimate": 15 * len(selected_scenes),
        "video_style": "whiteboard",
        "pen_style": "marker",
        "scenes": [scene(item[0], index, item[1], item[2], item[3]) for index, item in enumerate(selected_scenes)],
    }
    with httpx.Client(timeout=900) as client:
        fixture_mode = os.environ.get("EXPLAINFLOW_USE_FIXTURES", "").strip() == "1"
        fixture_suffix = "-v3.png" if (OUT / "ingredients-v3.png").exists() and requested == {"ingredients"} else "-v2.png"
        wrapper_fixture = OUT / ("wrappers-final-1024-board.png" if (OUT / "wrappers-final-1024-board.png").exists() else "wrappers-v4.png")
        boiling_fixture = OUT / ("boiling-final-1024-board.png" if (OUT / "boiling-final-1024-board.png").exists() else "boiling-v4.png")
        action_fixtures = {
            "roll_rope": OUT / "roll_rope-realref.png",
            "cut_pieces": OUT / "cut_pieces.png",
            "roll_wrapper": OUT / "roll_wrapper-v2.png",
            "wrapping": OUT / "wrapping-v2.png",
            # Combined boil scene uses the authored three-stage board for
            # lowering and adding water; the final scene isolates floating.
            "boil_drop": OUT / "boiling-final-1024-board.png",
            "boil_add_water": OUT / "boil_add_water.png",
            "boil_float_scoop": OUT / "boil_float_scoop-final-1024.png",
        }
        if fixture_mode and all((item["id"] in action_fixtures and action_fixtures[item["id"]].exists()) or (OUT / f"{item['id']}{fixture_suffix}").exists() or (item["id"] == "wrappers" and wrapper_fixture.exists()) or (item["id"] == "boiling" and boiling_fixture.exists()) for item in storyboard["scenes"]):
            image_payload = {"images": {}, "diagnostics": {}}
            for item in storyboard["scenes"]:
                source = action_fixtures.get(item["id"]) if item["id"] in action_fixtures and action_fixtures[item["id"]].exists() else wrapper_fixture if item["id"] == "wrappers" and wrapper_fixture.exists() else boiling_fixture if item["id"] == "boiling" and boiling_fixture.exists() else (OUT / f"{item['id']}{fixture_suffix}")
                encoded = base64.b64encode(source.read_bytes()).decode("ascii")
                image_payload["images"][item["id"]] = encoded
                image_payload["diagnostics"][item["id"]] = {"ok": True, "source": f"local-{source.stem}-fixture"}
        else:
            generated = client.post(f"{API}/imagegen/scenes", json={"scenes": [{
                "scene_id": item["id"], "topic": storyboard["topic"], "title": item["title"],
                "image_description": item["image_description"], "board_mode": "reference", "hand_usage": "trace",
                "video_style": "whiteboard", "visual_style": "marketing_doodle", "pen_style": "marker", "quality": "final",
            } for item in storyboard["scenes"]]})
            generated.raise_for_status()
            image_payload = generated.json()
            if any(item["id"] == "wrappers" for item in storyboard["scenes"]):
                board = _compose_wrapper_action_board(client, storyboard["topic"])
                image_payload["images"]["wrappers"] = base64.b64encode(board).decode("ascii")
                image_payload["diagnostics"]["wrappers"] = {"ok": True, "source": "local-action-panels"}
            if any(item["id"] == "boiling" for item in storyboard["scenes"]):
                board = _compose_boiling_action_board(client, storyboard["topic"])
                image_payload["images"]["boiling"] = base64.b64encode(board).decode("ascii")
                image_payload["diagnostics"]["boiling"] = {"ok": True, "source": "local-boiling-action-panels"}
        for item in storyboard["scenes"]:
            encoded = image_payload["images"].get(item["id"])
            if not encoded:
                raise RuntimeError(f"Image rejected for {item['id']}: {image_payload['diagnostics'].get(item['id'])}")
            (OUT / f"{item['id']}.png").write_bytes(base64.b64decode(encoded))
            item["image_url"] = f"data:image/png;base64,{encoded}"
        validation = client.post(f"{API}/planner/validate-storyboard", json={"storyboard": storyboard, "fps": 30})
        validation.raise_for_status()
        normalized = validation.json()
        if not normalized["ok"]:
            raise RuntimeError(json.dumps(normalized, ensure_ascii=False))
        storyboard = normalized["storyboard"]
        (OUT / "storyboard.json").write_text(json.dumps(storyboard, ensure_ascii=False, indent=2), encoding="utf-8")
        started = client.post(f"{RENDER}/render", json={"storyboard": storyboard, "voice": "xiaoxiao", "subtitlesEnabled": True, "backgroundMusicEnabled": False, "forceRender": True})
        started.raise_for_status()
        job_id = started.json()["jobId"]
        deadline = time.time() + 900
        status = {}
        while time.time() < deadline:
            response = client.get(f"{RENDER}/job/{job_id}")
            response.raise_for_status()
            status = response.json()
            if status.get("status") in {"done", "failed"}:
                break
            time.sleep(3)
    report = {"jobId": job_id, "status": status, "imageDiagnostics": image_payload["diagnostics"]}
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    qa = status.get("qa") or {}
    print(json.dumps({"jobId": job_id, "status": status.get("status"), "qaOk": qa.get("ok"), "duration": status.get("actualDurationSeconds")}, ensure_ascii=False))
    return 0 if status.get("status") == "done" and qa.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
