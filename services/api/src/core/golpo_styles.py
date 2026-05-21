import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(__file__).with_name("golpo_styles.json")


@lru_cache(maxsize=1)
def load_golpo_style_config() -> dict[str, Any]:
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))


def golpo_video_styles(include_auto: bool = False) -> set[str]:
    config = load_golpo_style_config()
    styles = set(config.get("video_style_order", []))
    if include_auto:
        styles.add("auto")
    return styles


def golpo_video_style_aliases() -> dict[str, str]:
    return dict(load_golpo_style_config().get("aliases", {}))


def golpo_video_style_presets(include_aliases: bool = True) -> dict[str, dict[str, str]]:
    config = load_golpo_style_config()
    presets = {
        style_id: dict(value)
        for style_id, value in config.get("video_styles", {}).items()
    }
    if include_aliases:
        for alias, target in golpo_video_style_aliases().items():
            if target not in presets:
                continue
            presets[alias] = {
                **presets[target],
                "alias_for": target,
                "name": presets[target].get("name", target),
                "planning_rule": f"Alias for {presets[target].get('name', target)}.",
                "image_rule": f"Alias for {presets[target].get('name', target)}.",
            }
    return presets


def golpo_pen_style_presets() -> dict[str, dict[str, str]]:
    return {
        style_id: dict(value)
        for style_id, value in load_golpo_style_config().get("pen_styles", {}).items()
    }
