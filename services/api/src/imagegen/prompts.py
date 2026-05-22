from src.core.golpo_styles import golpo_video_style_aliases, golpo_video_style_presets
from src.core.visual_prompts import (
    BOLD_EDITORIAL_IMAGE_NEGATIVE,
    BOLD_EDITORIAL_IMAGE_STYLE,
    visual_teaching_rules,
)

_TEACHING_RULES = visual_teaching_rules()
ACTIVE_VIDEO_STYLE = str(_TEACHING_RULES.get("active_style") or "whiteboard")
VIDEO_STYLE_ALIASES = golpo_video_style_aliases()
VIDEO_STYLE_PRESETS = golpo_video_style_presets(include_aliases=False)

STYLE_SUFFIX = (
    f"{BOLD_EDITORIAL_IMAGE_STYLE}, "
    "rich colorful educational explainer illustration, matching an engaging real teacher marker-board lecture video, "
    "one vivid central visual metaphor, object, comparison, process, or mechanism per image; never a dense infographic, "
    "place the main illustration in the middle or slightly right of center, using about 55-75 percent of the frame width, "
    "leave broad clean margins around the drawing for a hand to write callouts later, "
    "hand-drawn marker and crayon doodle style with solid readable strokes, not just thin black line art, "
    "include 3-6 meaningful illustrated subject parts such as people, signs, clocks, routes, scales, gears, cards, process paths, badges, containers, food, cookware, or maps when they clarify the concept, "
    "do not add a title, topic heading, scene name, readable labels, logo, watermark, paragraph text, legend box, slide frame, or poster layout inside the image, "
    "the scene title and topic are only context for the artist; never render them as words inside the image, "
    "draw the specific mechanism described with integral process paths, state comparison groups, and concrete metaphor objects when requested; do not add annotation overlays inside the generated image, "
    "never bake teacher annotation marks into the image: no titles, callout arrows, pointing arrows, warning marks, starbursts, underlines, circles, boxes, brackets, edge ticks, or later-addition marks unless they are real physical parts of the subject, "
    "for very complex objects, show the finished colorful doodle/reference illustration cleanly and leave room around it for hand-drawn callouts added later, "
    "even when the subject is a direct complex reference image, keep it in the same hand-drawn marker/crayon whiteboard style as simple traced diagrams, never as a photo, screenshot, glossy render, or stock vector, "
    "reserve clean margins for varied renderer-added annotations such as arrows, wavy underlines, brackets, edge ticks, starbursts, circles, and local zoom callouts, "
    "do not draw empty callout boxes, empty circles, speech bubbles, label plaques, blank legend boxes, placeholder containers, or standalone annotation marks; leave open whitespace instead, "
    "every visible box, circle, bracket, arrow, or badge in the generated image must be an actual subject component with obvious purpose, not a later-label placeholder, "
    "show the final board drawing as if it has just been sketched by a skilled visual teacher: slightly irregular marker lines, simple expressive objects, lively but readable composition, "
    "avoid generic placeholder shapes, decorative templates, glossy 3D, photorealism, monochrome-only diagrams, and dense infographic layouts"
)

NEGATIVE = (
    "photo, realistic, poster, 3d render, painting, complex background, decorative template, "
    f"{BOLD_EDITORIAL_IMAGE_NEGATIVE}, "
    "topic heading, dense infographic, long paragraph, slide frame, card layout, legend box, empty label boxes, empty circles, placeholder callouts, baked callout arrows, pointing arrows, standalone warning marks"
)

COOKING_TERMS = (
    "cook", "cooking", "recipe", "food", "dish", "wok", "skillet", "stir-fry", "simmer",
    "sauce", "tofu", "mapo", "麻婆", "豆腐", "烹饪", "做法", "食材", "炒", "煸", "爆香",
    "锅", "菜", "勾芡", "出锅", "装盘",
)

BLANCHING_TERMS = ("blanch", "boiling water", "boil water", "parboil", "焯水", "汆", "煮水", "开水")

STIR_FRY_TERMS = (
    "wok", "skillet", "stir-fry", "stir fry", "simmer", "thicken", "sauce",
    "炒", "煸", "爆香", "烧", "勾芡", "收汁", "底料",
)

PREP_TERMS = ("prep", "prepare", "ingredient", "mise en place", "食材", "准备", "切", "备料")
FINAL_TERMS = ("finish", "serve", "plate", "plating", "finished", "出锅", "装盘", "成品")
OVERVIEW_TERMS = ("overview", "map", "流程图", "步骤流程", "风味地图", "概览", "总览")
