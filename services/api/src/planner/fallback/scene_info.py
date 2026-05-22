import re

from ..models import Scene, AnimationInstruction
from ..storyboard_gen.normalizer import _clean_text, _subtitle_text
from .cooking_terms import (
    COOKING_TOPIC_TERMS,
    COOKING_BLANCH_TERMS,
    COOKING_PREP_TERMS,
    COOKING_FINAL_TERMS,
    COOKING_OVERVIEW_TERMS,
    COOKING_DENSE_LAYOUT_TERMS,
)
from .geometry import _short_text
from src.core.visual_prompts import BOLD_EDITORIAL_IMAGE_DESCRIPTION_HINT

def _animation_lines(scene: Scene) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()

    def add_line(value: str | None, max_chars: int = 22) -> None:
        text = _short_text(value, max_chars)
        if not text or text in seen:
            return
        seen.add(text)
        lines.append(text)

    if scene.diagram_plan:
        for label in scene.diagram_plan.required_labels[:4]:
            add_line(label, 22)

    for beat in getattr(scene, "visual_beats", []) or []:
        if beat.required_labels:
            for label in beat.required_labels[:3]:
                add_line(label, 22)
        elif beat.narration and len(lines) < 2:
            add_line(beat.narration, 18)
        if len(lines) >= 5:
            break
    for animation in scene.animations:
        raw_type = getattr(animation.type, "value", str(animation.type))
        if raw_type in {"write_formula", "formula_reveal"}:
            value = animation.latex or animation.content
            if value:
                add_line(value, 28)
        elif animation.items:
            if animation.content:
                add_line(animation.content, 20)
            for item in animation.items[:3]:
                add_line(item, 20)
        elif animation.content:
            add_line(animation.content, 20)
    if not lines:
        return []
    return lines[:4]


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


def _animation_type_values(scene: Scene) -> set[str]:
    return {getattr(animation.type, "value", str(animation.type)) for animation in scene.animations}


def _contains_any(corpus: str, terms: list[str]) -> bool:
    return any(term.lower() in corpus for term in terms)


def _is_cooking_topic_text(corpus: str) -> bool:
    return _contains_any(corpus, list(COOKING_TOPIC_TERMS))


def _cooking_prompt_suffix(corpus: str) -> str:
    if not _is_cooking_topic_text(corpus):
        return ""
    parts = [
        BOLD_EDITORIAL_IMAGE_DESCRIPTION_HINT,
        "Food/cooking accuracy: make the visual concrete and appetizing, not generic. Show correct cookware, ingredients, sauce color, steam, garnish, and real cooking state.",
        "Use real food colors: red/orange chili oil or sauce, white tofu cubes, brown minced meat, green scallions or garlic sprouts, warm highlights.",
        "Use one large food or cookware state as the primary visual anchor; avoid dense rows of many tiny pots, mini process boxes, or small unreadable recipe captions.",
        "Text policy: keep generated artwork text-free; the video renderer will add Chinese title, labels, ticks, underlines, and callouts.",
    ]
    if "mapo" in corpus or "麻婆" in corpus or "豆瓣" in corpus:
        parts.append(
            "For mapo tofu, always show recognizable Sichuan mapo tofu: white tofu cubes in glossy red chili-bean sauce, brown minced meat, green garlic sprouts/scallions, Sichuan pepper speckles, and red oil."
        )
    is_prep = _contains_any(corpus, list(COOKING_PREP_TERMS))
    is_final = _contains_any(corpus, list(COOKING_FINAL_TERMS))
    is_blanch = _contains_any(corpus, list(COOKING_BLANCH_TERMS))
    if is_final:
        parts.append("Finished scene: show a shallow white plate or bowl filled with the colorful finished dish.")
    elif is_prep:
        parts.append("Preparation scene: show cutting board and small ingredient bowls; do not use an empty pot as the main object.")
    elif _contains_any(corpus, list(COOKING_OVERVIEW_TERMS)):
        parts.append("Overview scene: show at most three large illustrated cooking states, or one finished dish with 3-5 flavor callouts; do not use a five-step row of tiny pots.")
    elif is_blanch:
        parts.append("Blanching scene: a pot of boiling clear water is acceptable only here, with tofu cubes and steam.")
    else:
        parts.append("Stir-fry/simmer/thickening scene: use a wide black Chinese wok or skillet on a burner, not a blue soup pot or empty stockpot.")
    return " ".join(parts)


def _is_dense_cooking_scene(scene: Scene) -> bool:
    corpus = _scene_corpus(scene)
    if not _is_cooking_topic_text(corpus):
        return False
    label_count = len(scene.diagram_plan.required_labels) if scene.diagram_plan else 0
    beat_count = len(scene.visual_beats or [])
    animation_item_count = sum(len(animation.items or []) for animation in scene.animations)
    dense_terms = _contains_any(corpus, list(COOKING_DENSE_LAYOUT_TERMS))
    too_many_labels = label_count >= 7 or animation_item_count >= 8
    too_many_beats = beat_count >= 5
    return dense_terms or too_many_labels or too_many_beats


