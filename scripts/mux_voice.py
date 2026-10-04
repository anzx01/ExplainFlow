from pathlib import Path
import subprocess, tempfile

root = Path(__file__).parents[1]
ff = root / 'apps/render/node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe'
src = root / 'outputs/How_to_make_Chinese_dumplings_flour_to_boiling_d39d4728.mp4'
dst = root / 'outputs/How_to_make_Chinese_dumplings_flour_to_boiling_with_voice.mp4'
files = sorted((root / 'outputs/audio').glob('tts_*.mp3'))[:6]
with tempfile.TemporaryDirectory() as d:
    listing = Path(d) / 'list.txt'
    voice = Path(d) / 'voice.mp3'
    listing.write_text(''.join(f"file '{p.as_posix()}'\n" for p in files), encoding='ascii')
    subprocess.run([str(ff), '-y', '-f', 'concat', '-safe', '0', '-i', str(listing), '-c', 'copy', str(voice)], check=True, capture_output=True)
    subprocess.run([str(ff), '-y', '-i', str(src), '-i', str(voice), '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', '-shortest', str(dst)], check=True, capture_output=True)
print(dst, dst.stat().st_size)
