import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        # When building from an sdist, web/ and scripts/ are absent —
        # the pre-generated assets are already included; nothing to do.
        if not (Path(self.root) / "web" / "sass" / "main.scss").exists():
            return
        subprocess.run(
            [sys.executable, Path(self.root) / "scripts" / "build.py"],
            check=True,
            cwd=self.root,
        )
