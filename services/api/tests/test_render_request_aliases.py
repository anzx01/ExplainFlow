import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.render.models import RenderJobRequest
from src.planner.models import GenerateRemotionCodeRequest


def _request_payload(**extra):
    return {
        "storyboard": {
            "topic": "test",
            "total_duration_estimate": 1,
            "video_style": "whiteboard",
            "pen_style": "marker",
            "scenes": [],
        },
        **extra,
    }


def test_force_render_accepts_frontend_camel_case():
    request = RenderJobRequest.model_validate(_request_payload(forceRender=True))
    assert request.force_render is True


def test_force_render_accepts_api_snake_case():
    request = RenderJobRequest.model_validate(_request_payload(force_render=True))
    assert request.force_render is True


def test_force_render_defaults_to_false():
    request = RenderJobRequest.model_validate(_request_payload())
    assert request.force_render is False


def test_remotion_codegen_defaults_to_fast_teaching_video_profile():
    request = GenerateRemotionCodeRequest(storyboard=_request_payload()["storyboard"])
    assert (request.width, request.height, request.fps) == (960, 540, 24)
