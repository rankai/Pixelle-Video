"""Fail-closed AppRun state transitions."""

from __future__ import annotations

APP_RUN_STATES = frozenset({"draft", "queued", "running", "needs_review", "completed", "failed", "cancelled"})
TERMINAL_APP_RUN_STATES = frozenset({"completed", "failed", "cancelled"})
ALLOWED_APP_RUN_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"queued", "cancelled"}),
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset({"needs_review", "completed", "failed", "cancelled"}),
    "needs_review": frozenset({"completed", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset({"queued", "cancelled"}),
    "cancelled": frozenset(),
}


class InvalidAppRunTransition(ValueError):
    """Raised when a state transition is not allowed."""


def validate_app_run_state(state: str) -> str:
    if state not in APP_RUN_STATES:
        raise InvalidAppRunTransition(f"unknown AppRun state: {state}")
    return state


def validate_transition(current: str, target: str) -> None:
    validate_app_run_state(current)
    validate_app_run_state(target)
    if target not in ALLOWED_APP_RUN_TRANSITIONS[current]:
        raise InvalidAppRunTransition(f"invalid AppRun transition: {current} -> {target}")
