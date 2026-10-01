import asyncio
import logging
import os
import subprocess
import tempfile
import wave
from pathlib import Path
from uuid import uuid4

import edge_tts
import imageio_ffmpeg

logger = logging.getLogger(__name__)

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
                imageio_ffmpeg.get_ffmpeg_exe(),
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


def _synthesize_silence(text: str) -> Path:
    """Create deterministic offline fallback audio so local rendering remains testable."""
    wav_path = _create_uuid_temp_path(".wav")
    mp3_path = _create_uuid_temp_path(".mp3")
    duration = max(1.5, min(30.0, len(text.strip()) / 5.0 + 0.8))
    sample_rate = 24_000
    try:
        with wave.open(str(wav_path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            handle.writeframes(b"\x00\x00" * int(sample_rate * duration))
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
                "-i", str(wav_path), "-codec:a", "libmp3lame", "-b:a", "64k", str(mp3_path),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        if not mp3_path.exists() or mp3_path.stat().st_size < 512:
            raise RuntimeError("Offline TTS fallback did not create usable audio")
        logger.warning("TTS providers unavailable; using %.1fs offline silent fallback audio", duration)
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
    except Exception as edge_error:
        _cleanup_temp_file(out_path)
        try:
            return await asyncio.to_thread(_synthesize_with_windows_sapi, text)
        except Exception as sapi_error:
            logger.warning("Edge TTS failed (%s); Windows SAPI failed (%s)", edge_error, sapi_error)
            return await asyncio.to_thread(_synthesize_silence, text)


async def synthesize_scenes(scenes: list[dict], voice_key: str = "xiaoxiao") -> list[Path]:
    tasks = [synthesize(scene["narration"], voice_key) for scene in scenes]
    return await asyncio.gather(*tasks)
