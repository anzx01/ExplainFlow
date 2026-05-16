import asyncio
import tempfile
from pathlib import Path

import edge_tts

VOICES: dict[str, str] = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",
    "yunxi": "zh-CN-YunxiNeural",
    "xiaoyi": "zh-CN-XiaoyiNeural",
}


async def synthesize(text: str, voice_key: str = "xiaoxiao") -> Path:
    voice = VOICES[voice_key]
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    out_path = Path(tmp.name)

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_path))
    return out_path


async def synthesize_scenes(scenes: list[dict], voice_key: str = "xiaoxiao") -> list[Path]:
    tasks = [synthesize(scene["narration"], voice_key) for scene in scenes]
    return await asyncio.gather(*tasks)
