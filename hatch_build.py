import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        # The sdist ships pre-generated assets and excludes the build tooling
        # (scripts/). When build.py is absent we are building from an sdist —
        # there is nothing to regenerate.
        build_script = Path(self.root) / "scripts" / "build.py"
        if not build_script.exists():
            return
        subprocess.run(
            [sys.executable, build_script],
            check=True,
            cwd=self.root,
        )
