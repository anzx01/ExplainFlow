import math
import re

from ..models import Scene
from ..storyboard_gen.normalizer import _clean_text, _canonical_video_style
from .geometry import (
    _short_text,
    _text_visual_width,
    _point,
    _text_stroke_points,
    _curve_points,
    _rect_points,
    _circle_points,
    _line_points,
    _polyline_length,
    _path_from_points,
    _arc_points,
    _diamond_points,
)
from .scene_info import _animation_lines, _contains_any
from .scene_diagram import _diagram_kind_for_scene, _scene_steps
from .scene_extra import _scene_extra, _audio_segments_for_scene


_ACCENT_PALETTE_BY_STYLE = {
    "chalkboard_bw": ["#F4F2E8"],
    "chalkboard_color": ["#5DE6FF", "#F2E85C", "#A8F06A"],
    "modern_minimal": ["#5D6FE8", "#8790A0"],
    "technical_blueprint": ["#7CC7E8", "#D66767", "#A5D6E8"],
    "editorial": ["#D85C4A", "#D9A514", "#111318"],
    "whiteboard": ["#2F6FB2", "#3F8F68", "#F3BE22", "#D85C4A"],
    "playful": ["#F06E6E", "#F1C84B", "#42B8A7", "#7A65B8"],
    "sharpie": ["#111318", "#2F6FB2", "#F3BE22", "#D85C4A"],
}

_ALLOWED_VISUAL_STYLES = {
    "teacher_whiteboard",
    "marketing_doodle",
    "math_chalkboard",
    "technical_reference",
    "modern_minimal",
    "editorial",
    "playful",
    "sharpie",
}


class FallbackSceneBuilder:
    """Builds a fallback scene spec from a Scene object."""

    def __init__(
        self,
        scene: Scene,
        scene_index: int,
        fps: int,
        width: int,
        height: int,
    ) -> None:
        self.scene = scene
        self.scene_index = scene_index
        self.fps = fps
        self.width = width
        self.height = height

        audio_segments, timing_duration, transition_frames = _audio_segments_for_scene(scene, fps)
        self.audio_segments: list[dict] = audio_segments
        self.transition_frames = transition_frames
        self.duration = max(fps * 8, round(scene.duration_estimate * fps), timing_duration)

        board_mode = (_clean_text(_scene_extra(scene, "board_mode") or _scene_extra(scene, "boardMode")) or "whiteboard").lower()
        hand_usage = (_clean_text(_scene_extra(scene, "hand_usage") or _scene_extra(scene, "handUsage")) or "trace").lower()
        video_style = _canonical_video_style(
            _scene_extra(scene, "video_style") or _scene_extra(scene, "videoStyle") or _scene_extra(scene, "visual_style")
        )
        visual_style = (_clean_text(_scene_extra(scene, "visual_style") or _scene_extra(scene, "visualStyle")) or "teacher_whiteboard").lower()

        if board_mode not in {"whiteboard", "chalkboard", "clean_canvas", "reference"}:
            board_mode = "whiteboard"
        if hand_usage not in {"trace", "annotate", "none"}:
            hand_usage = "trace"
        if visual_style not in _ALLOWED_VISUAL_STYLES:
            visual_style = "teacher_whiteboard"
        if board_mode == "chalkboard" or visual_style == "math_chalkboard":
            board_mode = "chalkboard"
            hand_usage = "none"
            visual_style = "math_chalkboard"
        if video_style in {"chalkboard_bw", "chalkboard_color"}:
            board_mode = "chalkboard"
            hand_usage = "none"
            visual_style = "math_chalkboard"

        self.board_mode = board_mode
        self.hand_usage = hand_usage
        self.video_style = video_style
        self.visual_style = visual_style

        self.left = width * 0.065
        self.top = height * 0.055
        self.diagram_left = width * 0.18
        self.diagram_top = height * 0.19
        self.board_center_x = width * 0.50
        self.board_draw_w = width * 0.64
        self.board_draw_h = height * 0.56

        accent_colors = _ACCENT_PALETTE_BY_STYLE.get(video_style, ["#FFD65A", "#FF4F7B", "#A8D8F0", "#BFE3C0", "#D7C5F7"])
        self.accent_colors = accent_colors
        self.accent = accent_colors[scene_index % len(accent_colors)]

        is_chalkboard = board_mode == "chalkboard"
        self.is_chalkboard = is_chalkboard
        self.ink = "#F4F2E8" if is_chalkboard else "#1D1D1F"
        self.blue = "#5DE6FF" if is_chalkboard else "#2F6FB2"
        self.red = "#FF6FAE" if is_chalkboard else "#FF4F7B"
        self.green = "#A8F06A" if is_chalkboard else "#3F8F68"
        self.violet = "#C6A7FF" if is_chalkboard else "#6E58B5"
        self.yellow = "#F2E85C" if is_chalkboard else "#F3BE22"
        if video_style == "technical_blueprint":
            self.ink, self.blue, self.red, self.green, self.violet, self.yellow = "#B8D7E8", "#7CC7E8", "#D66767", "#8AC7B4", "#9FB7D8", "#D7B85A"
        elif video_style == "modern_minimal":
            self.ink, self.blue, self.red, self.green, self.violet, self.yellow = "#22242A", "#5D6FE8", "#C85C5C", "#5E8E77", "#6A5ACD", "#D9B84C"
        elif video_style == "editorial":
            self.ink, self.blue, self.red, self.green, self.violet, self.yellow = "#121212", "#2F5E8E", "#D85C4A", "#4F8068", "#6E58B5", "#D9A514"
        elif video_style == "playful":
            self.ink, self.blue, self.red, self.green, self.violet, self.yellow = "#34302B", "#42B8D0", "#F06E6E", "#60B56A", "#7A65B8", "#F1C84B"
        elif video_style == "sharpie":
            self.ink, self.blue, self.red, self.green, self.violet, self.yellow = "#111111", "#2F6FB2", "#D85C4A", "#3F8F68", "#6E58B5", "#F3BE22"

        self.draw_ops: list[dict] = []
        self.texts: list[dict] = []
        self.text_boxes: list[dict[str, float]] = []
        self.strokes: list[dict] = []
        self.raster_reveal_spec: dict | None = None
        self.body_size = 26

        self.diagram_kind = _diagram_kind_for_scene(scene, scene_index)
        self.core_lines = _animation_lines(scene)
        self.steps = _scene_steps(scene)

        raw_trace_strokes = _scene_extra(scene, "trace_strokes") or _scene_extra(scene, "traceStrokes") or []
        self.trace_strokes = raw_trace_strokes if isinstance(raw_trace_strokes, list) else []
        raw_raster_reveal = _scene_extra(scene, "rasterReveal") or _scene_extra(scene, "raster_reveal") or {}
        self.raster_reveal = raw_raster_reveal if isinstance(raw_raster_reveal, dict) else {}
        self.raster_strokes = self.raster_reveal.get("strokes") if isinstance(self.raster_reveal.get("strokes"), list) else []
        self.reference_image_asset = (
            _scene_extra(scene, "referenceImageAsset")
            or _scene_extra(scene, "reference_image_asset")
            or self.raster_reveal.get("asset")
        )
        self.annotation_plan = [
            item
            for item in (getattr(scene, "annotation_plan", []) or [])
            if _clean_text(getattr(item, "layer", "renderer")) == "renderer"
        ]
        self.visual_anchor = _clean_text(getattr(scene, "visual_anchor", "") or "")

    def fit_timing(self, start: int, frames: int) -> tuple[int, int]:
        safe_start = min(max(0, start), max(0, self.duration - 8))
        safe_end = min(self.duration - 4, safe_start + max(4, frames))
        if safe_end <= safe_start:
            safe_end = min(self.duration - 1, safe_start + 1)
        return safe_start, safe_end

    def text_box_for(self, value: str, x: float, y: float, font_size: int, max_width: float) -> dict[str, float]:
        visual_width = _text_visual_width(value, font_size)
        line_count = max(1, int(math.ceil(visual_width / max(1.0, max_width))))
        box_width = min(max_width, max(font_size * 1.35, visual_width if line_count == 1 else max_width))
        box_height = font_size * (1.20 * line_count)
        return {"x": x - 10, "y": y - 8, "w": box_width + 20, "h": box_height + 14}

    def boxes_overlap(self, first: dict[str, float], second: dict[str, float], pad: float = 6.0) -> bool:
        return not (
            first["x"] + first["w"] + pad <= second["x"]
            or second["x"] + second["w"] + pad <= first["x"]
            or first["y"] + first["h"] + pad <= second["y"]
            or second["y"] + second["h"] + pad <= first["y"]
        )

    def resolve_text_position(
        self, value: str, x: float, y: float, font_size: int, max_width: float, max_chars: int
    ) -> tuple[float, float, dict[str, float]]:
        visual_width = min(max_width, max(font_size * 1.35, _text_visual_width(value, font_size)))
        box_height = font_size * 1.34
        clamped_x = max(self.width * 0.035, min(float(x), self.width - visual_width - self.width * 0.035))
        clamped_y = max(self.height * 0.035, min(float(y), self.height - box_height - self.height * 0.045))
        should_avoid = len(re.sub(r"\s+", "", value)) > 1 and max_chars > 1 and max_width > self.width * 0.055
        if not should_avoid:
            return clamped_x, clamped_y, self.text_box_for(value, clamped_x, clamped_y, font_size, max_width)
        step = max(font_size * 1.12, self.height * 0.040)
        candidates = [(clamped_x, clamped_y)]
        for offset in range(1, 5):
            candidates.append((clamped_x, clamped_y + step * offset))
            candidates.append((clamped_x, clamped_y - step * offset))
        candidates.extend([
            (clamped_x + self.width * 0.055, clamped_y),
            (clamped_x - self.width * 0.055, clamped_y),
            (clamped_x + self.width * 0.055, clamped_y + step),
            (clamped_x - self.width * 0.055, clamped_y + step),
        ])
        for candidate_x, candidate_y in candidates:
            safe_x = max(self.width * 0.035, min(candidate_x, self.width - visual_width - self.width * 0.035))
            safe_y = max(self.height * 0.035, min(candidate_y, self.height - box_height - self.height * 0.045))
            candidate_box = self.text_box_for(value, safe_x, safe_y, font_size, max_width)
            if all(not self.boxes_overlap(candidate_box, existing) for existing in self.text_boxes):
                return safe_x, safe_y, candidate_box
        return clamped_x, clamped_y, self.text_box_for(value, clamped_x, clamped_y, font_size, max_width)

    def beat_id_for(self, index: int) -> str | None:
        if 0 <= index < len(self.audio_segments):
            raw_id = self.audio_segments[index].get("id")
            return str(raw_id) if raw_id else f"beat_{index}"
        return f"beat_{index}" if self.audio_segments else None

    def title_x_for_text(self, text: str, font_size: int) -> float:
        return self.left
