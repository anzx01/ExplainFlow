import json
import time
import urllib.error
import urllib.request
from pathlib import Path


API_BASE = "http://localhost:8000"
RENDER_BASE = "http://localhost:3001"
OUT_DIR = Path("outputs/regen-seven-habits-valid")
GRAPH_PATH = OUT_DIR / "graph.json"
STORYBOARD_PATH = OUT_DIR / "storyboard.json"
RENDER_JOB_PATH = OUT_DIR / "render-job.json"


def post_json(url: str, payload: dict, timeout: int = 600) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"POST {url} failed: {exc.code} {detail}") from exc


def get_json(url: str, timeout: int = 30) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def assert_chinese_topic(graph: dict) -> None:
    topic = graph.get("topic", "")
    required = ["高效能", "七个习惯"]
    if not all(part in topic for part in required):
        raise RuntimeError(f"Graph topic mismatch: {topic!r}")
    labels = " ".join(str(node.get("label", "")) for node in graph.get("nodes", []))
    for part in ["主动积极", "以终为始", "要事第一", "双赢", "知彼解己"]:
        if part not in labels:
            raise RuntimeError(f"Graph appears incomplete; missing {part!r}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    graph_payload = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    graph = graph_payload["graph"]
    assert_chinese_topic(graph)
    print(f"[1/3] graph ok: {graph['topic']} ({len(graph.get('nodes', []))} nodes)", flush=True)

    print("[2/3] generating storyboard...", flush=True)
    storyboard_resp = post_json(
        f"{API_BASE}/planner/storyboard",
        {"graph": graph, "target_duration": 120},
        timeout=900,
    )
    storyboard = storyboard_resp["storyboard"]
    STORYBOARD_PATH.write_text(json.dumps(storyboard_resp, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[2/3] storyboard ok: {len(storyboard.get('scenes', []))} scenes, "
        f"{storyboard.get('total_duration_estimate')}s",
        flush=True,
    )
    titles = " | ".join(scene.get("title", "") for scene in storyboard.get("scenes", []))
    print(f"[2/3] titles: {titles}", flush=True)

    print("[3/3] submitting render job...", flush=True)
    job_resp = post_json(
        f"{API_BASE}/render/job",
        {
            "storyboard": storyboard,
            "voice": "xiaoxiao",
            "resolution": "1080p",
            "subtitles_enabled": False,
            "background_music_enabled": False,
            "background_music_id": None,
            "background_music_volume": 0.12,
        },
        timeout=120,
    )
    RENDER_JOB_PATH.write_text(json.dumps(job_resp, ensure_ascii=False, indent=2), encoding="utf-8")
    job_id = job_resp["job_id"]
    print(f"[3/3] job id: {job_id}", flush=True)

    last = None
    while True:
        status = get_json(f"{RENDER_BASE}/job/{job_id}", timeout=30)
        stamp = (
            status.get("status"),
            status.get("phase"),
            round(float(status.get("progress", 0)), 1),
            status.get("actualDurationSeconds"),
        )
        if stamp != last:
            print(f"[render] status={stamp[0]} phase={stamp[1]} progress={stamp[2]} duration={stamp[3]}", flush=True)
            last = stamp
        if status.get("status") == "done":
            print(f"[done] {RENDER_BASE}/download/{job_id}", flush=True)
            break
        if status.get("status") == "failed":
            raise RuntimeError(status.get("error") or "render failed")
        time.sleep(3)


if __name__ == "__main__":
    main()
