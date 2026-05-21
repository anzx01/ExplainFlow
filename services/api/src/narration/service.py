import asyncio
import os
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

import edge_tts

VOICES: dict[str, str] = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",
    "yunxi": "zh-CN-YunxiNeural",
    "xiaoyi": "zh-CN-XiaoyiNeural",
}


def _create_uuid_temp_path(suffix: str) -> Path:
    """Create a temp file with UUID-based name to avoid concurrent conflicts."""
    return Path(tempfile.gettempdir()) / f"explainflow_tts_{uuid4()}{suffix}"


def _cleanup_temp_file(path: Path) -> None:
    """Safely remove a temp file, ignoring errors."""
    try:
        if path.exists():
            path.unlink(missing_ok=True)
    except Exception:
        pass


def _synthesize_with_windows_sapi(text: str) -> Path:
    wav_path = _create_uuid_temp_path(".wav")
    mp3_path = _create_uuid_temp_path(".mp3")

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
        _cleanup_temp_file(wav_path)


async def synthesize(text: str, voice_key: str = "xiaoxiao") -> Path:
    voice = VOICES[voice_key]
    out_path = _create_uuid_temp_path(".mp3")

    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out_path))
        if out_path.exists() and out_path.stat().st_size >= 512:
            return out_path
        raise RuntimeError("No usable audio was received from Edge TTS")
    except Exception:
        _cleanup_temp_file(out_path)
        return await asyncio.to_thread(_synthesize_with_windows_sapi, text)


async def synthesize_scenes(scenes: list[dict], voice_key: str = "xiaoxiao") -> list[Path]:
    tasks = [synthesize(scene["narration"], voice_key) for scene in scenes]
    return await asyncio.gather(*tasks)
