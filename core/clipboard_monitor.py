from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QClipboard, QGuiApplication, QImage

from .db import HistoryDB
from .utils import (
    image_hash,
    normalize_preview,
    sha256_text,
    timestamp_for_filename,
)

log = logging.getLogger(__name__)


def hash_for_text(text: str) -> str:
    return sha256_text(text)


def hash_for_files(paths: list[str]) -> str:
    return sha256_text("file:" + "\0".join(paths))


class ClipboardMonitor(QObject):
    item_added = Signal(int)
    error = Signal(str)

    def __init__(self, db: HistoryDB, images_dir: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.db = db
        self.images_dir = images_dir
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.paused = False
        self._clipboard: QClipboard = QGuiApplication.clipboard()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(140)
        self._timer.timeout.connect(self._process)
        self._last_hash = ""
        self._last_kind = ""
        self._last_time = 0.0
        self._ignore_hash = ""
        self._ignore_until = 0.0
        self._retry = 0

    def start(self) -> None:
        self._clipboard.dataChanged.connect(self._on_data_changed)
        log.info("剪贴板监听已启动")

    def stop(self) -> None:
        try:
            self._clipboard.dataChanged.disconnect(self._on_data_changed)
        except Exception:
            pass

    def suppress(self, content_hash: str, seconds: float = 1.5) -> None:
        self._ignore_hash = content_hash
        self._ignore_until = time.monotonic() + seconds

    def _on_data_changed(self) -> None:
        if self.paused:
            return
        self._retry = 0
        self._timer.start()

    def _process(self) -> None:
        if self.paused:
            return
        md = self._clipboard.mimeData()
        if md is None:
            if self._retry < 2:
                self._retry += 1
                self._timer.start(100)
            return

        try:
            kind, text, preview, image_path, files, digest = self._read(md)
        except Exception:
            log.exception("读取剪贴板内容失败")
            return

        if not kind:
            if self._retry < 2:
                self._retry += 1
                self._timer.start(100)
            return

        now = time.monotonic()
        if (
            self._ignore_hash
            and digest == self._ignore_hash
            and now <= self._ignore_until
        ):
            self._discard_image(image_path)
            self._ignore_hash = ""
            self._last_hash = digest
            self._last_kind = kind
            self._last_time = now
            return

        # A single copy can emit several dataChanged signals, and image data may
        # be re-announced when the source process releases clipboard ownership.
        # Collapse those, but keep genuinely repeated copies made later.
        dedupe_window = {"text": 1.8, "image": 8.0, "file": 3.0}.get(kind, 2.0)
        if (
            digest == self._last_hash
            and kind == self._last_kind
            and (now - self._last_time) < dedupe_window
        ):
            self._discard_image(image_path)
            return

        self._last_hash = digest
        self._last_kind = kind
        self._last_time = now

        try:
            item_id = self.db.add_item(
                kind=kind,
                text=text,
                preview=preview,
                image_path=image_path,
                file_paths=files,
                content_hash=digest,
            )
        except Exception:
            log.exception("写入剪贴板历史失败")
            self._discard_image(image_path)
            self.error.emit("写入剪贴板历史失败")
            return

        log.info("记录剪贴板条目 #%s (%s)", item_id, kind)
        self.item_added.emit(item_id)

    @staticmethod
    def _discard_image(image_path: str) -> None:
        if not image_path:
            return
        try:
            Path(image_path).unlink(missing_ok=True)
        except Exception:
            log.exception("清理未采用的剪贴板图片失败: %s", image_path)

    def _read(self, md):
        # Files first: copying files also provides URL text.
        if md.hasUrls():
            urls = [u for u in md.urls() if u.isLocalFile()]
            paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
            if paths:
                if len(paths) == 1:
                    preview = Path(paths[0]).name or paths[0]
                else:
                    preview = f"{Path(paths[0]).name} 等 {len(paths)} 个文件"
                return (
                    "file",
                    "\n".join(paths),
                    preview,
                    "",
                    paths,
                    hash_for_files(paths),
                )

        # Image content.
        if md.hasImage():
            image = self._clipboard.image()
            if image is None or image.isNull():
                data = md.imageData()
                image = QImage(data) if data is not None else QImage()
            if not image.isNull():
                name = f"clip_{timestamp_for_filename()}_{uuid.uuid4().hex[:6]}.png"
                path = self.images_dir / name
                if image.save(str(path), "PNG"):
                    preview = f"[图片] {image.width()}×{image.height()}"
                    return "image", "", preview, str(path), [], image_hash(image)
                log.error("剪贴板图片保存失败: %s", path)

        # Plain text (includes copied file paths from apps that only provide text).
        if md.hasText():
            text = md.text()
            if text:
                preview = normalize_preview(text)
                if not preview:
                    preview = "(空白文本)"
                return "text", text, preview, "", [], hash_for_text(text)

        return "", "", "", "", [], ""
