import asyncio
import os
import subprocess
import tempfile
from pathlib import Path

import edge_tts

VOICES: dict[str, str] = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",
    "yunxi": "zh-CN-YunxiNeural",
    "xiaoyi": "zh-CN-XiaoyiNeural",
}


def _synthesize_with_windows_sapi(text: str) -> Path:
    wav_tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    wav_tmp.close()
    wav_path = Path(wav_tmp.name)
    mp3_tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    mp3_tmp.close()
    mp3_path = Path(mp3_tmp.name)

    env = os.environ.copy()
    env["EXPLAINFLOW_TTS_TEXT"] = text
    env["EXPLAINFLOW_TTS_WAV"] = str(wav_path)
    script = r"""
Add-Type -AssemblyName System.Speech
$text = [Environment]::GetEnvironmentVariable('EXPLAINFLOW_TTS_TEXT')
$out = [Environment]::GetEnvironmentVariable('EXPLAINFLOW_TTS_WAV')
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $culture = New-Object System.Globalization.CultureInfo('zh-CN')
  $synth.SelectVoiceByHints(
    [System.Speech.Synthesis.VoiceGender]::Female,
    [System.Speech.Synthesis.VoiceAge]::Adult,
    0,
    $culture
  )
} catch {}
$synth.Rate = 0
$synth.Volume = 100
$synth.SetOutputToWaveFile($out)
$synth.Speak($text)
$synth.Dispose()
"""
    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            env=env,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if not wav_path.exists() or wav_path.stat().st_size < 512:
            raise RuntimeError("Windows SAPI did not create usable WAV audio")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(wav_path),
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "96k",
                str(mp3_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if not mp3_path.exists() or mp3_path.stat().st_size < 512:
            raise RuntimeError("ffmpeg did not create usable MP3 audio")
        return mp3_path
    finally:
        try:
            wav_path.unlink(missing_ok=True)
        except Exception:
            pass


async def synthesize(text: str, voice_key: str = "xiaoxiao") -> Path:
    voice = VOICES[voice_key]
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    out_path = Path(tmp.name)

    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out_path))
        if out_path.exists() and out_path.stat().st_size >= 512:
            return out_path
        raise RuntimeError("No usable audio was received from Edge TTS")
    except Exception:
        try:
            out_path.unlink(missing_ok=True)
        except Exception:
            pass
        return await asyncio.to_thread(_synthesize_with_windows_sapi, text)


async def synthesize_scenes(scenes: list[dict], voice_key: str = "xiaoxiao") -> list[Path]:
    tasks = [synthesize(scene["narration"], voice_key) for scene in scenes]
    return await asyncio.gather(*tasks)
