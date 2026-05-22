from ..models import Scene
from . import FallbackSceneBuilder  # triggers all monkey-patches via __init__.py


def _build_fallback_scene_spec(
    scene: Scene,
    scene_index: int,
    fps: int,
    width: int,
    height: int,
) -> dict:
    return FallbackSceneBuilder(scene, scene_index, fps, width, height).build()
