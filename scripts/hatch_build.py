import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        subprocess.run(
            [sys.executable, Path(self.root) / "scripts" / "build.py"],
            check=True,
            cwd=self.root,
        )
        build_data["artifacts"].extend([
            "src/botamusique/static",
            "src/botamusique/web/templates",
        ])
