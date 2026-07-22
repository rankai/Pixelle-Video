"""Publishing adapters for creator platforms supported by the desktop assistant."""

from pixelle_video.services.publish.browser_runtime import BrowserRuntime
from pixelle_video.services.publish.platforms.base import HumanConfirmedPublisher


class XiaohongshuPublisher(HumanConfirmedPublisher):
    def __init__(self, runtime: BrowserRuntime):
        super().__init__(runtime, "xiaohongshu")


class ShipinhaoPublisher(HumanConfirmedPublisher):
    def __init__(self, runtime: BrowserRuntime):
        super().__init__(runtime, "shipinhao")


class KuaishouPublisher(HumanConfirmedPublisher):
    def __init__(self, runtime: BrowserRuntime):
        super().__init__(runtime, "kuaishou")
