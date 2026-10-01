import pytest

from src.planner.srt_timeline import SrtParseError, build_srt_timeline, group_scenes, parse_srt


def test_parse_srt_accepts_bom_comma_and_dot_milliseconds():
    timeline = build_srt_timeline(
        "\ufeff1\n00:00:00,000 --> 00:00:02,500\n第一步\n\n2\n00:00:03.50 --> 00:00:05.000\n第二步"
    )
    assert timeline["cues"][0]["endMs"] == 2500
    assert timeline["cues"][1]["startMs"] == 3500
    assert timeline["totalDurationMs"] == 5000


def test_group_scenes_splits_at_maximum_duration():
    cues = parse_srt("\n\n".join(
        f"{i}\n00:00:{i-1:02d},000 --> 00:00:{i:02d},000\ncue {i}" for i in range(1, 5)
    ))
    scenes = group_scenes(cues, target_sec=2, min_sec=1, max_sec=2.5)
    assert [scene["cueIds"] for scene in scenes] == [[1, 2], [3, 4]]


@pytest.mark.parametrize("srt", [
    "1\n00:00:02,000 --> 00:00:01,000\nbackwards",
    "1\n00:00:00,000 --> 00:00:01,000",
])
def test_invalid_srt_has_actionable_error(srt: str):
    with pytest.raises(SrtParseError):
        parse_srt(srt)
