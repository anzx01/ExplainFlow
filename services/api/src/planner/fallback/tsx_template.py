import json

from ..models import Storyboard
from ..storyboard_gen.normalizer import _subtitle_text
from .spec import _build_fallback_scene_spec
from ._tsx_template_string import _WHITEBOARD_TSX_TEMPLATE


def _build_fallback_remotion_tsx(
    storyboard: Storyboard,
    fps: int,
    width: int,
    height: int,
    subtitles_enabled: bool = False,
    background_music_url: str | None = None,
    background_music_volume: float = 0.12,
) -> tuple[str, int]:
    scene_specs = [
        _build_fallback_scene_spec(scene, index, fps, width, height)
        for index, scene in enumerate(storyboard.scenes)
    ]
    for scene_spec, scene in zip(scene_specs, storyboard.scenes):
        scene_spec["subtitleText"] = _subtitle_text(scene.narration) if subtitles_enabled else None
        if not subtitles_enabled:
            for segment in scene_spec.get("audioSegments") or []:
                segment["subtitleText"] = None
    if not scene_specs:
        raise ValueError("Cannot build fallback Remotion TSX without storyboard scenes")
    duration = sum(scene["duration"] for scene in scene_specs)
    scenes_json = json.dumps(scene_specs, ensure_ascii=False, separators=(",", ":"))
    return (
        _WHITEBOARD_TSX_TEMPLATE.replace("__SCENES_JSON__", scenes_json)
        .replace("__VIDEO_WIDTH__", str(width))
        .replace("__VIDEO_HEIGHT__", str(height))
        .replace("__BACKGROUND_MUSIC_URL__", json.dumps(background_music_url))
        .replace("__BACKGROUND_MUSIC_VOLUME__", str(max(0.0, min(0.5, background_music_volume))))
        .replace("__SUBTITLES_ENABLED__", "true" if subtitles_enabled else "false")
        .strip(),
        duration,
    )
