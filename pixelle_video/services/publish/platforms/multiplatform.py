"""Publishing adapters for creator platforms supported by the desktop assistant."""

from pathlib import Path
from typing import Any, Awaitable, Callable

from pixelle_video.services.publish.browser_runtime import BrowserRuntime
from pixelle_video.services.publish.execution_protocol import (
    PublishExecutionCheckpoint,
    PublishStage,
)
from pixelle_video.services.publish.platforms.base import HumanConfirmedPublisher


class XiaohongshuPublisher(HumanConfirmedPublisher):
    def __init__(self, runtime: BrowserRuntime, *, profile_path: str | Path | None = None, account_id: str | None = None, profile_ref: str | None = None, checkpoint: PublishExecutionCheckpoint | None = None, checkpoint_callback: Callable[[PublishExecutionCheckpoint, PublishStage, str | None], Awaitable[Any] | Any] | None = None):
        super().__init__(runtime, "xiaohongshu", profile_path=profile_path, account_id=account_id, profile_ref=profile_ref, checkpoint=checkpoint, checkpoint_callback=checkpoint_callback)


class ShipinhaoPublisher(HumanConfirmedPublisher):
    def __init__(self, runtime: BrowserRuntime, *, profile_path: str | Path | None = None, account_id: str | None = None, profile_ref: str | None = None, checkpoint: PublishExecutionCheckpoint | None = None, checkpoint_callback: Callable[[PublishExecutionCheckpoint, PublishStage, str | None], Awaitable[Any] | Any] | None = None):
        super().__init__(runtime, "shipinhao", profile_path=profile_path, account_id=account_id, profile_ref=profile_ref, checkpoint=checkpoint, checkpoint_callback=checkpoint_callback)


class KuaishouPublisher(HumanConfirmedPublisher):
    def __init__(self, runtime: BrowserRuntime, *, profile_path: str | Path | None = None, account_id: str | None = None, profile_ref: str | None = None, checkpoint: PublishExecutionCheckpoint | None = None, checkpoint_callback: Callable[[PublishExecutionCheckpoint, PublishStage, str | None], Awaitable[Any] | Any] | None = None):
        super().__init__(runtime, "kuaishou", profile_path=profile_path, account_id=account_id, profile_ref=profile_ref, checkpoint=checkpoint, checkpoint_callback=checkpoint_callback)
