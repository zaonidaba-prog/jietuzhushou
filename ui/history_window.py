from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from core.db import ClipboardItem, HistoryDB
from core.utils import format_time
from .icons import app_icon, kind_icon

ROLE_ID = int(Qt.ItemDataRole.UserRole)
ROLE_KIND = ROLE_ID + 1
ROLE_PREVIEW = ROLE_ID + 2
ROLE_TIME = ROLE_ID + 3
ROLE_PINNED = ROLE_ID + 4
ROLE_TOOLTIP = ROLE_ID + 5

log = logging.getLogger(__name__)

KIND_LABELS = {"text": "文本", "image": "图片", "file": "文件"}
KIND_COLORS = {"text": "#2563EB", "image": "#059669", "file": "#D97706"}
KIND_LETTERS = {"text": "文", "image": "图", "file": "件"}

PAGE_SIZE = 120


class ClipboardItemDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = option.rect.adjusted(8, 3, -8, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            bg = QColor("#EAF2FF")
            border = QColor("#BFDBFE")
        elif hovered:
            bg = QColor("#F8FAFC")
            border = QColor("#E2E8F0")
        else:
            bg = QColor("#FFFFFF")
            border = QColor("#EDF1F7")

        painter.setPen(border)
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 11, 11)
        painter.setClipRect(rect)

        kind = index.data(ROLE_KIND) or "text"
        color = QColor(KIND_COLORS.get(kind, "#64748B"))
        letter = KIND_LETTERS.get(kind, "?")

        icon_rect = QRect(rect.left() + 14, rect.top() + (rect.height() - 36) // 2, 36, 36)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(icon_rect, 10, 10)
        painter.setPen(QColor("#FFFFFF"))
        icon_font = QFont("Microsoft YaHei UI", 11)
        icon_font.setBold(True)
        painter.setFont(icon_font)
        painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, letter)

        text_left = icon_rect.right() + 13
        text_width = rect.right() - text_left - 34

        preview = index.data(ROLE_PREVIEW) or ""
        preview_font = QFont("Microsoft YaHei UI", 10)
        preview_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(preview_font)
        painter.setPen(QColor("#0F172A"))
        fm = QFontMetrics(preview_font)
        preview_text = fm.elidedText(
            str(preview).replace("\n", " "), Qt.TextElideMode.ElideRight, text_width
        )
        painter.drawText(
            QRect(text_left, rect.top() + 9, text_width, 22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            preview_text,
        )

        meta_font = QFont("Microsoft YaHei UI", 8.5)
        painter.setFont(meta_font)
        painter.setPen(QColor("#7C8BA1"))
        meta = f"{index.data(ROLE_TIME) or ''}  ·  {KIND_LABELS.get(kind, kind)}"
        if index.data(ROLE_PINNED):
            meta += "  ·  ★ 已收藏"
        painter.drawText(
            QRect(text_left, rect.top() + 33, text_width, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            meta,
        )

        if index.data(ROLE_PINNED):
            painter.setFont(QFont("Microsoft YaHei UI", 11))
            painter.setPen(QColor("#F59E0B"))
            painter.drawText(
                QRect(rect.right() - 32, rect.top() + 10, 24, 24),
                Qt.AlignmentFlag.AlignCenter,
                "★",
            )

        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), 76)


class HistoryWindow(QWidget):
    copy_requested = Signal(int)
    pin_requested = Signal(int, bool)
    delete_requested = Signal(int)
    clear_requested = Signal()
    pause_toggle_requested = Signal()
    settings_requested = Signal()
    open_data_dir_requested = Signal()

    def __init__(self, db: HistoryDB, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("剪贴板历史 - 截图助手")
        self.setWindowIcon(app_icon())
        self.resize(1080, 680)
        self.setMinimumSize(840, 520)

        self._offset = 0
        self._total = 0
        self._has_more = False
        self._paused = False
        self._dirty = True
        self._preview_item_id: int | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("剪贴板历史")
        title.setProperty("class", "title")
        subtitle = QLabel("复制过的文字、图片、文件都在这里 · 单击查看全文 · 双击复制")
        subtitle.setProperty("class", "subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)

        settings_btn = QPushButton("设置")
        settings_btn.setProperty("class", "ghost")
        settings_btn.clicked.connect(self.settings_requested.emit)
        header.addWidget(settings_btn)
        root.addLayout(header)

        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索文字、文件名…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search, 1)

        self.filter = QComboBox()
        self.filter.addItem("全部", "all")
        self.filter.addItem("文本", "text")
        self.filter.addItem("图片", "image")
        self.filter.addItem("文件", "file")
        self.filter.addItem("收藏", "pinned")
        self.filter.setFixedWidth(112)
        self.filter.currentIndexChanged.connect(self._on_filter_changed)
        search_row.addWidget(self.filter)
        root.addLayout(search_row)

        self.pause_banner = QFrame()
        self.pause_banner.setProperty("class", "banner")
        banner_layout = QHBoxLayout(self.pause_banner)
        banner_layout.setContentsMargins(14, 9, 10, 9)
        banner_label = QLabel("剪贴板记录已暂停，当前复制的内容不会进入历史。")
        banner_label.setStyleSheet("color: #9A3412;")
        banner_layout.addWidget(banner_label, 1)
        resume_btn = QPushButton("继续记录")
        resume_btn.clicked.connect(self.pause_toggle_requested.emit)
        banner_layout.addWidget(resume_btn)
        self.pause_banner.hide()
        root.addWidget(self.pause_banner)

        self.stack = QStackedWidget()
        self.list = QListWidget()
        self.list.setItemDelegate(ClipboardItemDelegate(self.list))
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list.setMouseTracking(True)
        self.list.setSpacing(0)
        self.list.itemDoubleClicked.connect(self._on_double_click)
        self.list.currentItemChanged.connect(self._on_current_item_changed)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._show_context_menu)
        self.list.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.stack.addWidget(self.list)

        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon = QLabel("📋")
        empty_icon.setStyleSheet("font-size: 44pt;")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title = QLabel("还没有记录")
        empty_title.setStyleSheet("font-size: 14pt; font-weight: 700; color: #334155;")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_hint = QLabel("在任何软件里复制文字、图片或文件，都会自动出现在这里。")
        empty_hint.setProperty("class", "subtitle")
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addStretch(1)
        empty_layout.addWidget(empty_icon)
        empty_layout.addSpacing(4)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_hint)
        empty_layout.addStretch(1)
        self.stack.addWidget(empty)

        # Right-hand preview: click any row to read the complete content.
        self.preview_panel = QFrame()
        self.preview_panel.setProperty("class", "card")
        self.preview_panel.setMinimumWidth(320)
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(16, 14, 16, 14)
        preview_layout.setSpacing(10)

        preview_header = QHBoxLayout()
        self.preview_title = QLabel("内容预览")
        self.preview_title.setProperty("class", "section")
        preview_header.addWidget(self.preview_title)
        preview_header.addStretch(1)
        self.preview_meta = QLabel("")
        self.preview_meta.setProperty("class", "hint")
        preview_header.addWidget(self.preview_meta)
        preview_layout.addLayout(preview_header)

        self.preview_stack = QStackedWidget()

        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("选中一条记录查看完整内容")
        self.preview_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.preview_stack.addWidget(self.preview_text)

        self.preview_image = QLabel("图片预览")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setMinimumHeight(240)
        self.preview_image.setStyleSheet(
            "background: #F8FAFC; border: 1px solid #E2E8F0; "
            "border-radius: 10px; color: #94A3B8;"
        )
        self.preview_stack.addWidget(self.preview_image)

        self.preview_files = QListWidget()
        self.preview_files.itemDoubleClicked.connect(
            lambda _item: self._open_preview_location()
        )
        self.preview_stack.addWidget(self.preview_files)

        self.preview_empty = QLabel("选中左边任意一条记录，这里会显示完整内容。")
        self.preview_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_empty.setWordWrap(True)
        self.preview_empty.setProperty("class", "hint")
        self.preview_stack.addWidget(self.preview_empty)
        self.preview_stack.setCurrentWidget(self.preview_empty)
        preview_layout.addWidget(self.preview_stack, 1)

        preview_buttons = QHBoxLayout()
        preview_buttons.setSpacing(8)
        self.preview_copy_btn = QPushButton("复制全文")
        self.preview_copy_btn.setProperty("class", "primary")
        self.preview_copy_btn.clicked.connect(self._copy_preview)
        self.preview_copy_btn.hide()
        preview_buttons.addWidget(self.preview_copy_btn)

        self.preview_open_btn = QPushButton("打开位置")
        self.preview_open_btn.setProperty("class", "ghost")
        self.preview_open_btn.clicked.connect(self._open_preview_location)
        self.preview_open_btn.hide()
        preview_buttons.addWidget(self.preview_open_btn)
        preview_buttons.addStretch(1)
        preview_layout.addLayout(preview_buttons)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.stack)
        self.splitter.addWidget(self.preview_panel)
        self.splitter.setSizes([580, 380])
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        root.addWidget(self.splitter, 1)

        footer = QHBoxLayout()
        self.status = QLabel("")
        self.status.setProperty("class", "hint")
        footer.addWidget(self.status, 1)

        clear_btn = QPushButton("清空全部")
        clear_btn.setProperty("class", "danger")
        clear_btn.clicked.connect(self._confirm_clear)
        footer.addWidget(clear_btn)
        root.addLayout(footer)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(220)
        self._search_timer.timeout.connect(self.refresh)

        sc_search = QShortcut(QKeySequence("Ctrl+F"), self)
        sc_search.activated.connect(self._focus_search)
        sc_esc = QShortcut(QKeySequence("Esc"), self)
        sc_esc.activated.connect(self.hide)
        sc_copy = QShortcut(QKeySequence("Return"), self)
        sc_copy.activated.connect(self._copy_selected)
        sc_delete = QShortcut(QKeySequence("Delete"), self)
        sc_delete.activated.connect(self._delete_selected)

    # ------------------------------------------------------------------ state
    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self.pause_banner.setVisible(paused)
        self._update_status()

    def notify_new_item(self) -> None:
        self._dirty = True
        if self.isVisible() and not self.search.text().strip():
            self.refresh()

    def show_window(self) -> None:
        log.info("show_window called, dirty=%s", self._dirty)
        if self._dirty:
            self.refresh()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self._focus_search()
        log.info("show_window done, visible=%s geometry=%s", self.isVisible(), self.geometry())

    def showEvent(self, event) -> None:  # noqa: N802
        log.info("HistoryWindow showEvent visible=%s", self.isVisible())
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        log.info("HistoryWindow hideEvent")
        super().hideEvent(event)

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    # ------------------------------------------------------------------ query
    def refresh(self) -> None:
        if self._search_timer.isActive():
            self._search_timer.stop()
        kind = self.filter.currentData() or "all"
        search = self.search.text().strip()
        self._offset = 0
        self._total = self.db.count_items(kind, search)
        self.list.blockSignals(True)
        self.list.clear()
        self._load_page()
        self.list.blockSignals(False)
        self._dirty = False
        self.stack.setCurrentIndex(0 if self._total > 0 else 1)
        self._update_status()
        if self._total > 0:
            self.list.setCurrentRow(0)
        else:
            self._clear_preview()

    def _load_page(self) -> None:
        kind = self.filter.currentData() or "all"
        search = self.search.text().strip()
        items = self.db.list_items(kind, search, PAGE_SIZE, self._offset)
        for item in items:
            self._append_item(item)
        self._offset += len(items)
        self._has_more = self._offset < self._total
        self._update_status()

    def _append_item(self, item: ClipboardItem) -> None:
        preview = item.preview or item.text or "(空)"
        li = QListWidgetItem()
        li.setData(ROLE_ID, item.id)
        li.setData(ROLE_KIND, item.kind)
        li.setData(ROLE_PREVIEW, preview)
        li.setData(ROLE_TIME, format_time(item.created_at))
        li.setData(ROLE_PINNED, item.pinned)
        li.setData(ROLE_TOOLTIP, item.text or preview)
        li.setIcon(kind_icon(item.kind))
        li.setToolTip((item.text or preview)[:600])
        li.setSizeHint(QSize(0, 76))
        self.list.addItem(li)

    def _update_status(self) -> None:
        text = f"共 {self._total} 条 · 永久保存在本机"
        if self._paused:
            text += " · 记录已暂停"
        self.status.setText(text)

    def show_toast(self, text: str) -> None:
        self.status.setText(text)
        QTimer.singleShot(1800, self._update_status)

    def _on_scroll(self, value: int) -> None:
        bar = self.list.verticalScrollBar()
        if self._has_more and value >= bar.maximum() - 60:
            self._load_page()

    def _on_search_changed(self) -> None:
        self._search_timer.start()

    def _on_filter_changed(self) -> None:
        self.refresh()

    # ----------------------------------------------------------------- actions
    def _selected_id(self) -> int | None:
        item = self.list.currentItem()
        if item is None:
            return None
        value = item.data(ROLE_ID)
        return int(value) if value is not None else None

    def _on_current_item_changed(self, current, previous) -> None:
        if current is None:
            self._clear_preview()
            return
        value = current.data(ROLE_ID)
        if value is not None:
            self._show_preview(int(value))

    def _clear_preview(self) -> None:
        self._preview_item_id = None
        self.preview_title.setText("内容预览")
        self.preview_meta.setText("")
        self.preview_stack.setCurrentWidget(self.preview_empty)
        self.preview_copy_btn.hide()
        self.preview_open_btn.hide()

    def _show_preview(self, item_id: int) -> None:
        item = self.db.get_item(item_id)
        if item is None:
            self._clear_preview()
            return
        self._preview_item_id = item_id
        self.preview_meta.setText(format_time(item.created_at))
        self.preview_copy_btn.show()
        self.preview_open_btn.hide()

        if item.kind == "text":
            self.preview_title.setText("文本全文")
            self.preview_meta.setText(f"{len(item.text)} 字 · {format_time(item.created_at)}")
            self.preview_text.setPlainText(item.text or "(空文本)")
            self.preview_stack.setCurrentWidget(self.preview_text)
            self.preview_copy_btn.setText("复制全文")
            cursor = self.preview_text.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self.preview_text.setTextCursor(cursor)

        elif item.kind == "image":
            self.preview_title.setText("图片预览")
            pixmap = QPixmap(item.image_path)
            if pixmap.isNull():
                self.preview_image.setPixmap(QPixmap())
                self.preview_image.setText("图片文件已不存在")
                self.preview_meta.setText(format_time(item.created_at))
            else:
                scaled = pixmap.scaled(
                    360,
                    360,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.preview_image.setPixmap(scaled)
                self.preview_image.setText("")
                self.preview_meta.setText(
                    f"{pixmap.width()}×{pixmap.height()} · {format_time(item.created_at)}"
                )
            self.preview_stack.setCurrentWidget(self.preview_image)
            self.preview_copy_btn.setText("复制图片")
            self.preview_open_btn.show()

        elif item.kind == "file":
            self.preview_title.setText("文件列表")
            self.preview_meta.setText(
                f"{len(item.file_paths)} 个文件 · {format_time(item.created_at)}"
            )
            self.preview_files.clear()
            for path in item.file_paths:
                li = QListWidgetItem(path)
                li.setToolTip(path)
                self.preview_files.addItem(li)
            self.preview_stack.setCurrentWidget(self.preview_files)
            self.preview_copy_btn.setText("复制文件路径")
            self.preview_open_btn.show()

    def _copy_preview(self) -> None:
        if self._preview_item_id is None:
            return
        self.copy_requested.emit(self._preview_item_id)
        self.show_toast("已复制到剪贴板")

    def _open_preview_location(self) -> None:
        if self._preview_item_id is not None:
            self._open_location(self._preview_item_id)

    def _on_double_click(self, item: QListWidgetItem) -> None:
        value = item.data(ROLE_ID)
        if value is not None:
            self.list.setCurrentItem(item)
            self._show_preview(int(value))
            self.copy_requested.emit(int(value))

    def _copy_selected(self) -> None:
        item_id = self._selected_id()
        if item_id is not None:
            self.copy_requested.emit(item_id)

    def _delete_selected(self) -> None:
        item_id = self._selected_id()
        if item_id is not None:
            self.delete_requested.emit(item_id)

    def _confirm_clear(self) -> None:
        if self._total == 0:
            return
        answer = QMessageBox.question(
            self,
            "清空剪贴板历史",
            "确定要删除全部剪贴板历史吗？\n此操作不可恢复，已保存的截图不受影响。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.clear_requested.emit()

    def _show_context_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        item_id = int(item.data(ROLE_ID))
        pinned = bool(item.data(ROLE_PINNED))
        kind = item.data(ROLE_KIND)

        menu = QMenu(self)
        act_view = menu.addAction("查看全文")
        act_copy = menu.addAction("复制")
        act_pin = menu.addAction("取消收藏" if pinned else "收藏")
        menu.addSeparator()
        act_open = None
        if kind in ("image", "file"):
            act_open = menu.addAction("打开文件位置")
        act_delete = menu.addAction("删除")

        chosen = menu.exec(self.list.mapToGlobal(pos))
        if chosen is act_view:
            self.list.setCurrentItem(item)
            self._show_preview(item_id)
        elif chosen is act_copy:
            self.copy_requested.emit(item_id)
        elif chosen is act_pin:
            self.pin_requested.emit(item_id, not pinned)
        elif act_open is not None and chosen is act_open:
            self._open_location(item_id)
        elif chosen is act_delete:
            self.delete_requested.emit(item_id)

    def _open_location(self, item_id: int) -> None:
        item = self.db.get_item(item_id)
        if item is None:
            return
        target = item.image_path or (item.file_paths[0] if item.file_paths else "")
        if not target:
            return
        path = Path(target)
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        elif path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def closeEvent(self, event) -> None:  # noqa: N802
        event.ignore()
        self.hide()
