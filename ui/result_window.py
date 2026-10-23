from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .icons import app_icon


class ResultWindow(QWidget):
    copy_text_requested = Signal(str)
    copy_image_requested = Signal(QImage)
    save_as_requested = Signal()
    open_folder_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("识别结果 - 截图助手")
        self.setWindowIcon(app_icon())
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(660, 540)
        self.setMinimumSize(520, 400)

        self._image = QImage()
        self._path: Path | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)
        icon_label = QLabel()
        icon_label.setPixmap(app_icon().pixmap(28, 28))
        header.addWidget(icon_label)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title = QLabel("识别结果")
        title.setProperty("class", "title")
        self.subtitle = QLabel("正在识别文字…")
        self.subtitle.setProperty("class", "subtitle")
        title_box.addWidget(title)
        title_box.addWidget(self.subtitle)
        header.addLayout(title_box, 1)

        close_btn = QPushButton("×")
        close_btn.setProperty("class", "ghost")
        close_btn.setFixedSize(34, 34)
        close_btn.setToolTip("关闭")
        close_btn.clicked.connect(self.hide)
        header.addWidget(close_btn)
        root.addLayout(header)

        self.path_label = QLabel("")
        self.path_label.setProperty("class", "hint")
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.path_label)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("正在识别文字，请稍候…")
        self.editor.setReadOnly(True)
        self.editor.setMinimumHeight(260)
        root.addWidget(self.editor, 1)

        self.status = QLabel("")
        self.status.setProperty("class", "hint")
        root.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.copy_text_btn = QPushButton("复制文字")
        self.copy_text_btn.setProperty("class", "primary")
        self.copy_text_btn.setDefault(True)
        self.copy_text_btn.clicked.connect(self._copy_text)
        buttons.addWidget(self.copy_text_btn)

        self.copy_image_btn = QPushButton("复制图片")
        self.copy_image_btn.clicked.connect(self._copy_image)
        buttons.addWidget(self.copy_image_btn)

        self.save_as_btn = QPushButton("另存为…")
        self.save_as_btn.clicked.connect(self.save_as_requested.emit)
        buttons.addWidget(self.save_as_btn)

        self.open_folder_btn = QPushButton("打开文件夹")
        self.open_folder_btn.clicked.connect(self.open_folder_requested.emit)
        buttons.addWidget(self.open_folder_btn)

        buttons.addStretch(1)
        close2 = QPushButton("关闭")
        close2.clicked.connect(self.hide)
        buttons.addWidget(close2)
        root.addLayout(buttons)

        esc = QShortcut(QKeySequence("Esc"), self)
        esc.activated.connect(self.hide)
        copy_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        copy_shortcut.activated.connect(self._copy_text)

    def show_result(self, image: QImage, path: Path | None) -> None:
        self._image = image.copy()
        self._path = path
        self.editor.setPlainText("")
        self.editor.setReadOnly(True)
        self.editor.setPlaceholderText("正在识别文字，请稍候…")
        self.subtitle.setText("正在识别文字…")
        if path is not None:
            self.path_label.setText(f"已保存：{path}")
        else:
            self.path_label.setText("未能保存到磁盘，可点「另存为」选择位置。")
        self.status.setText("")
        self.copy_text_btn.setEnabled(False)
        self.copy_image_btn.setEnabled(True)
        self.show()
        self.raise_()
        self.activateWindow()
        self._center_on_cursor_screen()
        QTimer.singleShot(60, self.editor.setFocus)

    def set_ocr_text(self, text: str) -> None:
        self.editor.setReadOnly(False)
        if text:
            self.editor.setPlainText(text)
            self.subtitle.setText("识别完成，可直接修改后复制")
            self.status.setText("文字已就绪。点「复制文字」后才会写入剪贴板和历史。")
            self.copy_text_btn.setEnabled(True)
            self.editor.setFocus()
            cursor = self.editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self.editor.setTextCursor(cursor)
        else:
            self.editor.setPlainText("")
            self.editor.setPlaceholderText("未识别到文字。可以尝试放大截图区域后重新截取。")
            self.subtitle.setText("未识别到文字")
            self.status.setText("图片已保存，可点「复制图片」或「另存为」。")
            self.copy_text_btn.setEnabled(False)

    def set_error(self, message: str) -> None:
        self.editor.setReadOnly(False)
        self.subtitle.setText("识别失败")
        self.status.setText(f"识别失败：{message}")
        self.copy_text_btn.setEnabled(False)

    def current_path(self) -> Path | None:
        return self._path

    def current_image(self) -> QImage:
        return self._image

    def set_saved_path(self, path: Path) -> None:
        self._path = path
        self.path_label.setText(f"已保存：{path}")

    def _copy_text(self) -> None:
        text = self.editor.toPlainText().strip()
        if not text:
            self.status.setText("没有可复制的文字")
            return
        self.copy_text_requested.emit(text)
        self.status.setText("已复制到剪贴板，并会进入剪贴板历史。")

    def _copy_image(self) -> None:
        if self._image.isNull():
            self.status.setText("没有可复制的图片")
            return
        self.copy_image_requested.emit(self._image)
        self.status.setText("图片已复制到剪贴板。")

    def _center_on_cursor_screen(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(
            geo.x() + (geo.width() - self.width()) // 2,
            geo.y() + (geo.height() - self.height()) // 2,
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        event.ignore()
        self.hide()
