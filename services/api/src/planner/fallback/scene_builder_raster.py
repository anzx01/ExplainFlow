import math

from .scene_builder_base import FallbackSceneBuilder
from .geometry import _point, _curve_points, _line_points, _polyline_length, _path_from_points, _text_visual_width
from ..storyboard_gen.normalizer import _clean_text


def build_raster_reveal(self, start: int) -> int:
    if not self.reference_image_asset or not self.raster_reveal:
        return self.build_process_flow(start)

    image_w = float(self.raster_reveal.get("imageWidth") or self.raster_reveal.get("image_width") or 1)
    image_h = float(self.raster_reveal.get("imageHeight") or self.raster_reveal.get("image_height") or 1)
    image_aspect = max(0.1, image_w / max(1.0, image_h))
    render_mode = _clean_text(self.raster_reveal.get("renderMode") or self.raster_reveal.get("render_mode")).lower()

    if render_mode == "direct":
        region_x = self.width * 0.18
        region_y = self.height * 0.17
        region_w = self.width * 0.64
        region_h = self.height * 0.62
    else:
        region_x = self.width * 0.20
        region_y = self.diagram_top - self.height * 0.01
        region_w = self.width * 0.60
        region_h = self.height * 0.60
    region_aspect = region_w / max(1.0, region_h)
    if image_aspect >= region_aspect:
        draw_w = region_w
        draw_h = region_w / image_aspect
    else:
        draw_h = region_h
        draw_w = region_h * image_aspect
    draw_x = region_x + (region_w - draw_w) * 0.5
    draw_y = region_y + (region_h - draw_h) * 0.5

    if render_mode == "direct":
        draw_x = region_x
        draw_y = region_y
        draw_w = region_w
        draw_h = region_h
        self.raster_reveal_spec = {
            "asset": str(self.reference_image_asset),
            "x": round(draw_x, 1),
            "y": round(draw_y, 1),
            "width": round(draw_w, 1),
            "height": round(draw_h, 1),
            "renderMode": "direct",
            "fit": "cover",
            "directAppearFrame": 0,
            "strokes": [],
        }
        plan_items = self.annotation_items(4)
        fallback_labels = self.direct_callout_labels()
        while len(plan_items) < 4:
            fallback = fallback_labels[len(plan_items)] if len(plan_items) < len(fallback_labels) else f"重点{len(plan_items) + 1}"
            plan_items.append((["side_label", "short_arrow", "wavy_underline", "checkmark"][len(plan_items) % 4], fallback, self.beat_id_for(len(plan_items))))
        segment_windows: list[tuple[str | None, int, int]] = []
        if self.audio_segments:
            for segment in self.audio_segments:
                segment_windows.append((
                    str(segment.get("id") or f"beat_{len(segment_windows)}"),
                    max(0, int(segment.get("startFrame") or 0)),
                    max(1, int(segment.get("endFrame") or self.duration)),
                ))
        else:
            usable_start = max(start + 18, int(self.duration * 0.22))
            usable_end = max(usable_start + 1, self.duration - 14)
            span = max(36, (usable_end - usable_start) // 3)
            for index in range(3):
                segment_start = usable_start + index * span
                segment_windows.append((None, segment_start, min(usable_end, segment_start + span)))

        note_size = max(44, int(self.body_size * 1.44))
        note_width = self.width * 0.18
        left_note_x = max(self.width * 0.055, draw_x - note_width - self.width * 0.055)
        right_note_x = min(self.width - note_width - self.width * 0.055, draw_x + draw_w + self.width * 0.055)
        label_specs = [
            {"annotation_type": plan_items[0][0], "label": plan_items[0][1], "beat_id": plan_items[0][2], "side": "left", "text_x": left_note_x, "text_y": draw_y + draw_h * 0.17, "color": self.red if plan_items[0][0] == "risk_ray" else self.blue},
            {"annotation_type": plan_items[1][0], "label": plan_items[1][1], "beat_id": plan_items[1][2], "side": "right", "text_x": right_note_x, "text_y": draw_y + draw_h * 0.30, "color": self.red if plan_items[1][0] in {"risk_ray", "crossout"} else self.violet},
            {"annotation_type": plan_items[2][0], "label": plan_items[2][1], "beat_id": plan_items[2][2], "side": "left", "text_x": left_note_x, "text_y": draw_y + draw_h * 0.58, "color": self.green if plan_items[2][0] == "checkmark" else self.red},
            {"annotation_type": plan_items[3][0], "label": plan_items[3][1], "beat_id": plan_items[3][2], "side": "right", "text_x": right_note_x, "text_y": draw_y + draw_h * 0.70, "color": self.green if plan_items[3][0] == "checkmark" else self.blue},
        ]
        cursor = max(start + 8, int(self.duration * 0.16))
        for index, spec in enumerate(label_specs):
            beat_id, segment_start, segment_end = segment_windows[min(index, len(segment_windows) - 1)]
            beat_id = spec.get("beat_id") or beat_id
            segment_span = max(36, segment_end - segment_start)
            local_cursor = max(cursor, segment_start + min(12, max(0, segment_span // 8)))
            label_y = spec["text_y"]
            label_x = spec["text_x"]
            side = spec["side"]
            annotation_type = spec.get("annotation_type") or "side_label"
            color = self.semantic_annotation_color(annotation_type, spec["label"], spec["color"])
            connector_color = self.semantic_annotation_color(annotation_type, spec["label"], self.blue if side == "left" else self.violet)
            underline_color = self.yellow if annotation_type == "wavy_underline" else connector_color
            note_text_width = min(note_width * 0.82, _text_visual_width(spec["label"], note_size) * 0.88 + self.width * 0.018)
            link_start_x = label_x + note_text_width if side == "left" else label_x - self.width * 0.012
            edge_x = draw_x - self.width * 0.014 if side == "left" else draw_x + draw_w + self.width * 0.014
            edge_y = min(draw_y + draw_h * 0.86, max(draw_y + draw_h * 0.14, label_y + note_size * 0.58))
            note_frames = min(34, max(18, segment_span // 5))
            self.add_text(spec["label"], label_x, label_y, note_size, color, local_cursor, note_frames, note_width, emphasis=True, max_chars=9, beat_id=beat_id)
            underline_w = min(note_width * 0.86, max(self.width * 0.070, _text_visual_width(spec["label"], note_size) * 0.82))
            self.add_stroke("bold_callout_underline", _curve_points(label_x, label_y + note_size * 1.08, label_x + underline_w, label_y + note_size * 1.08, count=9, wave=self.height * 0.006), underline_color, 7, local_cursor + note_frames + 1, min(12, max(7, segment_span // 10)), beat_id=beat_id)
            self.add_stroke("callout_link", _curve_points(link_start_x, label_y + note_size * 0.56, edge_x, edge_y, count=8, wave=self.height * 0.006), connector_color, 5, local_cursor + note_frames + 6, min(16, max(8, segment_span // 8)), beat_id=beat_id)
            tick_dir = 1 if side == "left" else -1
            self.add_stroke("callout_tick", _line_points(edge_x, edge_y, edge_x + tick_dir * self.width * 0.030, edge_y, count=4), connector_color, 7, local_cursor + note_frames + min(18, max(8, segment_span // 8)), min(10, max(6, segment_span // 12)), beat_id=beat_id)
            accent_start = local_cursor + note_frames + min(26, max(12, segment_span // 7))
            accent_x = label_x - self.width * 0.018 if side == "left" else label_x + note_text_width + self.width * 0.018
            accent_y = label_y + note_size * 0.50
            if annotation_type == "risk_ray":
                self.draw_risk_rays(accent_x, accent_y, self.red, accent_start, direction=-tick_dir, beat_id=beat_id)
            elif annotation_type == "checkmark":
                self.draw_check_mark(accent_x, accent_y, self.green, accent_start, min(12, max(8, segment_span // 11)), beat_id=beat_id)
            elif annotation_type == "crossout":
                self.draw_cross_mark(accent_x, accent_y, self.red, accent_start, min(14, max(9, segment_span // 10)), beat_id=beat_id)
            elif annotation_type == "wavy_underline":
                self.draw_wavy_underline(label_x, label_y + note_size * 1.22, underline_w, self.yellow, accent_start, min(12, max(8, segment_span // 11)), beat_id=beat_id)
            elif annotation_type == "route_trace":
                self.add_arrow(_curve_points(edge_x, edge_y, edge_x + tick_dir * self.width * 0.085, edge_y + self.height * 0.045, count=12, wave=self.height * 0.018), self.green, 5, accent_start, min(16, max(9, segment_span // 10)), role="annotation_route_trace", beat_id=beat_id)
            elif annotation_type == "side_label":
                self.draw_star(accent_x, accent_y - self.height * 0.018, self.width * 0.016, self.yellow, accent_start, min(12, max(8, segment_span // 11)), beat_id=beat_id)
            else:
                self.draw_check_mark(accent_x, accent_y, self.green, accent_start, min(12, max(8, segment_span // 11)), beat_id=beat_id)
            cursor = max(local_cursor + note_frames + 32, segment_end - 4)
        return min(self.duration - 8, cursor)

    prepared: list[dict] = []
    for raw_path in self.raster_strokes:
        if not isinstance(raw_path, dict):
            continue
        raw_points = raw_path.get("points")
        if not isinstance(raw_points, list) or len(raw_points) < 2:
            continue
        points: list[dict[str, float]] = []
        for raw_point in raw_points:
            if not isinstance(raw_point, dict):
                continue
            px = raw_point.get("x")
            py = raw_point.get("y")
            if not isinstance(px, (int, float)) or not isinstance(py, (int, float)):
                continue
            points.append(_point(draw_x + max(0.0, min(1.0, float(px))) * draw_w, draw_y + max(0.0, min(1.0, float(py))) * draw_h))
        if len(points) < 2:
            continue
        normalized_width = raw_path.get("revealWidth") or raw_path.get("reveal_width") or 0.018
        reveal_width = max(36.0, min(128.0, float(normalized_width) * max(draw_w, draw_h)))
        prepared.append({"points": points, "revealWidth": round(reveal_width, 1), "dashLength": round(_polyline_length(points), 1), "weight": math.sqrt(max(1.0, _polyline_length(points)))})

    if not prepared:
        return self.build_process_flow(start)

    window_start = min(max(0, start), max(0, self.duration - 32))
    window_end = max(window_start + 12.0, self.duration - 24.0)
    total_weight = sum(item["weight"] for item in prepared) or float(len(prepared))
    cursor_float = float(window_start)
    raster_paths: list[dict] = []
    for index, item in enumerate(prepared):
        op_id = f"s{self.scene_index}_raster_{index}"
        span = max(0.45, (window_end - window_start) * item["weight"] / total_weight)
        end_float = window_end if index == len(prepared) - 1 else min(window_end, cursor_float + span)
        self.draw_ops.append({"id": op_id, "kind": "path", "startFrame": round(cursor_float, 2), "endFrame": round(max(cursor_float + 0.35, end_float), 2), "points": item["points"]})
        raster_paths.append({"opId": op_id, "d": _path_from_points(item["points"]), "revealWidth": item["revealWidth"], "dashLength": item["dashLength"]})
        cursor_float = end_float

    self.raster_reveal_spec = {
        "asset": str(self.reference_image_asset),
        "x": round(draw_x, 1),
        "y": round(draw_y, 1),
        "width": round(draw_w, 1),
        "height": round(draw_h, 1),
        "strokes": raster_paths,
    }
    return min(self.duration - 8, int(math.ceil(window_end + 6)))


FallbackSceneBuilder.build_raster_reveal = build_raster_reveal
