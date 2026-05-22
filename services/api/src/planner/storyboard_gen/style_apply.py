from ..models import Scene
from .normalizer import (
    _clean_text,
    _normalize_image_description_text,
    _canonical_video_style,
    _normalize_video_style,
    _video_style_preset,
    _normalize_pen_style,
    _style_image_rule_in_description,
    ACTIVE_VIDEO_STYLE,
    ACTIVE_PEN_STYLE,
)
from ..coverage.corpus import _scene_corpus, _contains_terms

def _apply_video_style_to_scene(scene: Scene, video_style: str) -> None:
    style = _canonical_video_style(video_style)
    if style == "auto":
        return
    preset = _video_style_preset(style)
    scene.video_style = style
    scene_corpus = _scene_corpus(scene)
    is_math_scene = _contains_terms(
        scene_corpus,
        [
            "数学",
            "解题",
            "证明",
            "公式推导",
            "derivation",
            "proof",
            "equation",
            "formula",
            "plane normal",
            "perpendicular",
            "parametric",
            "iit",
            "gradient descent",
            "梯度下降",
            "loss function",
            "损失函数",
            "learning rate",
            "学习率",
        ],
    )
    is_reference_scene = _contains_terms(
        scene_corpus,
        [
            "reference",
            "cross-section",
            "cross section",
            "3d",
            "三维",
            "截面",
            "剖面",
            "电路",
            "医学",
            "机械",
            "多层",
            "interface",
            "ui",
        ],
    )

    if style in {"chalkboard_bw", "chalkboard_color"}:
        scene.board_mode = "chalkboard"
        scene.hand_usage = "none"
        scene.visual_style = "math_chalkboard"
        scene.render_strategy = "trace"
    elif style == "technical_blueprint":
        scene.board_mode = "reference"
        scene.hand_usage = "annotate"
        scene.visual_style = "technical_reference"
        scene.render_strategy = "hybrid"
    elif style == "whiteboard":
        if is_math_scene:
            scene.board_mode = "whiteboard"
            scene.hand_usage = "trace"
            scene.visual_style = "teacher_whiteboard"
            scene.render_strategy = scene.render_strategy or "trace"
        elif is_reference_scene and (scene.visual_complexity or "").lower() in {"dense", "reference"}:
            scene.board_mode = "reference"
            scene.hand_usage = "annotate"
            scene.visual_style = "technical_reference"
            scene.render_strategy = "hybrid"
        else:
            # Default to teacher_whiteboard for whiteboard style (user's expected behavior)
            scene.board_mode = "whiteboard"
            scene.hand_usage = "trace"
            scene.visual_style = "teacher_whiteboard"
            scene.render_strategy = scene.render_strategy or "trace"
    elif style in {"modern_minimal", "editorial", "playful", "sharpie"}:
        scene.board_mode = "clean_canvas"
        scene.hand_usage = "annotate" if style != "sharpie" else "trace"
        scene.visual_style = style
        scene.render_strategy = "hybrid" if style != "sharpie" else "hybrid"

    image_rule = preset["image_rule"]
    if scene.image_description and not _style_image_rule_in_description(scene, style):
        scene.image_description = f"{scene.image_description}. {image_rule}".strip(". ")
    scene.image_description = _normalize_image_description_text(scene.image_description)


def _apply_pen_style_to_scene(scene: Scene, pen_style: str) -> None:
    style = _normalize_pen_style(pen_style)
    scene.pen_style = style
    if style == "no_hand" or scene.board_mode == "chalkboard" or scene.visual_style == "math_chalkboard":
        scene.hand_usage = "none"
        scene.pen_style = "no_hand"
        return
    if not scene.hand_usage or scene.hand_usage == "none":
        scene.hand_usage = "annotate"
    # For teacher_whiteboard style, keep trace hand_usage regardless of pen_style
    if scene.visual_style == "teacher_whiteboard" and scene.hand_usage == "annotate":
        scene.hand_usage = "trace"
    if style == "marker" and scene.hand_usage == "trace" and scene.video_style not in {"sharpie"} and scene.visual_style not in {"teacher_whiteboard"}:
        scene.hand_usage = "annotate"


