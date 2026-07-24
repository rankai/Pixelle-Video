"""Server-owned digital-human workflow profile catalog.

The desktop submits a semantic profile only.  Provider workflow filenames and
IDs remain server facts and are never accepted from application input.
"""

from __future__ import annotations

from dataclasses import dataclass


class DigitalHumanWorkflowError(ValueError):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(f"{code}: {message or code}")


@dataclass(frozen=True)
class WorkflowBinding:
    mode: str
    profile: str
    workflow_revision: str
    workflow_key: str
    release_state: str


_CATALOG: dict[tuple[str, str], WorkflowBinding] = {
    ("image_talking", "stable"): WorkflowBinding(
        "image_talking", "stable", "digital_combination.v1", "digital_combination", "pilot_verified"
    ),
    ("image_talking", "natural"): WorkflowBinding(
        "image_talking",
        "natural",
        "digital_talk_image_prompt.v1",
        "digital_talk_image_prompt",
        "candidate",
    ),
    ("video_lipsync", "natural"): WorkflowBinding(
        "video_lipsync",
        "natural",
        "digital_lip_sync_video.v1",
        "digital_lip_sync_video",
        "stable",
    ),
}


def resolve_workflow_profile(
    mode: str, profile: str, *, require_released: bool = True
) -> WorkflowBinding:
    binding = _CATALOG.get((str(mode).strip(), str(profile).strip()))
    if binding is None:
        raise DigitalHumanWorkflowError("DIGITAL_HUMAN_WORKFLOW_PROFILE_INVALID")
    if require_released and binding.release_state not in {"pilot_verified", "stable"}:
        raise DigitalHumanWorkflowError("DIGITAL_HUMAN_WORKFLOW_NOT_RELEASED")
    return binding


def list_workflow_profiles() -> tuple[WorkflowBinding, ...]:
    return tuple(_CATALOG.values())
