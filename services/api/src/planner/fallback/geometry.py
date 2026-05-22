import math
import re

def _short_text(value: str | None, max_chars: int = 30) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _text_visual_width(value: str, font_size: float) -> float:
    width = 0.0
    for char in value:
        width += font_size * (1.0 if re.match(r"[\u3400-\u9fff]", char) else 0.55)
    return width


def _point(x: float, y: float) -> dict[str, float]:
    return {"x": round(float(x), 1), "y": round(float(y), 1)}


def _text_stroke_points(
    text: str,
    x: float,
    y: float,
    font_size: float,
    max_width: float,
) -> list[dict[str, float]]:
    char_count = max(1, min(len(text), 20))
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", text))
    char_w = font_size * (0.92 if cjk_count >= max(1, char_count // 2) else 0.58)
    char_w = max(12.0, min(char_w, max_width / max(char_count, 1)))
    baseline = y + font_size * 0.82
    high = y + font_size * 0.18
    mid = y + font_size * 0.52
    low = y + font_size * 0.92
    points: list[dict[str, float]] = []
    for i in range(char_count):
        left = x + i * char_w
        wobble = (i % 3) * font_size * 0.04
        points.extend(
            [
                _point(left, baseline),
                _point(left + char_w * 0.18, high + wobble),
                _point(left + char_w * 0.42, low - wobble),
                _point(left + char_w * 0.66, mid + wobble),
                _point(left + char_w * 0.96, baseline - wobble),
            ]
        )
    return points


def _curve_points(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    count: int = 20,
    wave: float = 34.0,
) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for i in range(count):
        t = i / max(count - 1, 1)
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t - math.sin(math.pi * t) * wave + math.sin(math.pi * 3 * t) * wave * 0.18
        points.append(_point(x, y))
    return points


def _rect_points(x: float, y: float, width: float, height: float) -> list[dict[str, float]]:
    return [
        _point(x, y),
        _point(x + width * 0.34, y - 4),
        _point(x + width, y),
        _point(x + width + 5, y + height * 0.46),
        _point(x + width, y + height),
        _point(x + width * 0.42, y + height + 4),
        _point(x, y + height),
        _point(x - 4, y + height * 0.42),
        _point(x, y),
    ]


def _circle_points(cx: float, cy: float, rx: float, ry: float, count: int = 24) -> list[dict[str, float]]:
    return [
        _point(cx + math.cos((math.pi * 2 * i) / count) * rx, cy + math.sin((math.pi * 2 * i) / count) * ry)
        for i in range(count + 1)
    ]


def _line_points(x0: float, y0: float, x1: float, y1: float, count: int = 5) -> list[dict[str, float]]:
    return [_point(x0 + (x1 - x0) * i / max(count - 1, 1), y0 + (y1 - y0) * i / max(count - 1, 1)) for i in range(count)]


def _smile_points(cx: float, cy: float, width: float, height: float, count: int = 10) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for i in range(count):
        t = i / max(count - 1, 1)
        x = cx - width / 2 + width * t
        y = cy + math.sin(math.pi * t) * height
        points.append(_point(x, y))
    return points


def _polyline_length(points: list[dict[str, float]], close: bool = False) -> float:
    if len(points) < 2:
        return 1.0
    total = 0.0
    pairs = zip(points, points[1:])
    for start, end in pairs:
        total += math.hypot(end["x"] - start["x"], end["y"] - start["y"])
    if close and points[0] != points[-1]:
        total += math.hypot(points[-1]["x"] - points[0]["x"], points[-1]["y"] - points[0]["y"])
    return max(1.0, total + 12.0)


def _path_from_points(points: list[dict[str, float]], close: bool = False) -> str:
    if not points:
        return ""
    commands = [f"M {points[0]['x']} {points[0]['y']}"]
    commands.extend(f"L {p['x']} {p['y']}" for p in points[1:])
    if close:
        commands.append("Z")
    return " ".join(commands)



def _arc_points(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    start_angle: float,
    end_angle: float,
    count: int = 18,
) -> list[dict[str, float]]:
    return [
        _point(
            cx + math.cos(start_angle + (end_angle - start_angle) * i / max(count - 1, 1)) * rx,
            cy + math.sin(start_angle + (end_angle - start_angle) * i / max(count - 1, 1)) * ry,
        )
        for i in range(count)
    ]


def _diamond_points(cx: float, cy: float, width: float, height: float) -> list[dict[str, float]]:
    return [
        _point(cx, cy - height / 2),
        _point(cx + width / 2 + 4, cy),
        _point(cx, cy + height / 2 + 3),
        _point(cx - width / 2 - 3, cy),
        _point(cx, cy - height / 2),
    ]


