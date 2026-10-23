from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "截图助手"
APP_VERSION = "1.0.1"


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / "AppData" / "Roaming"
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_screenshot_dir() -> Path:
    return Path.home() / "Pictures" / APP_NAME


def resource_path(relative: str) -> Path:
    """Path to a bundled resource, works both in source and PyInstaller builds."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent
    return base / relative


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
