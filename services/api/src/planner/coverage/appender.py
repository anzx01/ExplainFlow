from src.explain.models import ExplainGraph
from ..models import Scene, Storyboard
from .analyzer import _missing_coverage_units, _brief_coverage_units
from .specs import _coverage_scene_spec, _scene_from_spec
from .corpus import _storyboard_scene_corpus
from ..storyboard_gen.normalizer import _clean_text, _normalize_image_description_text, _clean_narration_text
from ..storyboard_gen.timing import _max_scene_count_for_target, _narration_from_beats

def _replace_with_specs(storyboard: Storyboard, specs: list[dict]) -> Storyboard:
    scenes = [_scene_from_spec(index, spec) for index, spec in enumerate(specs)]
    for scene in scenes:
        if scene.image_description:
            scene.image_description = _normalize_image_description_text(scene.image_description)
    return Storyboard(
        topic=storyboard.topic,
        total_duration_estimate=round(sum(scene.duration_estimate for scene in scenes), 1),
        scenes=scenes,
        video_style=storyboard.video_style,
        pen_style=storyboard.pen_style,
    )


def _append_missing_coverage_scenes(storyboard: Storyboard, graph: ExplainGraph, target_duration: int, limit: int | None = None) -> Storyboard:
    missing = _missing_coverage_units(storyboard, graph)
    if not missing:
        return storyboard
    effective_limit = limit if limit is not None else _max_scene_count_for_target(target_duration)
    room = max(0, effective_limit - len(storyboard.scenes))
    protected_ids = {id(scene) for scene in _protected_coverage_scenes(storyboard, graph, max(1, len(storyboard.scenes)))}
    for unit in missing:
        scene = _scene_from_spec(
            len(storyboard.scenes),
            _coverage_scene_spec(unit, len(storyboard.scenes), graph.topic),
        )
        if room > 0:
            storyboard.scenes.append(scene)
            protected_ids.add(id(scene))
            room -= 1
            continue
        replace_at = _replaceable_scene_index(storyboard.scenes, protected_ids)
        if replace_at is None:
            continue
        storyboard.scenes[replace_at] = scene
        protected_ids.add(id(scene))
    for index, scene in enumerate(storyboard.scenes):
        scene.order = index
        scene.id = f"scene_{index}"
    storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
    return storyboard


def _sanitize_storyboard_narration(storyboard: Storyboard) -> Storyboard:
    for scene in storyboard.scenes:
        for beat in scene.visual_beats:
            beat.narration = _clean_narration_text(beat.narration)
        scene.narration = _narration_from_beats(scene.narration, scene.visual_beats)
    return storyboard



