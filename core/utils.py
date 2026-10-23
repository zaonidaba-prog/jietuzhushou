from __future__ import annotations

import hashlib
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QImage, QKeySequence


def setup_logging() -> Path:
    from .paths import app_data_dir

    log_dir = app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    root = logging.getLogger()
    if root.handlers:
        return log_file

    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    if sys.stderr is not None:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    return log_file


def normalize_preview(text: str, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def image_to_png_bytes(image: QImage) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def image_hash(image: QImage) -> str:
    return sha256_bytes(image_to_png_bytes(image))


def format_time(iso: str) -> str:
    try:
        dt = datetime.strptime(iso, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso
    now = datetime.now()
    if dt.date() == now.date():
        return "今天 " + dt.strftime("%H:%M")
    if (now.date() - dt.date()).days == 1:
        return "昨天 " + dt.strftime("%H:%M")
    if dt.year == now.year:
        return dt.strftime("%m-%d %H:%M")
    return dt.strftime("%Y-%m-%d %H:%M")


def timestamp_for_filename() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


def unique_path(folder: Path, prefix: str, suffix: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{prefix}_{timestamp_for_filename()}{suffix}"


def qt_key_to_hotkey_string(seq: QKeySequence) -> str:
    """QKeySequence -> 'Alt+Q' style string usable by RegisterHotKey parser."""
    return seq.toString(QKeySequence.SequenceFormat.NativeText).strip()
