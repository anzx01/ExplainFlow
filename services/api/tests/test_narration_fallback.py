from pathlib import Path

from src.narration.service import _synthesize_silence


def test_offline_narration_fallback_creates_mp3():
    path = _synthesize_silence("离线渲染也需要稳定的音频时间轴。")
    try:
        assert path.suffix == ".mp3"
        assert path.exists()
        assert path.stat().st_size > 512
    finally:
        Path(path).unlink(missing_ok=True)
