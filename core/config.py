from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import app_data_dir, default_screenshot_dir

log = logging.getLogger(__name__)


@dataclass
class Config:
    screenshot_dir: str = field(default_factory=lambda: str(default_screenshot_dir()))
    hotkey_capture: str = "Alt+Q"
    hotkey_history: str = "Alt+V"
    autostart: bool = True
    clipboard_paused: bool = False
    legacy_capture: bool = False
    first_run_done: bool = False

    @property
    def path(self) -> Path:
        return app_data_dir() / "config.json"

    @classmethod
    def load(cls) -> "Config":
        path = app_data_dir() / "config.json"
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            log.exception("读取配置失败，使用默认配置")
            return cls()

        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in known}
        cfg = cls(**clean)
        if not cfg.screenshot_dir:
            cfg.screenshot_dir = str(default_screenshot_dir())
        return cfg

    def save(self) -> None:
        path = self.path
        tmp = path.with_suffix(".json.tmp")
        data = asdict(self)
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
