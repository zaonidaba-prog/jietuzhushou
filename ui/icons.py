from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

KIND_COLORS = {
    "text": "#2563EB",
    "image": "#059669",
    "file": "#D97706",
}
KIND_LABELS = {"text": "文", "image": "图", "file": "件"}


def _rounded_icon(size: int, bg: str, letter: str, font_size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(bg))
    radius = size * 0.28
    p.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.setPen(QColor("#FFFFFF"))
    font = QFont("Microsoft YaHei UI", font_size)
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, letter)
    p.end()
    return pm


def kind_icon(kind: str) -> QIcon:
    color = KIND_COLORS.get(kind, "#64748B")
    letter = KIND_LABELS.get(kind, "?")
    icon = QIcon()
    for size in (16, 20, 24, 32, 40):
        icon.addPixmap(_rounded_icon(size, color, letter, max(7, int(size * 0.52))))
    return icon


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_rounded_icon(size, "#2563EB", "截", max(8, int(size * 0.5))))
    return icon


def tray_icon() -> QIcon:
    return app_icon()
