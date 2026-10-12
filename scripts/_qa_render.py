"""QA script: explain -> storyboard -> render job, then poll until done."""
import json, urllib.request, urllib.error, time, sys

API = "http://localhost:8010"
RENDER = "http://localhost:3002"

def post(url, body):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)

print("[1] explain/graph ...")
graph_resp = post(f"{API}/explain/graph", {"prompt": "backpropagation algorithm"})
graph = graph_resp["graph"]
print(f"    topic={graph['topic']}  nodes={len(graph['nodes'])}")

print("[2] planner/storyboard ...")
sb_resp = post(f"{API}/planner/storyboard", {"graph": graph})
# handle both {"storyboard": {...}} and direct storyboard object
sb = sb_resp.get("storyboard", sb_resp)
scenes = sb.get("scenes", [])
print(f"    scenes={len(scenes)}")
if scenes:
    print("      sample keys:", list(scenes[0].keys())[:8])
for s in scenes[:3]:
    sid = s.get('scene_id') or s.get('id') or s.get('sceneId') or '?'
    print(f"      [{sid}] {s.get('title','')} anims={len(s.get('animation_instructions',[]))}")

print("[3] render/job ...")
render_resp = post(f"{API}/render/job", {"storyboard": sb})
job_id = render_resp.get("job_id") or render_resp.get("jobId")
print(f"    job_id={job_id}")

print("[4] polling render status ...")
for i in range(60):
    time.sleep(5)
    try:
        with urllib.request.urlopen(f"{RENDER}/job/{job_id}", timeout=10) as r:
            status_data = json.load(r)
    except Exception:
        with urllib.request.urlopen(f"{API}/render/job/{job_id}", timeout=10) as r:
            status_data = json.load(r)
    status = status_data.get("status", "unknown")
    progress = status_data.get("progress", "")
    print(f"    [{i*5}s] status={status} {progress}")
    if status in ("completed", "failed", "done"):
        break

print("[done]", json.dumps(status_data, ensure_ascii=False, indent=2)[:500])
