from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.config import Config
from core.paths import default_screenshot_dir
from .icons import app_icon


class FirstRunDialog(QDialog):
    def __init__(self, config: Config, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("欢迎使用截图助手")
        self.setWindowIcon(app_icon())
        self.setModal(True)
        self.resize(600, 470)

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 22)
        root.setSpacing(16)

        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(54, 54))
        header.addWidget(logo)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("欢迎使用截图助手")
        title.setProperty("class", "title")
        subtitle = QLabel("截图识字 + 本地剪贴板历史，全部离线运行")
        subtitle.setProperty("class", "subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        root.addLayout(header)

        intro = QLabel(
            "按 Alt+Q 呼出截图：拖拽截局部，回车截整屏，识别出的文字可编辑后复制。\n"
            "按 Alt+V 打开剪贴板历史：复制过的文字、图片、文件都会永久保存在本机，可搜索、可再次复制。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #475569; line-height: 160%;")
        root.addWidget(intro)

        card = QFrame()
        card.setProperty("class", "card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(12)

        label = QLabel("截图保存文件夹")
        label.setProperty("class", "section")
        card_layout.addWidget(label)

        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit(config.screenshot_dir or str(default_screenshot_dir()))
        folder_row.addWidget(self.folder_edit, 1)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse)
        folder_row.addWidget(browse)
        card_layout.addLayout(folder_row)

        hint = QLabel("之后可以在托盘菜单 → 设置里随时修改。")
        hint.setProperty("class", "hint")
        card_layout.addWidget(hint)

        self.autostart_check = QCheckBox("开机自动启动（推荐，确保关机后也不会漏记复制内容）")
        self.autostart_check.setChecked(True)
        card_layout.addWidget(self.autostart_check)
        root.addWidget(card)

        root.addStretch(1)

        footer = QHBoxLayout()
        tip = QLabel("所有数据只保存在本机，不联网、不上传。")
        tip.setProperty("class", "hint")
        footer.addWidget(tip, 1)
        start = QPushButton("开始使用")
        start.setProperty("class", "primary")
        start.setDefault(True)
        start.clicked.connect(self._start)
        footer.addWidget(start)
        root.addLayout(footer)

    def _browse(self) -> None:
        start = self.folder_edit.text().strip() or str(default_screenshot_dir())
        folder = QFileDialog.getExistingDirectory(self, "选择截图保存文件夹", start)
        if folder:
            self.folder_edit.setText(folder)

    def _start(self) -> None:
        folder = self.folder_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, "截图助手", "请选择截图保存文件夹。")
            return
        try:
            Path(folder).mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            QMessageBox.warning(self, "截图助手", f"无法创建文件夹：\n{exc}")
            return
        self.config.screenshot_dir = folder
        self.config.autostart = self.autostart_check.isChecked()
        self.config.first_run_done = True
        self.accept()
