import subprocess
import sys


def test_streamlit_legacy_imports_do_not_require_heavy_optional_dependencies():
    script = """
import importlib.abc
import sys

blocked = {"comfykit", "moviepy", "playwright"}


class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in blocked:
            raise ImportError(f"blocked optional dependency: {fullname}")
        return None


sys.meta_path.insert(0, Blocker())

import pixelle_video.service  # noqa: F401
import web.pipelines  # noqa: F401
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
