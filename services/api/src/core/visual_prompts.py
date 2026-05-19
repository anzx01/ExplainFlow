"""Shared visual prompt presets for storyboard planning and image generation."""

BOLD_EDITORIAL_HANDDRAWN_STYLE_NAME = "bold_editorial_handdrawn"

BOLD_EDITORIAL_IMAGE_STYLE = (
    "bold editorial hand-drawn explainer illustration inspired by modern marker and wax-crayon storyboard slides, "
    "warm off-white whiteboard or paper surface with subtle grain, "
    "thick imperfect black marker/crayon outlines, loose sketch texture, expressive but simple people, objects, food, tools, or icons, "
    "large friendly visual anchors rather than tiny symbols, "
    "hot pink accent arrows, underlines, check marks, starbursts, rays, hearts, mail icons, gears, or small doodles when useful, "
    "sunny yellow paint-blob or halo highlight shapes behind the main subject, never as a full-page background, "
    "limited lively palette: black ink, warm yellow, coral pink, small grey fills, plus subject-specific semantic colors, "
    "composition has one big subject or at most three big step groups connected by broad pink arrows, "
    "leave generous blank margins for renderer-added handwriting and later animated callouts, "
    "text-free artwork: do not draw titles, paragraphs, captions, labels, UI buttons, logos, watermarks, or random letters; "
    "the video renderer will add all readable text separately in a handwritten style"
)

BOLD_EDITORIAL_IMAGE_DESCRIPTION_HINT = (
    "Style preset: bold editorial hand-drawn explainer illustration, thick imperfect black crayon/marker outlines, "
    "warm off-white surface, hot pink accent arrows/underlines/checks/starbursts, sunny yellow highlight blobs, "
    "one large friendly subject or at most three large step groups, generous blank space, text-free artwork for later handwritten overlays."
)

BOLD_EDITORIAL_IMAGE_NEGATIVE = (
    "photorealistic, glossy 3d, stock vector template, corporate flat vector, thin technical line art only, "
    "monochrome-only diagram, dense infographic, crowded flowchart, tiny icons, tiny labels, long paragraph, "
    "AI-generated gibberish text, title text, captions, UI button, logo, watermark, full yellow background, "
    "card grid, slide deck frame, legend box, decorative border"
)

BOLD_EDITORIAL_BOARD_RULES = [
    "采用粗黑蜡笔/马克笔手绘质感：主体线条要厚、有轻微抖动，不能像细线技术图或单调简笔画。",
    "画面以一个大主体为核心，或最多三个大步骤；不要排很多小框、小图标、小锅、小字流程。",
    "使用参考图式配色：黑色主体线，珊瑚粉箭头/勾选/爆炸星/下划线，暖黄色大色块或光晕作强调，另按题材加入必要真实颜色。",
    "图像模型负责生成大手绘图形、人物、物体、食物、色块和箭头；可读文字、标题、中文标签和动态标注由渲染端手写叠加。",
    "image_description 要明确要求 text-free artwork，并预留空白给后续手写标题、callout、勾选、下划线和短箭头。",
]

BOLD_EDITORIAL_LAYOUT_RULES = [
    "一屏一个核心画面：大人物/大物体/大食物/大工具占主要视觉面积，旁边只留少量短标注。",
    "可使用暖黄色 blob/halo 放在主体背后，粉色宽箭头串起步骤，但不要做整页彩色背景或密集海报。",
    "如果有步骤流程，最多三个大节点；超过三个步骤要拆分到多个场景，用旁白承接细节。",
]
