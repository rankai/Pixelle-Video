"""IP broadcast API schemas."""

from typing import Any

from pydantic import BaseModel, Field


class IpBroadcastCreateSessionResponse(BaseModel):
    session_id: str
    current_step: int
    completed_steps: int
    next_action: dict[str, Any]
    missing_requirements: list[str]
    step_status: dict[int, str]
    notices: dict[int, dict[str, str]]
    artifacts: dict[str, str]
    state: dict[str, Any]


class IpBroadcastConfigPatch(BaseModel):
    model_config = {"extra": "allow"}

    values: dict[str, Any] = Field(default_factory=dict)

    def flattened(self) -> dict[str, Any]:
        data = self.model_dump(exclude={"values"})
        return {**self.values, **{key: value for key, value in data.items() if value is not None}}


class IpBroadcastRunStepResponse(BaseModel):
    session_id: str
    step_key: str
    task_id: str
