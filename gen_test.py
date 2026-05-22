import urllib.request, json, time

API_BASE = 'http://localhost:8000'

# Get graph
req = urllib.request.Request(f'{API_BASE}/explain/graph',
    data=json.dumps({'prompt': 'What is Machine Learning', 'markdown': '', 'audience': 'beginner'}).encode(),
    headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(req, timeout=120) as r:
    graph = json.loads(r.read())['graph']
print('Graph ready:', graph['topic'])

# Get storyboard
req2 = urllib.request.Request(f'{API_BASE}/planner/storyboard',
    data=json.dumps({'graph': graph, 'target_duration': 60, 'video_style': 'whiteboard', 'pen_style': 'marker'}).encode(),
    headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(req2, timeout=180) as r:
    sb = json.loads(r.read())['storyboard']
print('Scenes:', len(sb['scenes']), 'Duration:', sb['total_duration_estimate'], 'Style:', sb.get('video_style'))

# Generate remotion code
req3 = urllib.request.Request(f'{API_BASE}/planner/remotion-code',
    data=json.dumps({
        'storyboard': sb,
        'fps': 30,
        'width': 1280,
        'height': 720,
        'style_prompt': 'hand-drawn YouTube whiteboard animation, black ink outlines, loose watercolor fills'
    }).encode(),
    headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(req3, timeout=300) as r:
    remotion = json.loads(r.read())
print('Remotion code generated, frames:', remotion['duration_in_frames'])

# Create render job
req4 = urllib.request.Request(f'{API_BASE}/render/job',
    data=json.dumps({
        'storyboard': sb,
        'voice': 'xiaoxiao',
        'resolution': '720p',
        'subtitles_enabled': False,
        'background_music_enabled': False
    }).encode(),
    headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(req4, timeout=30) as r:
    job = json.loads(r.read())
job_id = job['job_id']
print('Render job created:', job_id)

# Poll for completion
print('Waiting for render to complete...', flush=True)
timeout = 600  # 10 minutes
start = time.time()
while time.time() - start < timeout:
    time.sleep(10)
    req5 = urllib.request.Request(f'{API_BASE}/render/job/{job_id}',
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req5, timeout=30) as r:
        status = json.loads(r.read())
    print(f'  Status: {status["status"]} Progress: {status.get("progress", 0):.1f}% Phase: {status.get("phase", "N/A")}')
    if status['status'] == 'done':
        break
    if status['status'] == 'failed':
        print('Render failed:', status.get('error'))
        exit(1)

# Download video
print('Downloading video...')
req6 = urllib.request.Request(f'{API_BASE}/render/download/{job_id}')
with urllib.request.urlopen(req6, timeout=300) as r:
    video_data = r.read()

output_file = f'{job_id}.mp4'
with open(output_file, 'wb') as f:
    f.write(video_data)
print(f'Video saved to: {output_file} ({len(video_data) // 1024} KB)')
