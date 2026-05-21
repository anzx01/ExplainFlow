import urllib.request, json, time
API_BASE = 'http://localhost:8000'
RENDER_BASE = 'http://localhost:8000'

print('1. Getting graph...')
req = urllib.request.Request(API_BASE + '/explain/graph',
    data=json.dumps({'prompt': '如何保护视力', 'markdown': '', 'audience': 'beginner'}).encode(),
    headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(req, timeout=120) as r:
    graph = json.loads(r.read())['graph']
print('Graph:', graph['topic'])
print()

print('2. Getting storyboard with video_style=whiteboard...')
req2 = urllib.request.Request(API_BASE + '/planner/storyboard',
    data=json.dumps({'graph': graph, 'target_duration': 60, 'video_style': 'whiteboard', 'pen_style': 'marker'}).encode(),
    headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(req2, timeout=180) as r:
    sb = json.loads(r.read())['storyboard']
print('Scenes:', len(sb['scenes']))
for i, scene in enumerate(sb['scenes'][:3]):
    vs = scene.get('visual_style')
    bm = scene.get('board_mode')
    hu = scene.get('hand_usage')
    rr = scene.get('rasterReveal', {})
    rm = rr.get('renderMode', 'None')
    print('  Scene %d: visualStyle=%s, boardMode=%s, handUsage=%s, renderMode=%s' % (i, vs, bm, hu, rm))
print()

print('3. Creating render job...')
req3 = urllib.request.Request(API_BASE + '/render/job',
    data=json.dumps({
        'storyboard': sb,
        'voice': 'xiaoxiao',
        'resolution': '720p',
        'subtitles_enabled': False,
        'background_music_enabled': False
    }).encode(),
    headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(req3, timeout=30) as r:
    job = json.loads(r.read())
job_id = job['job_id']
print('Job ID:', job_id)
print()
print('4. Polling for completion...')
for i in range(120):
    time.sleep(5)
    try:
        req4 = urllib.request.Request(RENDER_BASE + '/render/job/' + job_id, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req4, timeout=10) as r:
            status = json.loads(r.read())
        print('  Status: %s, Progress: %s%%' % (status.get('status'), status.get('progress')))
        if status.get('status') == 'done':
            print()
            print('5. Downloading video...')
            video_url = RENDER_BASE + '/render/download/' + job_id
            req5 = urllib.request.Request(video_url)
            with urllib.request.urlopen(req5, timeout=60) as r:
                video_data = r.read()
            output_path = r'D:\aiapp\ExplainFlow\outputs\teacher_whiteboard_v2.mp4'
            with open(output_path, 'wb') as f:
                f.write(video_data)
            import os
            size_mb = os.path.getsize(output_path) / (1024*1024)
            print('Video saved to:', output_path, '(%.1f MB)' % size_mb)
            break
    except Exception as e:
        print('  Error:', e)
