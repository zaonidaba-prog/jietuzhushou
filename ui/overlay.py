from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)


def grab_virtual_desktop() -> tuple[QImage, QRect, float]:
    screens = QGuiApplication.screens()
    if not screens:
        return QImage(), QRect(), 1.0

    virtual = QRect()
    for screen in screens:
        virtual = virtual.united(screen.geometry())

    dpr = max((screen.devicePixelRatio() for screen in screens), default=1.0)
    canvas = QImage(
        QSize(int(virtual.width() * dpr), int(virtual.height() * dpr)),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    canvas.fill(Qt.GlobalColor.black)

    painter = QPainter(canvas)
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        for screen in screens:
            pixmap = screen.grabWindow(0)
            if pixmap.isNull():
                log.warning("截取屏幕失败: %s", screen.name())
                continue
            geo = screen.geometry()
            target = QRectF(
                (geo.x() - virtual.x()) * dpr,
                (geo.y() - virtual.y()) * dpr,
                geo.width() * dpr,
                geo.height() * dpr,
            )
            painter.drawPixmap(target, pixmap, QRectF(0, 0, pixmap.width(), pixmap.height()))
    finally:
        painter.end()

    return canvas, virtual, dpr


class CaptureOverlay(QWidget):
    captured = Signal(QImage)
    canceled = Signal()
    failed = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        self._bg = QImage()
        self._dpr = 1.0
        self._virtual = QRect()
        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self._selecting = False
        self._finished = False

        self._bg, self._virtual, self._dpr = grab_virtual_desktop()
        self.setGeometry(self._virtual)

    def start(self) -> None:
        if self._bg.isNull() or self._bg.width() < 2 or self._bg.height() < 2:
            self.failed.emit("无法截取屏幕，请检查显示设置或权限")
            self.close()
            return
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self.grabKeyboard()
        self.update()

    def _selection(self) -> QRect:
        if self._origin is None or self._current is None:
            return QRect()
        return QRect(self._origin, self._current).normalized().intersected(self.rect())

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.drawImage(self.rect(), self._bg)
        p.fillRect(self.rect(), QColor(10, 15, 30, 118))

        sel = self._selection()
        if sel.width() > 1 and sel.height() > 1:
            src = QRectF(
                sel.x() * self._dpr,
                sel.y() * self._dpr,
                sel.width() * self._dpr,
                sel.height() * self._dpr,
            )
            p.drawImage(QRectF(sel), self._bg, src)

            p.setPen(QPen(QColor("#3B82F6"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(sel.adjusted(0, 0, -1, -1))

            # Corner handles
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#3B82F6"))
            for point in (
                sel.topLeft(),
                sel.topRight(),
                sel.bottomLeft(),
                sel.bottomRight(),
            ):
                p.drawEllipse(point, 4, 4)

            if self._current is not None:
                p.setPen(QPen(QColor(59, 130, 246, 90), 1))
                p.drawLine(self._current.x(), 0, self._current.x(), self.height())
                p.drawLine(0, self._current.y(), self.width(), self._current.y())

            self._paint_size_label(p, sel)

        self._paint_hint(p)
        p.end()

    def _paint_size_label(self, p: QPainter, sel: QRect) -> None:
        text = f"{sel.width()} × {sel.height()}"
        font = QFont("Microsoft YaHei UI", 10)
        p.setFont(font)
        fm = QFontMetrics(font)
        w = fm.horizontalAdvance(text) + 22
        h = 30
        x = sel.left()
        y = sel.bottom() + 8
        if y + h > self.height() - 8:
            y = sel.top() - h - 8
        if x + w > self.width() - 8:
            x = self.width() - w - 8
        x = max(8, x)
        y = max(8, y)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(15, 23, 42, 205))
        p.drawRoundedRect(QRect(x, y, w, h), 8, 8)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRect(x, y, w, h), Qt.AlignmentFlag.AlignCenter, text)

    def _paint_hint(self, p: QPainter) -> None:
        text = "拖拽选择区域      Enter 截取全屏      Esc 取消"
        font = QFont("Microsoft YaHei UI", 11)
        p.setFont(font)
        fm = QFontMetrics(font)
        w = fm.horizontalAdvance(text) + 36
        h = 38
        rect = QRect((self.width() - w) // 2, 22, w, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(15, 23, 42, 195))
        p.drawRoundedRect(rect, 12, 12)
        p.setPen(QColor("#F8FAFC"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            self._cancel()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._current = self._origin
            self._selecting = True
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._selecting:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or not self._selecting:
            return
        self._selecting = False
        self._current = event.position().toPoint()
        sel = self._selection()
        if sel.width() < 6 or sel.height() < 6:
            # A stray click should not throw the user out of capture mode.
            self._origin = None
            self._current = None
            self.update()
            return
        self._finish(sel)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._finish(self.rect())

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            sel = self._selection()
            self._finish(sel if sel.width() > 1 and sel.height() > 1 else self.rect())
            return
        super().keyPressEvent(event)

    def _finish(self, rect: QRect) -> None:
        if self._finished:
            return
        rect = rect.intersected(self.rect())
        if rect.width() < 2 or rect.height() < 2:
            return
        self._finished = True
        x = int(round(rect.x() * self._dpr))
        y = int(round(rect.y() * self._dpr))
        w = int(round(rect.width() * self._dpr))
        h = int(round(rect.height() * self._dpr))
        x = max(0, min(x, self._bg.width() - 1))
        y = max(0, min(y, self._bg.height() - 1))
        w = max(1, min(w, self._bg.width() - x))
        h = max(1, min(h, self._bg.height() - y))
        image = self._bg.copy(QRect(x, y, w, h))
        self.hide()
        self.releaseKeyboard()
        self.captured.emit(image)
        self.close()

    def _cancel(self) -> None:
        if self._finished:
            return
        self._finished = True
        self.hide()
        self.releaseKeyboard()
        self.canceled.emit()
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        super().closeEvent(event)
