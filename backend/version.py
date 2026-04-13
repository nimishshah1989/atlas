"""Version metadata — populated at deploy time from git."""

import os
import subprocess
from pathlib import Path

VERSION = "1.0.0"


def _resolve_git_sha() -> str:
    env = os.environ.get("ATLAS_GIT_SHA")
    if env:
        return env[:12]
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


GIT_SHA = _resolve_git_sha()
