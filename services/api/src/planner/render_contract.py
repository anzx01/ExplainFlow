"""Deterministic render contract validation and timeline compilation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .models import RenderElement, RenderRegion, RenderReveal, Scene, Storyboard


@dataclass(frozen=True)
class ContractIssue:
    code: str
    message: str
    severity: str = "error"
    scene_id: str | None = None
    element_id: str | None = None


def _region_inside(region: RenderRegion, width: int, height: int) -> bool:
    return (
        region.x >= 0
        and region.y >= 0
        and region.width > 0
        and region.height > 0
        and region.x + region.width <= width
        and region.y + region.height <= height
    )


def _overlap(a: RenderRegion, b: RenderRegion) -> bool:
    return not (
        a.x + a.width <= b.x
        or b.x + b.width <= a.x
        or a.y + a.height <= b.y
        or b.y + b.height <= a.y
    )


def compile_scene_timeline(scene: Scene, *, fps: int = 30) -> list[dict]:
    """Return a stable, renderer-neutral timeline for a scene."""
    cursor = 0
    group_start: dict[str, int] = {}
    group_end: dict[str, int] = {}
    items: list[dict] = []
    for element in sorted(scene.render_elements, key=lambda item: (item.sequence, item.id)):
        reveal = element.reveal
        if element.parallel_group and element.parallel_group in group_start:
            start = group_start[element.parallel_group]
        else:
            start = max(cursor, reveal.start_ms)
        duration = reveal.duration_ms
        if element.parallel_group:
            group_start.setdefault(element.parallel_group, start)
            group_end[element.parallel_group] = max(group_end.get(element.parallel_group, 0), start + duration)
        items.append(
            {
                "id": element.id,
                "sequence": element.sequence,
                "startMs": start,
                "durationMs": duration,
                "endMs": start + duration,
                "startFrame": round(start * fps / 1000),
                "endFrame": round((start + duration) * fps / 1000),
                "region": element.region.model_dump(mode="json"),
                "protectedRegions": [r.model_dump(mode="json") for r in reveal.protected_regions],
                "narrativeRole": element.narrative_role,
                "subtitle": element.subtitle,
            }
        )
        cursor = max(cursor, start + duration)
    return items


def validate_scene_contract(scene: Scene, *, total_duration_ms: int | None = None) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    width, height = scene.canvas_width, scene.canvas_height
    previous_sequence = 0
    previous_end = 0
    elements = sorted(scene.render_elements, key=lambda item: (item.sequence, item.id))
    asset = scene.asset_contract
    if asset:
        required_layers = {"text", "ink", "color"}
        if asset.mode == "trace":
            if not asset.master_asset:
                issues.append(ContractIssue("asset_master_missing", "Trace asset contract requires masterAsset", "error", scene.id))
            if not asset.ink_asset:
                issues.append(ContractIssue("asset_ink_missing", "Trace asset contract requires inkAsset", "error", scene.id))
            if not asset.color_asset:
                issues.append(ContractIssue("asset_color_missing", "Trace asset contract requires colorAsset", "error", scene.id))
        elif asset.mode == "full":
            if not asset.color_asset:
                issues.append(ContractIssue("full_asset_missing", "Full asset contract requires colorAsset", "error", scene.id))
            if set(asset.layers) != {"color"}:
                issues.append(ContractIssue("full_asset_layers_invalid", "Full asset mode can only expose the color layer", "error", scene.id))
        if asset.width and asset.height and asset.observed_content_bounds:
            bounds = asset.observed_content_bounds
            if bounds.x + bounds.width > asset.width or bounds.y + bounds.height > asset.height:
                issues.append(ContractIssue("asset_bounds_out_of_bounds", "Observed asset content bounds exceed the source asset", "error", scene.id))
        if asset.layers and asset.layers != sorted(asset.layers, key=lambda layer: {"text": 0, "ink": 1, "detail": 2, "color": 3}.get(layer, 99)):
            issues.append(ContractIssue("asset_layer_order_invalid", "Asset layers must be ordered text, ink, detail, color", "error", scene.id))
    for element_index, element in enumerate(elements):
        if element.sequence <= previous_sequence:
            issues.append(ContractIssue("sequence_not_increasing", "Element sequence must be strictly increasing", element_id=element.id))
        previous_sequence = element.sequence
        if not _region_inside(element.region, width, height):
            issues.append(ContractIssue("region_out_of_bounds", "Element region is outside the scene canvas", element_id=element.id))
        reveal = element.reveal
        previous_element = elements[element_index - 1] if element_index > 0 else None
        same_parallel_group = bool(
            previous_element
            and element.parallel_group
            and element.parallel_group == previous_element.parallel_group
        )
        if reveal.start_ms < previous_end and not same_parallel_group:
            issues.append(ContractIssue("timeline_overlap", "Element reveal overlaps the previous element; use explicit concurrency before allowing overlap", element_id=element.id))
        if reveal.start_ms + reveal.duration_ms > (total_duration_ms or 2**31 - 1):
            issues.append(ContractIssue("timeline_out_of_bounds", "Element ends after the scene duration", element_id=element.id))
        for protected in reveal.protected_regions:
            if not _region_inside(protected, width, height):
                issues.append(ContractIssue("protected_region_out_of_bounds", "Protected region is outside the scene canvas", element_id=element.id))
            if _overlap(protected, element.region):
                issues.append(ContractIssue("protected_region_overlap", "Protected region overlaps its own draw region", "warning", element_id=element.id))
        previous_end = max(previous_end, reveal.start_ms + reveal.duration_ms)
    return issues


def validate_storyboard_contract(storyboard: Storyboard, *, fps: int = 30) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    scene_cursor_ms = 0
    for scene in sorted(storyboard.scenes, key=lambda item: (item.order, item.id)):
        duration_ms = max(1, round(scene.duration_estimate * 1000))
        for issue in validate_scene_contract(scene, total_duration_ms=duration_ms):
            issues.append(ContractIssue(issue.code, issue.message, issue.severity, scene.id, issue.element_id))
        if scene.render_elements:
            last_end = max(item.reveal.start_ms + item.reveal.duration_ms for item in scene.render_elements)
            if duration_ms - last_end < 500:
                issues.append(ContractIssue("missing_hold", "Scene must hold the completed artwork for at least 500ms", "warning", scene.id))
        scene_cursor_ms += duration_ms
    return issues


def ensure_scene_contract_defaults(scene: Scene) -> Scene:
    """Populate deterministic element defaults without inventing visual content."""
    duration_ms = max(1000, round(scene.duration_estimate * 1000))

    # Keep the completed artwork visible after the last reveal. This is part of
    # the scene contract, so hand-authored and model-authored elements follow
    # the same rule. Clamping the final reveal preserves the requested scene
    # duration and avoids adding an unvoiced tail during audio retiming.
    if scene.render_elements:
        ordered = sorted(scene.render_elements, key=lambda item: (item.sequence, item.id))
        last = ordered[-1]
        reveal = last.reveal
        latest_end = reveal.start_ms + reveal.duration_ms
        hold_start = max(0, duration_ms - 500)
        if latest_end > hold_start:
            if reveal.start_ms >= hold_start:
                reveal.start_ms = max(0, hold_start - 1)
            reveal.duration_ms = max(1, hold_start - reveal.start_ms)
        if not all(item.source == "generated" for item in scene.render_elements):
            return scene

    elements: list[RenderElement] = []
    count = max(len(scene.animations), 1)
    available_height = max(1, scene.canvas_height - 160)
    row_height = max(1, min(140, available_height // count))
    x = min(80, max(0, (scene.canvas_width - 1) // 4))
    region_width = max(1, scene.canvas_width - 2 * x)
    usable_ms = max(500, duration_ms - 500)
    for index, animation in enumerate(scene.animations, start=1):
        start_ms = round((index - 1) * usable_ms / count)
        next_ms = round(index * usable_ms / count)
        elements.append(
            RenderElement(
                id=f"{scene.id}-element-{index}",
                sequence=index,
                narrative_role="content",
                subtitle=animation.content[:240] or None,
                region=RenderRegion(
                    x=x,
                    y=min(scene.canvas_height - row_height, 80 + (index - 1) * row_height),
                    width=region_width,
                    height=row_height,
                ),
                reveal=RenderReveal(start_ms=start_ms, duration_ms=max(1, next_ms - start_ms)),
                source="generated",
            )
        )
    scene.render_elements = elements
    return scene


def finalize_storyboard_contract(storyboard: Storyboard, *, fps: int = 30) -> Storyboard:
    """Finalize generated elements after all scene-duration transforms."""
    for scene in storyboard.scenes:
        ensure_scene_contract_defaults(scene)
        timeline = compile_scene_timeline(scene, fps=fps)
        by_id = {item.id: item for item in scene.render_elements}
        for entry in timeline:
            element = by_id[entry["id"]]
            element.reveal.start_ms = entry["startMs"]
    issues = validate_storyboard_contract(storyboard, fps=fps)
    hard = [issue for issue in issues if issue.severity == "error"]
    if hard:
        summary = "; ".join(
            f"{issue.scene_id or 'storyboard'}:{issue.element_id or '-'}:{issue.code}"
            for issue in hard
        )
        raise ValueError(f"Storyboard render contract failed: {summary}")
    storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
    if storyboard.style_lock and not storyboard.style_fingerprint:
        storyboard.style_fingerprint = hashlib.sha256(storyboard.style_lock.encode("utf-8")).hexdigest()[:16]
    if storyboard.character_lock and not storyboard.character_fingerprint:
        storyboard.character_fingerprint = hashlib.sha256(storyboard.character_lock.encode("utf-8")).hexdigest()[:16]
    return storyboard
