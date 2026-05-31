"""Browser runtime abstraction for desktop publishing automation."""

from typing import Any, Protocol

DEFAULT_BROWSER_RUNTIME = "playwright"
SUPPORTED_BROWSER_RUNTIMES = {"playwright", "cloakbrowser"}


class BrowserRuntime(Protocol):
    """Protocol implemented by browser automation runtimes."""

    async def launch_persistent_context(self, platform: str) -> Any:
        """Open or reuse a persistent browser context for a platform."""

    async def close(self) -> None:
        """Close browser resources owned by this runtime."""
