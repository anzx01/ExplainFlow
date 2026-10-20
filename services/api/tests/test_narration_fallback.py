import asyncio
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from src.narration import service


class UnavailableEdge:
    def __init__(self, *args):
        pass

    async def save(self, path):
        raise RuntimeError("edge unavailable")


def test_unavailable_voice_providers_fail_instead_of_returning_silence(monkeypatch):
    def unavailable_sapi(text):
        raise RuntimeError("sapi unavailable")

    monkeypatch.setattr(service.edge_tts, "Communicate", UnavailableEdge)
    monkeypatch.setattr(service, "_synthesize_with_windows_sapi", unavailable_sapi)
    with pytest.raises(RuntimeError, match="配音生成失败"):
        asyncio.run(service.synthesize("必须有真实配音。"))


def test_local_voice_is_used_when_online_voice_fails(monkeypatch, tmp_path):
    voice_path = tmp_path / "local.mp3"
    monkeypatch.setattr(service.edge_tts, "Communicate", UnavailableEdge)
    monkeypatch.setattr(service, "_synthesize_with_windows_sapi", lambda text: voice_path)
    assert asyncio.run(service.synthesize("使用本地语音。")) == voice_path
