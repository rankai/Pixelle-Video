"""Douyin publishing adapter skeleton.

The adapter prepares a draft and deliberately stops before final publishing.
"""

from pixelle_video.services.publish.browser_runtime import BrowserRuntime
from pixelle_video.services.publish.platforms.base import HumanConfirmedPublisher

DOUYIN_CREATOR_PLATFORM = "douyin"


class DouyinPublisher(HumanConfirmedPublisher):
    """Prepare Douyin drafts through an injected browser runtime."""

    def __init__(self, runtime: BrowserRuntime):
        super().__init__(runtime, DOUYIN_CREATOR_PLATFORM)
