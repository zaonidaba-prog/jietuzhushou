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

MIN_SELECTION = 6
HANDLE_SIZE = 8
BUTTON_SIZE = 34


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
    """Frozen-screen capture surface.

    New mode (default): drag a region, release, then move/resize the selection
    and press ✓ / Enter to accept, or ✕ / Esc to discard.
    Legacy mode: release immediately accepts and saves, like v1.0.1.
    """

    captured = Signal(QImage)
    canceled = Signal()
    failed = Signal(str)

    def __init__(self, legacy_mode: bool = False, parent: QWidget | None = None):
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

        self._legacy_mode = bool(legacy_mode)
        self._bg = QImage()
        self._dpr = 1.0
        self._virtual = QRect()
        self._bg, self._virtual, self._dpr = grab_virtual_desktop()
        self.setGeometry(self._virtual)

        self._sel = QRect()
        self._drag_mode: str | None = None
        self._drag_origin: QPoint | None = None
        self._drag_current: QPoint | None = None
        self._drag_start_sel = QRect()
        self._drag_offset = QPoint()
        self._resize_handle = ""
        self._mouse_pos = QPoint()
        self._check_rect = QRect()
        self._cancel_rect = QRect()
        self._finished = False

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

    # ------------------------------------------------------------------ geometry
    def _selection(self) -> QRect:
        if self._drag_mode == "new" and self._drag_origin is not None and self._drag_current is not None:
            return QRect(self._drag_origin, self._drag_current).normalized().intersected(self.rect())
        return self._sel.normalized().intersected(self.rect())

    @staticmethod
    def _valid(rect: QRect) -> bool:
        return rect.width() >= MIN_SELECTION and rect.height() >= MIN_SELECTION

    def _clamp_rect(self, rect: QRect) -> QRect:
        rect = rect.normalized()
        w = min(rect.width(), self.width())
        h = min(rect.height(), self.height())
        x = max(0, min(rect.x(), self.width() - w))
        y = max(0, min(rect.y(), self.height() - h))
        return QRect(x, y, w, h)

    @staticmethod
    def _adjust_resize(start: QRect, origin: QPoint, pos: QPoint, handle: str) -> QRect:
        r = QRect(start)
        dx = pos.x() - origin.x()
        dy = pos.y() - origin.y()
        min_w = MIN_SELECTION
        min_h = MIN_SELECTION

        if "l" in handle:
            r.setLeft(min(start.left() + dx, start.right() - min_w))
        if "r" in handle:
            r.setRight(max(start.right() + dx, start.left() + min_w))
        if "t" in handle:
            r.setTop(min(start.top() + dy, start.bottom() - min_h))
        if "b" in handle:
            r.setBottom(max(start.bottom() + dy, start.top() + min_h))
        return r.normalized()

    def _handle_at(self, pos: QPoint, sel: QRect) -> str:
        if self._legacy_mode or not self._valid(sel):
            return ""
        m = 10
        corners = {
            "tl": sel.topLeft(),
            "tr": sel.topRight(),
            "bl": sel.bottomLeft(),
            "br": sel.bottomRight(),
        }
        for name, point in corners.items():
            if QRect(point.x() - m, point.y() - m, 2 * m, 2 * m).contains(pos):
                return name
        if QRect(sel.left() + m, sel.top() - m, max(1, sel.width() - 2 * m), 2 * m).contains(pos):
            return "t"
        if QRect(sel.left() + m, sel.bottom() - m, max(1, sel.width() - 2 * m), 2 * m).contains(pos):
            return "b"
        if QRect(sel.left() - m, sel.top() + m, 2 * m, max(1, sel.height() - 2 * m)).contains(pos):
            return "l"
        if QRect(sel.right() - m, sel.top() + m, 2 * m, max(1, sel.height() - 2 * m)).contains(pos):
            return "r"
        return ""

    # ------------------------------------------------------------------ painting
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.drawImage(self.rect(), self._bg)
        p.fillRect(self.rect(), QColor(10, 15, 30, 118))

        sel = self._selection()
        if self._valid(sel):
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

            if not self._legacy_mode and self._drag_mode != "new":
                self._paint_handles(p, sel)
                self._paint_buttons(p, sel)
            else:
                self._check_rect = QRect()
                self._cancel_rect = QRect()

            self._paint_size_label(p, sel)

            if self._drag_mode == "new" and self._drag_current is not None:
                p.setPen(QPen(QColor(59, 130, 246, 90), 1))
                p.drawLine(self._drag_current.x(), 0, self._drag_current.x(), self.height())
                p.drawLine(0, self._drag_current.y(), self.width(), self._drag_current.y())
        else:
            self._check_rect = QRect()
            self._cancel_rect = QRect()

        self._paint_hint(p)
        p.end()

    def _paint_handles(self, p: QPainter, sel: QRect) -> None:
        p.setPen(QPen(QColor("#3B82F6"), 2))
        p.setBrush(QColor("#FFFFFF"))
        points = (
            sel.topLeft(),
            sel.topRight(),
            sel.bottomLeft(),
            sel.bottomRight(),
            QPoint(sel.center().x(), sel.top()),
            QPoint(sel.center().x(), sel.bottom()),
            QPoint(sel.left(), sel.center().y()),
            QPoint(sel.right(), sel.center().y()),
        )
        for point in points:
            p.drawRect(QRect(point.x() - HANDLE_SIZE // 2, point.y() - HANDLE_SIZE // 2, HANDLE_SIZE, HANDLE_SIZE))

    def _paint_buttons(self, p: QPainter, sel: QRect) -> None:
        size = BUTTON_SIZE
        gap = 8
        margin = 8
        if sel.width() >= 2 * size + gap + 2 * margin:
            x = sel.right() - 2 * size - gap - margin
            y = sel.bottom() - size - margin
        else:
            x = sel.left() + margin
            y = sel.bottom() + 8
            if y + size > self.height() - 6:
                y = sel.top() - size - 8
            if y < 6:
                y = sel.top() + margin
        x = max(4, min(x, self.width() - 2 * size - gap - 4))
        y = max(4, min(y, self.height() - size - 4))
        self._check_rect = QRect(x, y, size, size)
        self._cancel_rect = QRect(x + size + gap, y, size, size)

        for rect, color, symbol in (
            (self._check_rect, QColor("#16A34A"), "✓"),
            (self._cancel_rect, QColor("#DC2626"), "✕"),
        ):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawEllipse(rect)
            p.setPen(QColor("#FFFFFF"))
            font = QFont("Microsoft YaHei UI", 14)
            font.setBold(True)
            p.setFont(font)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, symbol)

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
        sel = self._selection()
        if self._legacy_mode:
            text = "拖拽选择区域      Enter 截取全屏      Esc 取消"
        elif self._valid(sel):
            text = "拖动选区移动 · 拖动边角缩放      Enter 确认      Esc 取消"
        else:
            text = "拖拽选择区域      Enter 全屏预览      Esc 取消"

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

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            self._cancel()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.position().toPoint()
        self._mouse_pos = pos

        if not self._legacy_mode and self._valid(self._sel):
            if self._check_rect.contains(pos):
                self._finish(self._sel)
                return
            if self._cancel_rect.contains(pos):
                self._cancel()
                return
            handle = self._handle_at(pos, self._sel)
            if handle:
                self._drag_mode = "resize"
                self._resize_handle = handle
                self._drag_start_sel = QRect(self._sel)
                self._drag_origin = pos
                return
            if self._sel.contains(pos):
                self._drag_mode = "move"
                self._drag_start_sel = QRect(self._sel)
                self._drag_offset = pos - self._sel.topLeft()
                return

        # Start a fresh selection (also the only mode in legacy flow).
        self._drag_mode = "new"
        self._drag_origin = pos
        self._drag_current = pos
        self._sel = QRect()
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position().toPoint()
        self._mouse_pos = pos

        if self._drag_mode == "new":
            self._drag_current = pos
            self.update()
            return

        if self._drag_mode == "move":
            new_top_left = pos - self._drag_offset
            self._sel = self._clamp_rect(QRect(new_top_left, self._drag_start_sel.size()))
            self.update()
            return

        if self._drag_mode == "resize":
            resized = self._adjust_resize(
                self._drag_start_sel, self._drag_origin or pos, pos, self._resize_handle
            )
            self._sel = self._clamp_rect(resized)
            self.update()
            return

        self._update_cursor(pos)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._drag_mode == "new":
            sel = self._selection()
            if self._valid(sel):
                self._sel = sel
            else:
                self._sel = QRect()
            self._drag_mode = None
            self._drag_origin = None
            self._drag_current = None
            if self._legacy_mode and self._valid(self._sel):
                self._finish(self._sel)
                return
            self.update()
            return

        if self._drag_mode in ("move", "resize"):
            self._drag_mode = None
            self.update()

    def _update_cursor(self, pos: QPoint) -> None:
        if self._legacy_mode:
            self.setCursor(Qt.CursorShape.CrossCursor)
            return
        if self._check_rect.contains(pos) or self._cancel_rect.contains(pos):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            return
        handle = self._handle_at(pos, self._sel)
        cursors = {
            "tl": Qt.CursorShape.SizeFDiagCursor,
            "br": Qt.CursorShape.SizeFDiagCursor,
            "tr": Qt.CursorShape.SizeBDiagCursor,
            "bl": Qt.CursorShape.SizeBDiagCursor,
            "t": Qt.CursorShape.SizeVerCursor,
            "b": Qt.CursorShape.SizeVerCursor,
            "l": Qt.CursorShape.SizeHorCursor,
            "r": Qt.CursorShape.SizeHorCursor,
        }
        if handle:
            self.setCursor(cursors[handle])
        elif self._sel.contains(pos):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    # ------------------------------------------------------------------ keyboard
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._legacy_mode:
                self._finish(self._sel if self._valid(self._sel) else self.rect())
            elif self._valid(self._sel):
                self._finish(self._sel)
            else:
                # First Enter selects the full screen and shows the ✓/✕ controls.
                self._sel = self.rect()
                self.update()
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        # Keep the old double-click full-screen shortcut only in legacy mode.
        if self._legacy_mode and event.button() == Qt.MouseButton.LeftButton:
            self._finish(self.rect())

    # ------------------------------------------------------------------ finish
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
