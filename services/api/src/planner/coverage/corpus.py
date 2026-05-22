import json
import re

from src.explain.models import ExplainGraph
from ..models import Scene, Storyboard
from ..storyboard_gen.normalizer import _clean_text


def _graph_enhanced_brief(graph: ExplainGraph) -> dict | None:
    brief = getattr(graph, "enhanced_brief", None)
    if not brief:
        return None
    if hasattr(brief, "model_dump"):
        return brief.model_dump(mode="json")
    if isinstance(brief, dict):
        return brief
    return None

def _storyboard_corpus(storyboard: Storyboard, graph: ExplainGraph) -> str:
    brief = _graph_enhanced_brief(graph) or {}
    parts = [graph.topic, graph.summary, " ".join(graph.key_insights), json.dumps(brief, ensure_ascii=False)]
    for scene in storyboard.scenes:
        parts.extend([scene.title, scene.narration, scene.learning_goal or "", scene.image_description or ""])
        if scene.diagram_plan:
            parts.append(scene.diagram_plan.kind)
            parts.append(scene.diagram_plan.layout)
            parts.extend(scene.diagram_plan.required_labels)
        for beat in scene.visual_beats:
            parts.extend([beat.draw_intent, beat.narration, *beat.required_labels])
        for animation in scene.animations:
            parts.append(animation.content)
            parts.append(animation.latex or "")
            if animation.items:
                parts.extend(animation.items)
    return " ".join(part for part in parts if part).lower()


def _graph_source_corpus(graph: ExplainGraph) -> str:
    brief = _graph_enhanced_brief(graph) or {}
    parts = [graph.topic, graph.summary, " ".join(graph.key_insights)]
    if isinstance(brief, dict):
        parts.extend(
            [
                _clean_text(brief.get("original_prompt")),
                _clean_text(brief.get("topic_type")),
                json.dumps(brief.get("must_include_points") or [], ensure_ascii=False),
                json.dumps(brief.get("learning_objectives") or [], ensure_ascii=False),
            ]
        )
    return " ".join(part for part in parts if part).lower()


def _storyboard_scene_corpus(storyboard: Storyboard) -> str:
    parts: list[str] = []
    for scene in storyboard.scenes:
        parts.extend([scene.title, scene.narration, scene.learning_goal or "", scene.image_description or ""])
        if scene.diagram_plan:
            parts.append(scene.diagram_plan.kind)
            parts.append(scene.diagram_plan.layout)
            parts.extend(scene.diagram_plan.required_labels)
        for beat in scene.visual_beats:
            parts.extend([beat.draw_intent, beat.narration, *beat.required_labels])
        for animation in scene.animations:
            parts.append(animation.content)
            parts.append(animation.latex or "")
            if animation.items:
                parts.extend(animation.items)
    return " ".join(part for part in parts if part).lower()


def _contains_terms(corpus: str, terms: list[str]) -> bool:
    return any(term.lower() in corpus for term in terms)


def _scene_corpus(scene: Scene) -> str:
    parts: list[str] = [scene.title, scene.narration, scene.learning_goal or "", scene.image_description or ""]
    if scene.diagram_plan:
        parts.extend([scene.diagram_plan.kind, scene.diagram_plan.layout])
        parts.extend(scene.diagram_plan.required_labels)
    for beat in getattr(scene, "visual_beats", []) or []:
        parts.extend([beat.draw_intent, beat.narration])
        parts.extend(beat.required_labels)
    for animation in scene.animations:
        parts.append(getattr(animation.type, "value", str(animation.type)))
        parts.extend(
            [
                animation.content or "",
                animation.latex or "",
                animation.from_node or "",
                animation.to_node or "",
            ]
        )
        if animation.items:
            parts.extend(animation.items)
    return " ".join(part for part in parts if part).lower()


