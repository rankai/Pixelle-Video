"""Joint backend/desktop gate for the digital-human V2 rollout."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DigitalHumanFeatureGate:
    backend_flag: bool
    desktop_flag: bool
    backend_ready: bool
    desktop_ready: bool

    @property
    def v2_enabled(self) -> bool:
        return self.backend_flag and self.desktop_flag and self.backend_ready and self.desktop_ready

    @property
    def legacy_route_available(self) -> bool:
        # The desktop switch controls V2 visibility only.  Turning it off must
        # never make the already-supported V1 route disappear.
        return not self.v2_enabled

    @property
    def v2_entry_visible(self) -> bool:
        return self.desktop_flag and self.desktop_ready and self.backend_flag and self.backend_ready


def evaluate_digital_human_feature_gate(
    *, backend_flag: bool, desktop_flag: bool, backend_ready: bool, desktop_ready: bool
) -> DigitalHumanFeatureGate:
    return DigitalHumanFeatureGate(
        backend_flag=bool(backend_flag),
        desktop_flag=bool(desktop_flag),
        backend_ready=bool(backend_ready),
        desktop_ready=bool(desktop_ready),
    )
