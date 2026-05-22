import json
import logging

from src.core.llm import chat_json, check_llm_connection
from src.core.visual_prompts import visual_teaching_rules_prompt
from src.explain.models import ExplainGraph
from ..models import (
    AnimationInstruction,
    AnimationType,
    GenerateStoryboardRequest,
    Scene,
    Storyboard,
)
from .normalizer import (
    _clean_text,
    _normalize_image_description_text,
    _parse_visual_beats,
    _parse_diagram_plan,
    _parse_annotation_plan,
    _normalize_video_style,
    _video_style_preset,
    _canonical_video_style,
    _normalize_pen_style,
    _pen_style_preset,
)
from .timing import (
    _estimate_scene_duration,
    _narration_from_beats,
    _compress_storyboard_narration_to_target,
    _fit_storyboard_to_target,
)
from .scene_mgmt import (
    _trim_storyboard_scene_count,
    _ensure_opening_scene_first,
    _graph_enhanced_brief,
    _desired_scene_count,
)
from .quality_ensure import _ensure_storyboard_quality
from ..coverage.appender import _sanitize_storyboard_narration
from ..prompts.storyboard import STORYBOARD_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

async def generate_storyboard(req: GenerateStoryboardRequest) -> Storyboard:
    await check_llm_connection()

    graph = req.graph
    brief_data = _graph_enhanced_brief(graph)
    video_style = _canonical_video_style(req.video_style)
    video_style_preset = _video_style_preset(video_style)
    pen_style = _normalize_pen_style(req.pen_style)
    pen_style_preset = _pen_style_preset(pen_style)
    desired_scene_count = _desired_scene_count(graph, req.target_duration)
    nodes_desc = "\n".join(
        f"- [{n.node_type.value}] {n.label}（teach_order={n.teach_order}）: {n.description}"
        + (f" LaTeX: {n.latex}" if n.latex else "")
        for n in sorted(graph.nodes, key=lambda x: x.teach_order)
    )
    edges_desc = "\n".join(
        f"- {e.source} → {e.target}（{e.relation}）" for e in graph.edges
    )

    user_content = f"""主题：{graph.topic}
总结：{graph.summary}
目标时长：{req.target_duration}秒

概念节点（按教学顺序）：
{nodes_desc}

概念关系：
{edges_desc}

核心洞察：
{chr(10).join(f"- {i}" for i in graph.key_insights)}

要求：
- 生成 {max(3, min(6, len(graph.nodes)))} 个场景
- 每个场景必须有 2-4 个 animations
- 优先使用 write_text + bullet_list/step_reveal 组合
- 公式场景必须用 write_formula（不要用 write_text 写公式）"""

    user_content = json.dumps(
        {
            "topic": graph.topic,
            "summary": graph.summary,
            "target_duration_seconds": req.target_duration,
            "desired_scene_count": desired_scene_count,
            "selected_video_style": {
                "id": video_style,
                "name": video_style_preset["name"],
                "default_board_mode": video_style_preset["board_mode"] or None,
                "default_hand_usage": video_style_preset["hand_usage"] or None,
                "default_visual_style": video_style_preset["visual_style"] or None,
                "default_render_strategy": video_style_preset["render_strategy"] or None,
                "planning_rule": video_style_preset["planning_rule"],
                "image_rule": video_style_preset["image_rule"],
            },
            "selected_pen_style": {
                "id": pen_style,
                "name": pen_style_preset["name"],
                "animation_rule": pen_style_preset["rule"],
            },
            "enhanced_teaching_brief": brief_data,
            "concept_nodes": [
                {
                    "id": node.id,
                    "label": node.label,
                    "node_type": node.node_type.value,
                    "description": node.description,
                    "latex": node.latex,
                    "teach_order": node.teach_order,
                }
                for node in sorted(graph.nodes, key=lambda item: item.teach_order)
            ],
            "edges": [edge.model_dump(mode="json") for edge in graph.edges],
            "key_insights": graph.key_insights,
            "requirements": [
                "Generate concrete scenes, not generic slide bullets.",
                "Use natural Chinese for all scene titles, narration, diagram labels, and visual beats. When source concepts are English, transcreate them into Chinese expressions a real teacher would say; keep English only for fixed technical terms, acronyms, formulas, or search names, optionally in parentheses.",
                "Avoid dictionary-like hard translations and awkward coined shorthand. Prefer clear Chinese phrases over literal word-by-word translations; e.g. dependence/independence/interdependence can become '依赖 → 独立 → 互相依赖/成熟协作/协作共赢' depending on context, rather than a stiff literal label.",
                "Use the reference-whiteboard grammar: each scene needs one primary visual anchor, such as an object, metaphor, diagram, route, scale, funnel, matrix, clock, warning sign, tool, person/group, chart, or system stack.",
                "Every scene must specify diagram_plan.layout as a staged board composition: title/anchor first, main object or diagram second, arrows/callouts third, and one short takeaway last.",
                "Use the default visual preset for image_description: bold editorial hand-drawn explainer illustration with thick imperfect black crayon/marker outlines, warm off-white surface, subject-integral color accents only, sunny yellow highlight blobs behind the main subject, one large visual anchor or at most three large step groups, generous blank space, and text-free artwork because readable text and teacher annotations will be added by the renderer.",
                "For any direct/reference image_description, describe only the clean subject artwork. Do not request baked titles, labels, callout arrows, pointing arrows, warning marks, starbursts, underlines, circles, boxes, brackets, or 'later additions' inside the generated image; the renderer will add those annotations as semantic drawOps.",
                "Do not create any scene that is only a title plus bullet list, checklist, checkmarks, or text boxes. A checklist may appear only as a tiny supporting note beside a larger visual object.",
                "For abstract topics, translate the idea into a concrete visual metaphor before choosing labels: balance scale for tradeoffs, route map for goals, funnel for filtering, loop for feedback, gear/tool for mechanism, clock for timing, warning triangle for risk, clipboard for procedure, people for responsibility, chart for evidence.",
                "Each diagram_plan.required_labels list should name the short labels attached near the visual anchor, not paragraph fragments. Prefer 3-5 labels that map to visible parts of the drawing.",
                "Each scene must include learning_goal, diagram_plan, visual_beats, narration, image_description and animations.",
                "Each scene must also include visual_mode (trace|direct_reference|hybrid), teaching_density=rich, visual_anchor, and annotation_plan. annotation_plan must contain at least 3 renderer annotations with different type values; every item needs type, label, target, beat_id, and layer='renderer'.",
                "Use only the active product style for now: video_style must be whiteboard and pen_style must be marker. Other Golpo styles are visible in the UI but currently unavailable.",
                "Every visual_beat must pair draw_intent with narration so voiceover follows drawing.",
                "Cover every high-priority teaching_coverage_units item from enhanced_teaching_brief in the actual scene text, labels, beats or narration. Do not merely leave it in the brief.",
                "Respect desired_scene_count. If coverage units are more numerous than scenes, group related units into one scene with multiple visual_beats instead of adding duplicate scenes.",
                "For multi-part topics, include an overview map, grouped explanation scenes, then a final visual synthesis such as a loop, roadmap, hub-and-spoke map, or evidence chart. Avoid final checklist-only scenes.",
                "Use comparison/process/structure/cross-section diagrams and arrows whenever possible.",
                "Borrow strong science-video teaching techniques: start with a hook or historical/context clue when useful, expand acronyms visually, use picture-in-picture reference diagrams, and introduce one concrete real-world analogy that maps to the mechanism.",
                "For abstract mechanisms, show the analogy and the technical diagram side by side, then transfer arrows/labels from the analogy to the device/process.",
                "Make narration lively and a little witty: every scene needs one concrete everyday metaphor, tiny reversal, or teacher-like aside that clarifies the idea. Avoid dry textbook wording and avoid internet memes.",
                "Make visuals feel active: prefer route maps, seesaws, sorting counters, warning marks, loop arrows, sticky-note-sized callouts and small teacher doodles over plain boxes and long labels.",
                "Use progressive focus: first show the whole object, then zoom/call out one region, then add colored arrows and labels only when the narration reaches them.",
                "Generalize the complex/simple visual split across every future topic: simple diagrams should be hand-drawn stroke by stroke; especially complex, dense, realistic, multi-layer, or reference-like graphics should be shown directly as a finished hand-drawn reference image and then annotated by the hand.",
                "Unless the topic is pure chalkboard math or has only one scene, plan a mix of both visual modes in the same video: at least one simple trace scene and at least one direct/hybrid reference scene. The two modes must share the same hand-drawn marker/crayon style, canvas color, and teaching palette.",
                "Do not let direct images look like photos, screenshots, stock vectors, or a different art style. Direct complex graphics must still be text-free hand-drawn explainer art, with the renderer adding all readable Chinese labels and callouts.",
                "Use varied annotations in every scene, not only plain labels and straight arrows: combine short handwritten labels, wavy underlines, circles, brackets, edge ticks, warning/starburst marks, local zoom boxes, and connector arrows according to what the teaching point needs.",
                "Treat target_duration_seconds as a pacing hint, not a hard cap. Never drop required concepts or compress narration so much that drawing and voiceover become incomplete.",
                "Use red for current, blue for voltage/control signals, green for conductive channels, purple for gates/attention, and yellow underlines/callouts for key terms.",
                "Underline, circle, or box important concepts like V_G > V_th, electron channel, short-channel effect, FinFET, W_eff, learning rate, and gradient.",
                "For each scene choose board_mode, hand_usage, video_style and visual_style from the brief strategy. Use chalkboard/no hand for chalkboard styles, clean_canvas/annotate for editorial/whiteboard/playful styles, reference/annotate for technical blueprint or complex finished diagrams, and trace only when the drawing is simple enough to follow by hand.",
                "Honor selected_video_style unless it would make the explanation unclear or factually wrong. If selected_video_style.id is not auto, use its default board_mode, hand_usage, visual_style and render_strategy as the baseline for most scenes; only override individual math derivation or complex reference scenes when that clearly improves understanding.",
                "Put selected_video_style.id on each scene as video_style, unless selected_video_style.id is auto. Keep video_style as one of the eight Golpo canvas styles, not the old internal visual_style names.",
                "Reflect selected_video_style.image_rule inside each image_description. The image_description must be specific enough for an image generation model, including style, objects, colors, composition, blank margins, and text-free artwork.",
                "Honor selected_pen_style as a separate animation layer. It can combine with any visual style: pen=fine precise hand, fountain_pen=stylus/tablet feeling, marker=bold marker hand, no_hand=hide hand and use staged reveal. Put the chosen pen_style on each scene unless the scene must hide the hand.",
                "For cooking or food how-to topics, make image_description concrete and appetizing: name the cookware, ingredients, sauce color, steam, garnish, and finished state. For Chinese stir-fry/simmer steps prefer a wide black wok or skillet; use a blue soup pot only for explicit blanching or boiling-water scenes. Map colors to real food, e.g. red chili oil/sauce, white tofu cubes, brown minced meat, green garlic sprouts or scallions.",
                "For cooking or food how-to scenes, use one large food/cookware state per scene. Avoid dense step-flow diagrams with many tiny pots, boxes, or captions. If an overview is needed, use at most three large illustrated nodes; leave recipe details to narration and later scenes.",
            ],
        },
        ensure_ascii=False,
    )

    logger.info("Generating storyboard for: %s, target=%ds", graph.topic, req.target_duration)

    raw = await chat_json(
        messages=[
            {"role": "system", "content": f"{STORYBOARD_SYSTEM_PROMPT}\n\n{visual_teaching_rules_prompt('planner')}"},
            {"role": "user", "content": user_content},
        ]
    )

    scenes: list[Scene] = []
    total_duration = 0.0

    for s in raw.get("scenes", []):
        animations: list[AnimationInstruction] = []
        for a in s.get("animations", []):
            raw_type = a.get("type", "write_text")
            try:
                anim_type = AnimationType(raw_type)
            except ValueError:
                anim_type = AnimationType.WRITE_TEXT
            animations.append(
                AnimationInstruction(
                    type=anim_type,
                    duration=min(15.0, max(0.5, float(a.get("duration", 2.0)))),
                    content=a.get("content") or "",
                    latex=a.get("latex"),
                    from_node=a.get("from_node"),
                    to_node=a.get("to_node"),
                    x=a.get("x"),
                    y=a.get("y"),
                    items=a.get("items"),
                )
            )
        visual_beats = _parse_visual_beats(s.get("visual_beats"))
        diagram_plan = _parse_diagram_plan(s.get("diagram_plan"))
        narration = _narration_from_beats(s.get("narration") or "", visual_beats)
        dur = _estimate_scene_duration(float(s.get("duration_estimate", 20)), narration, visual_beats, animations)
        total_duration += dur
        scenes.append(
            Scene(
                id=s.get("id") or f"scene_{len(scenes)}",
                order=s.get("order", len(scenes)),
                title=s.get("title") or f"场景 {len(scenes) + 1}",
                narration=narration,
                duration_estimate=dur,
                animations=animations,
                node_ids=s.get("node_ids") or [],
                image_description=_normalize_image_description_text(s.get("image_description")) or None,
                learning_goal=s.get("learning_goal") or None,
                visual_beats=visual_beats,
                diagram_plan=diagram_plan,
                visual_mode=_clean_text(s.get("visual_mode") or s.get("visualMode") or ""),
                teaching_density=_clean_text(s.get("teaching_density") or s.get("teachingDensity") or ""),
                visual_anchor=_clean_text(s.get("visual_anchor") or s.get("visualAnchor") or ""),
                annotation_plan=_parse_annotation_plan(s.get("annotation_plan") or s.get("annotationPlan")),
                render_strategy=_clean_text(s.get("render_strategy") or s.get("raster_strategy") or ""),
                visual_complexity=_clean_text(s.get("visual_complexity") or ""),
                board_mode=_clean_text(s.get("board_mode") or ""),
                hand_usage=_clean_text(s.get("hand_usage") or ""),
                video_style=_clean_text(s.get("video_style") or s.get("videoStyle") or ""),
                visual_style=_clean_text(s.get("visual_style") or ""),
                pen_style=_clean_text(s.get("pen_style") or s.get("penStyle") or ""),
            )
        )

    storyboard = Storyboard(
        topic=graph.topic,
        total_duration_estimate=total_duration,
        scenes=scenes,
        video_style=video_style,
        pen_style=pen_style,
    )
    storyboard = _trim_storyboard_scene_count(storyboard, req.target_duration, graph)
    storyboard = _ensure_storyboard_quality(storyboard, graph, req.target_duration)
    storyboard = _trim_storyboard_scene_count(storyboard, req.target_duration, graph)
    storyboard = _ensure_opening_scene_first(storyboard)
    storyboard = _compress_storyboard_narration_to_target(storyboard, req.target_duration)
    storyboard = _fit_storyboard_to_target(storyboard, req.target_duration)
    storyboard = _sanitize_storyboard_narration(storyboard)

    logger.info("Storyboard generated: %d scenes, %.1fs total", len(storyboard.scenes), storyboard.total_duration_estimate)
    return storyboard


