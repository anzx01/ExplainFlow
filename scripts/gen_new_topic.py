"""Generate a fresh ExplainFlow video on a new topic, with subtitles on."""
import json, urllib.request, urllib.error, time, sys

API = "http://127.0.0.1:8010"
RENDER = "http://127.0.0.1:3002"
TOPIC = sys.argv[1] if len(sys.argv) > 1 else "复利效应：为什么钱会越滚越多"
SB_CACHE = "outputs/gen-storyboard-cache.json"

def post(url, body, timeout=300):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def get(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)

import os
if os.path.exists(SB_CACHE) and os.environ.get("REUSE_SB") == "1":
    sb = json.load(open(SB_CACHE, encoding="utf-8"))
    print(f"[reuse] storyboard from {SB_CACHE}: scenes={len(sb.get('scenes', []))}", flush=True)
else:
    print("[1] explain/graph ...", flush=True)
    graph_resp = post(f"{API}/explain/graph", {"prompt": TOPIC})
    graph = graph_resp["graph"]
    print(f"    topic={graph['topic']}  nodes={len(graph['nodes'])}", flush=True)

    print("[2] planner/storyboard ...", flush=True)
    sb_resp = post(f"{API}/planner/storyboard", {"graph": graph})
    sb = sb_resp.get("storyboard", sb_resp)
    json.dump(sb, open(SB_CACHE, "w", encoding="utf-8"), ensure_ascii=False)

scenes = sb.get("scenes", [])
print(f"    scenes={len(scenes)}  estimated total={sb.get('total_duration_estimate')}s", flush=True)

print("[3] render/job (subtitles on) ...", flush=True)
render_resp = post(f"{API}/render/job", {"storyboard": sb, "subtitles_enabled": True, "force_render": True})
job_id = render_resp.get("job_id") or render_resp.get("jobId")
print(f"    job_id={job_id}", flush=True)

print("[4] polling ...", flush=True)
deadline = time.time() + 1500
last = None
while time.time() < deadline:
    time.sleep(10)
    try:
        status_data = get(f"{RENDER}/job/{job_id}")
    except Exception:
        status_data = get(f"{API}/render/job/{job_id}")
    status = status_data.get("status", "unknown")
    progress = status_data.get("progress", "")
    line = f"    [{int(time.time() % 100000)}] {status} {progress}"
    if line != last:
        print(line, flush=True)
        last = line
    if status in ("completed", "failed", "done", "error"):
        break

print("[done]")
out = {k: status_data.get(k) for k in ("status", "videoUrl", "video_url", "outputPath", "error", "qa")}
print(json.dumps(out, ensure_ascii=False, indent=2)[:800])
with open("outputs/new-topic-job.json", "w", encoding="utf-8") as f:
    json.dump({"job_id": job_id, "topic": TOPIC, "status": status_data}, f, ensure_ascii=False)
