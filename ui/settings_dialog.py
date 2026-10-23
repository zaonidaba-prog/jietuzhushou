from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.config import Config
from core.hotkey import parse_hotkey
from core.paths import APP_VERSION, app_data_dir
from .icons import app_icon

log = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    def __init__(
        self,
        config: Config,
        apply_callback,
        clear_callback,
        open_data_callback,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        log.info("SettingsDialog constructed")
        self.config = config
        self.apply_callback = apply_callback
        self.clear_callback = clear_callback
        self.open_data_callback = open_data_callback

        self.setWindowTitle("设置 - 截图助手")
        self.setWindowIcon(app_icon())
        self.setModal(True)
        self.resize(640, 610)

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(16)

        title = QLabel("设置")
        title.setProperty("class", "title")
        root.addWidget(title)
        subtitle = QLabel("所有数据都保存在本机，不会上传到任何服务器。")
        subtitle.setProperty("class", "subtitle")
        root.addWidget(subtitle)

        card = QFrame()
        card.setProperty("class", "card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        folder_row = QWidget()
        folder_layout = QHBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(8)
        self.folder_edit = QLineEdit(config.screenshot_dir)
        self.folder_edit.setPlaceholderText("截图保存文件夹")
        folder_layout.addWidget(self.folder_edit, 1)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_folder)
        folder_layout.addWidget(browse)
        form.addRow("截图保存到", folder_row)

        self.capture_key = QKeySequenceEdit(QKeySequence(config.hotkey_capture))
        self.capture_key.setClearButtonEnabled(True)
        form.addRow("截图热键", self.capture_key)

        self.history_key = QKeySequenceEdit(QKeySequence(config.hotkey_history))
        self.history_key.setClearButtonEnabled(True)
        form.addRow("剪贴板热键", self.history_key)

        toggle_box = QWidget()
        toggle_layout = QVBoxLayout(toggle_box)
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        toggle_layout.setSpacing(8)
        self.autostart_check = QCheckBox("开机自动启动（推荐，否则关机后会漏记复制内容）")
        self.autostart_check.setChecked(config.autostart)
        toggle_layout.addWidget(self.autostart_check)
        self.pause_check = QCheckBox("暂停记录剪贴板（暂停期间仍可查看和复制历史）")
        self.pause_check.setChecked(config.clipboard_paused)
        toggle_layout.addWidget(self.pause_check)

        self.legacy_capture_check = QCheckBox(
            "使用旧版截图流程（松开鼠标立即保存，不显示 ✓ / ✕）"
        )
        self.legacy_capture_check.setChecked(config.legacy_capture)
        toggle_layout.addWidget(self.legacy_capture_check)
        form.addRow("", toggle_box)

        card_layout.addLayout(form)
        root.addWidget(card)

        data_card = QFrame()
        data_card.setProperty("class", "card")
        data_layout = QVBoxLayout(data_card)
        data_layout.setContentsMargins(20, 16, 20, 16)
        data_layout.setSpacing(10)
        data_title = QLabel("数据与存储")
        data_title.setProperty("class", "section")
        data_layout.addWidget(data_title)

        path_row = QHBoxLayout()
        path_label = QLabel(f"数据目录：{app_data_dir()}")
        path_label.setProperty("class", "hint")
        path_label.setWordWrap(True)
        path_row.addWidget(path_label, 1)
        open_data = QPushButton("打开")
        open_data.clicked.connect(self.open_data_callback)
        path_row.addWidget(open_data)
        data_layout.addLayout(path_row)

        danger_row = QHBoxLayout()
        danger_hint = QLabel("清空剪贴板历史不会删除已保存的截图文件。")
        danger_hint.setProperty("class", "hint")
        danger_row.addWidget(danger_hint, 1)
        clear_btn = QPushButton("清空剪贴板历史")
        clear_btn.setProperty("class", "danger")
        clear_btn.clicked.connect(self._confirm_clear)
        danger_row.addWidget(clear_btn)
        data_layout.addLayout(danger_row)
        root.addWidget(data_card)

        root.addStretch(1)

        footer = QHBoxLayout()
        version = QLabel(f"截图助手 v{APP_VERSION}")
        version.setProperty("class", "hint")
        footer.addWidget(version)
        footer.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        save = QPushButton("保存")
        save.setProperty("class", "primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        footer.addWidget(save)
        root.addLayout(footer)

    def _browse_folder(self) -> None:
        start = self.folder_edit.text().strip() or str(Path.home() / "Pictures")
        folder = QFileDialog.getExistingDirectory(self, "选择截图保存文件夹", start)
        if folder:
            self.folder_edit.setText(folder)

    def _confirm_clear(self) -> None:
        answer = QMessageBox.question(
            self,
            "清空剪贴板历史",
            "确定要删除全部剪贴板历史吗？\n此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.clear_callback()

    def _save(self) -> None:
        folder = self.folder_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, "设置", "请选择截图保存文件夹。")
            return
        try:
            Path(folder).mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            QMessageBox.warning(self, "设置", f"无法创建文件夹：\n{exc}")
            return

        capture = self.capture_key.keySequence().toString(QKeySequence.SequenceFormat.NativeText).strip()
        history = self.history_key.keySequence().toString(QKeySequence.SequenceFormat.NativeText).strip()
        if not capture or not history:
            QMessageBox.warning(self, "设置", "截图和剪贴板都需要设置热键。")
            return
        if capture.lower() == history.lower():
            QMessageBox.warning(self, "设置", "两个热键不能相同。")
            return
        for label, value in (("截图热键", capture), ("剪贴板热键", history)):
            try:
                parse_hotkey(value)
            except ValueError as exc:
                QMessageBox.warning(self, "设置", f"{label}无效：{exc}")
                return

        new_config = dataclasses.replace(
            self.config,
            screenshot_dir=folder,
            hotkey_capture=capture,
            hotkey_history=history,
            autostart=self.autostart_check.isChecked(),
            clipboard_paused=self.pause_check.isChecked(),
            legacy_capture=self.legacy_capture_check.isChecked(),
        )
        ok, message = self.apply_callback(new_config)
        if not ok:
            QMessageBox.warning(self, "设置", message)
            return
        self.accept()
