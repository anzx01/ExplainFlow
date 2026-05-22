import json
import logging
from copy import deepcopy

from src.core.llm import chat_json, check_llm_connection
from src.core.config import settings
from src.core.visual_prompts import visual_teaching_rules_prompt

from ..models import (
    GenerateRemotionCodeRequest,
    GenerateRemotionCodeResponse,
)
from .tsx_validator import _validate_generated_tsx, _validate_generated_tsx_for_request, _storyboard_has_audio_segments
from ..fallback.tsx_template import _build_fallback_remotion_tsx
from ..prompts.remotion_codegen import REMOTION_CODE_SYSTEM_PROMPT
from .validator import HAND_ASSET

logger = logging.getLogger(__name__)

REMOTION_CODE_CACHE: dict[str, GenerateRemotionCodeResponse] = {}
REMOTION_CODE_CACHE_MAX_ITEMS = 16

def _remotion_codegen_cache_key(req: GenerateRemotionCodeRequest, mode: str) -> str:
    return json.dumps(
        {
            "mode": mode,
            "fps": req.fps,
            "width": req.width,
            "height": req.height,
            "subtitles_enabled": req.subtitles_enabled,
            "background_music_url": req.background_music_url,
            "background_music_volume": round(req.background_music_volume, 3),
            "style_prompt": req.style_prompt,
            "storyboard": req.storyboard.model_dump(mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _cache_remotion_response(key: str, response: GenerateRemotionCodeResponse) -> GenerateRemotionCodeResponse:
    if len(REMOTION_CODE_CACHE) >= REMOTION_CODE_CACHE_MAX_ITEMS:
        REMOTION_CODE_CACHE.pop(next(iter(REMOTION_CODE_CACHE)))
    REMOTION_CODE_CACHE[key] = deepcopy(response)
    return response


def _cached_remotion_response(key: str) -> GenerateRemotionCodeResponse | None:
    cached = REMOTION_CODE_CACHE.get(key)
    return deepcopy(cached) if cached else None




def _compile_fast_remotion_response(
    req: GenerateRemotionCodeRequest,
    note: str,
) -> GenerateRemotionCodeResponse:
    fallback_tsx, fallback_duration = _build_fallback_remotion_tsx(
        req.storyboard,
        req.fps,
        req.width,
        req.height,
        req.subtitles_enabled,
        req.background_music_url,
        req.background_music_volume,
    )
    return GenerateRemotionCodeResponse(
        tsx=_validate_generated_tsx(fallback_tsx),
        duration_in_frames=fallback_duration,
        fps=req.fps,
        width=req.width,
        height=req.height,
        notes=note,
    )



async def generate_remotion_code(
    req: GenerateRemotionCodeRequest,
) -> GenerateRemotionCodeResponse:
    await check_llm_connection()

    storyboard_data = req.storyboard.model_dump(mode="json")
    target_frames = max(
        req.fps * 10,
        round(req.storyboard.total_duration_estimate * req.fps),
    )
    style_prompt = req.style_prompt or (
        "Chinese educational whiteboard animation with a real visible hand holding a marker. "
        f"{visual_teaching_rules_prompt('render')} "
        "The hand must write every text label and draw every SVG line by following drawOps stroke points, "
        "moving up/down/left/right inside glyphs like real handwriting, "
        "using glyphPaths/GlyphText/DrawGlyphPath so the renderer can replace Chinese text with opentype.js font outlines, "
        "using rasterReveal/referenceImageAsset masks when the storyboard provides an original reference image to reveal, "
        "never creating inner paper/card/panel/sheet surfaces, shadows, washes, gradients, or backings behind drawings, "
        "making generic-topic visuals lively with small humorous teacher-board metaphors, "
        "using staticFile('hand-real-pen.png'), <Img>, and getPenPosition(frame) coordinates. "
        "When scene.audioSegments exist, synchronize Audio, subtitles, and drawOps to those beat windows. "
        "If subtitles_enabled is true, show scene.narration as bottom subtitles; if false, do not show captions. "
        "If background_music_url is provided, add it as one low-volume looping background Audio track behind narration. "
        "Respect scene board_mode/hand_usage/visual_style: hide the hand for chalkboard or hand_usage=none scenes, use direct/hybrid presentation for reference or annotate scenes, and use colorful finished doodles plus hand annotations for marketing_doodle scenes. "
        "Generalize the mixed visual policy: simple graphics are handwritten stroke by stroke, especially complex graphics are shown directly as finished hand-drawn reference art, and both remain visually unified with varied teacher annotations. "
        "Every non-reference shape must be hand-drawn by drawOps and semantically tied to a label or beat; never add unlabeled boxes, circles, brackets, or arrows. "
        "Respect scene.video_style as the Golpo Canvas layer: black/white chalkboard stays white-only, color chalkboard uses limited cyan/yellow accents, modern_minimal stays sparse, technical_blueprint stays navy/pale-blue, editorial stays bold off-white/red-orange, whiteboard stays marker-board, playful stays crayon-pastel, and sharpie stays thick black marker. "
        "Use Chinese handwritten fonts and teacher-style whiteboard callouts. "
        "No stock images, no templates, no decorative component frames."
    )
    codegen_mode = settings.remotion_codegen_mode.strip().lower()
    cache_key = _remotion_codegen_cache_key(req, codegen_mode)
    cached = _cached_remotion_response(cache_key)
    if cached:
        cached.notes = f"{cached.notes or 'Generated Remotion TSX'} (cache hit)"
        return cached

    if codegen_mode not in {"llm", "llm-first", "llm_repair"}:
        logger.info("Compiling Remotion TSX with fast local compiler for: %s", req.storyboard.topic)
        return _cache_remotion_response(
            cache_key,
            _compile_fast_remotion_response(
                req,
                (
                    "Fast Remotion compiler path: ExplainFlow used the storyboard produced by the LLM "
                    "and generated validated glyph-outline Remotion TSX locally."
                ),
            ),
        )

    user_content = json.dumps(
        {
            "fps": req.fps,
            "width": req.width,
            "height": req.height,
            "target_duration_in_frames": target_frames,
            "subtitles_enabled": req.subtitles_enabled,
            "background_music_url": req.background_music_url,
            "background_music_volume": req.background_music_volume,
            "style_prompt": style_prompt,
            "storyboard": storyboard_data,
        },
        ensure_ascii=False,
    )

    logger.info("Generating Remotion TSX for: %s", req.storyboard.topic)

    messages = [
        {"role": "system", "content": REMOTION_CODE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        raw = await chat_json(messages=messages, model=settings.coder_model)
    except Exception as llm_error:
        logger.warning("Remotion TSX LLM call failed before validation: %s", llm_error)
        return _cache_remotion_response(
            cache_key,
            _compile_fast_remotion_response(
                req,
                (
                    "LLM TSX generation failed before validation, so ExplainFlow "
                    "compiled a self-contained Remotion whiteboard module from the storyboard."
                ),
            ),
        )

    try:
        tsx = _validate_generated_tsx_for_request(raw.get("tsx") or raw.get("code") or "", req)
    except ValueError as first_error:
        logger.warning("Generated Remotion TSX failed validation: %s", first_error)
        if not settings.remotion_llm_repair and codegen_mode != "llm_repair":
            return _cache_remotion_response(
                cache_key,
                _compile_fast_remotion_response(
                    req,
                    (
                        "LLM TSX failed validation, so ExplainFlow skipped the repair round "
                        "and compiled a validated Remotion whiteboard module locally."
                    ),
                ),
            )
        repair_messages = [
            *messages,
            {
                "role": "assistant",
                "content": json.dumps(raw, ensure_ascii=False),
            },
            {
                "role": "user",
                "content": (
                    "The TSX failed validation with this error: "
                    f"{first_error}. Return corrected JSON only. Keep it self-contained, "
                    "use only react/remotion imports, export named GeneratedVideo, "
                    "use useCurrentFrame(), Sequence, and interpolate() or spring(), "
                    "draw SVG lines with strokeDasharray/strokeDashoffset, reveal text progressively, "
                    "render Chinese text through glyphPaths with GlyphText/DrawGlyphPath so the renderer can "
                    "preprocess font outline paths using opentype.js, "
                    "render scene.narration as bottom HTML subtitles only when subtitles_enabled is true, "
                    "synchronize beat-level Audio, subtitles, and drawOps to scene.audioSegments when present, "
                    "add one global low-volume looping background Audio track only when background_music_url is provided, "
                    "use STXingkai/华文行楷/KaiTi/STKaiti for Chinese handwriting, never bold sans-serif, "
                    "include limited teaching accent colors and teacher-style whiteboard callouts, with a clean whiteboard background, "
                    f"render a moving HandPen with <Img src={{staticFile('{HAND_ASSET}')}} />, "
                    "use HAND_WIDTH >= 220 and PEN_TIP_X/PEN_TIP_Y offsets so the marker tip touches the active stroke, "
                    "define drawOps with kind/startFrame/endFrame/points, pointOnPolyline(), getActiveDrawOp(), "
                    "and getPenPosition(frame); pass getPenPosition(frame) to HandPen, "
                    "make text points move up/down/left/right inside words instead of sliding on a baseline, "
                    "avoid coarse scene-level tipX/tipY interpolation and avoid SVG <animate>, "
                    "and do not use CSS transitions/animations or nondeterministic timers."
                ),
            },
        ]
        try:
            raw = await chat_json(messages=repair_messages, model=settings.coder_model)
        except Exception as repair_error:
            logger.warning("Repaired Remotion TSX LLM call failed before validation: %s", repair_error)
            response = _compile_fast_remotion_response(
                req,
                (
                    "LLM TSX repair failed before validation, so ExplainFlow "
                    "compiled a self-contained Remotion whiteboard module from the storyboard."
                ),
            )
            tsx = response.tsx
            raw = {
                "duration_in_frames": response.duration_in_frames,
                "notes": response.notes,
            }
        candidate_tsx = raw.get("tsx") or raw.get("code")
        if candidate_tsx:
            try:
                tsx = _validate_generated_tsx_for_request(candidate_tsx, req)
            except ValueError as second_error:
                logger.warning("Repaired Remotion TSX failed validation: %s", second_error)
                response = _compile_fast_remotion_response(
                    req,
                    (
                        "LLM TSX failed stroke-following validation, so ExplainFlow "
                        "compiled a self-contained Remotion whiteboard module from the storyboard."
                    ),
                )
                tsx = response.tsx
                raw = {
                    "duration_in_frames": response.duration_in_frames,
                    "notes": response.notes,
                }
    try:
        raw_duration_frames = int(raw.get("duration_in_frames") or 0)
    except (TypeError, ValueError):
        raw_duration_frames = 0
    duration = max(req.fps * 10, target_frames, raw_duration_frames)

    return _cache_remotion_response(
        cache_key,
        GenerateRemotionCodeResponse(
            tsx=tsx,
            duration_in_frames=duration,
            fps=req.fps,
            width=req.width,
            height=req.height,
            notes=raw.get("notes"),
        ),
    )

