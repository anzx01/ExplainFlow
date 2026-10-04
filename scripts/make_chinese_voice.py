from pathlib import Path
import httpx, subprocess, tempfile

root=Path(__file__).parents[1]
ff=root/'apps/render/node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe'
src=root/'outputs/How_to_make_Chinese_dumplings_flour_to_boiling_d39d4728.mp4'
dst=root/'outputs/How_to_make_Chinese_dumplings_chinese_voice.mp4'
texts=['往面粉中加水，搅拌成絮状面团，再揉成光滑的面团。','把面团搓成长而均匀的面条状。','把面团条切成大小均匀的小面剂。','用擀面杖把一个面剂擀成圆形面皮。','在面皮中央放入馅料，对折面皮并沿边缘捏出褶皱。','把饺子放入沸水中煮，浮起变大后用漏勺捞出。']
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=120) as c, tempfile.TemporaryDirectory() as d:
    files=[]
    for i,t in enumerate(texts):
        r=c.post('/narration/synthesize',json={'text':t,'voice':'xiaoxiao'}); r.raise_for_status(); p=Path(d)/f'{i}.mp3'; p.write_bytes(r.content); files.append(p)
    listing=Path(d)/'list.txt'; listing.write_text(''.join(f"file '{p.as_posix()}'\n" for p in files),encoding='ascii'); voice=Path(d)/'voice.mp3'
    subprocess.run([str(ff),'-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(voice)],check=True,capture_output=True)
    subprocess.run([str(ff),'-y','-i',str(src),'-i',str(voice),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','128k','-shortest',str(dst)],check=True,capture_output=True)
print(dst,dst.stat().st_size)
