from __future__ import annotations

import argparse
import ctypes
import dataclasses
import logging
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

from PySide6.QtCore import QMimeData, QObject, QThreadPool, QTimer, QUrl, Qt
from PySide6.QtGui import QAction, QDesktopServices, QFont, QGuiApplication, QImage, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from core import autostart
from core.clipboard_monitor import ClipboardMonitor, hash_for_files, hash_for_text
from core.config import Config
from core.db import HistoryDB
from core.hotkey import HotkeyManager
from core.ocr import OcrEngine, OcrWorker, preload_async
from core.paths import APP_NAME, APP_VERSION, app_data_dir, resource_path
from core.single_instance import SingleInstance
from core.utils import image_hash, setup_logging, unique_path
from ui.first_run import FirstRunDialog
from ui.history_window import HistoryWindow
from ui.icons import app_icon, tray_icon
from ui.overlay import CaptureOverlay, grab_virtual_desktop
from ui.result_window import ResultWindow
from ui.settings_dialog import SettingsDialog
from ui.theme import APP_STYLE

log = logging.getLogger(__name__)


class AppController(QObject):
    def __init__(self, app: QApplication, single: SingleInstance):
        super().__init__()
        self.app = app
        self.single = single
        self.config = Config.load()
        self.db = HistoryDB(app_data_dir() / "history.db")
        self.monitor = ClipboardMonitor(
            self.db, app_data_dir() / "clipboard_images", self
        )
        self.ocr = OcrEngine()
        self.hotkeys = HotkeyManager(self)
        self.result_window = ResultWindow()
        self.history_window = HistoryWindow(self.db)
        self._overlay: CaptureOverlay | None = None
        self._capture_pending = False
        self._ocr_seq = 0
        self._ocr_workers: dict[int, OcrWorker] = {}
        self._quitting = False

        self.tray = QSystemTrayIcon(tray_icon(), self)
        self._build_tray()
        self._connect_signals()

    # ------------------------------------------------------------------ setup
    def _build_tray(self) -> None:
        self.menu = QMenu()
        self.capture_action = QAction("截图识字", self)
        self.history_action = QAction("剪贴板历史", self)
        self.pause_action = QAction("暂停记录", self)
        self.pause_action.setCheckable(True)
        self.settings_action = QAction("设置…", self)
        self.autostart_action = QAction("开机自启", self)
        self.autostart_action.setCheckable(True)
        self.open_folder_action = QAction("打开截图文件夹", self)
        self.quit_action = QAction("退出", self)

        self.menu.addAction(self.capture_action)
        self.menu.addAction(self.history_action)
        self.menu.addSeparator()
        self.menu.addAction(self.pause_action)
        self.menu.addAction(self.autostart_action)
        self.menu.addAction(self.settings_action)
        self.menu.addAction(self.open_folder_action)
        self.menu.addSeparator()
        self.menu.addAction(self.quit_action)
        self.tray.setContextMenu(self.menu)

        self.capture_action.triggered.connect(self.start_capture)
        self.history_action.triggered.connect(self.show_history)
        self.pause_action.toggled.connect(self.set_paused)
        self.settings_action.triggered.connect(self.open_settings)
        self.autostart_action.toggled.connect(self.set_autostart)
        self.open_folder_action.triggered.connect(self.open_screenshot_dir)
        self.quit_action.triggered.connect(self.quit)
        self.tray.activated.connect(self._on_tray_activated)

    def _connect_signals(self) -> None:
        self.monitor.item_added.connect(self._on_item_added)
        self.monitor.error.connect(self._on_monitor_error)
        self.hotkeys.activated.connect(self._on_hotkey)
        self.single.message_received.connect(self._on_single_message)

        self.result_window.copy_text_requested.connect(self.copy_result_text)
        self.result_window.copy_image_requested.connect(self.copy_result_image)
        self.result_window.save_as_requested.connect(self.save_result_as)
        self.result_window.open_folder_requested.connect(self.open_result_folder)

        self.history_window.copy_requested.connect(self.copy_history_item)
        self.history_window.pin_requested.connect(self.pin_item)
        self.history_window.delete_requested.connect(self.delete_item)
        self.history_window.clear_requested.connect(self.clear_history)
        self.history_window.pause_toggle_requested.connect(self.toggle_pause)
        self.history_window.settings_requested.connect(self.open_settings)
        self.history_window.open_data_dir_requested.connect(self.open_data_dir)

    def start(self) -> None:
        self.monitor.start()
        self.history_window.set_paused(self.config.clipboard_paused)
        self._register_initial_hotkeys()
        self._update_tray()
        self.tray.show()
        autostart.sync(self.config.autostart)
        QTimer.singleShot(250, self._maybe_first_run)
        QTimer.singleShot(1200, lambda: preload_async(self.ocr))
        QTimer.singleShot(900, lambda: self._notify(
            "截图助手已启动",
            f"{self.config.hotkey_capture} 截图识字，"
            f"{self.config.hotkey_history} 打开剪贴板历史。",
        ))

    def _maybe_first_run(self) -> None:
        if self.config.first_run_done:
            return
        dialog = FirstRunDialog(self.config)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config.save()
        else:
            self.config.first_run_done = True
            self.config.save()
        autostart.sync(self.config.autostart)
        self._update_tray()

    def _register_initial_hotkeys(self) -> None:
        errors: list[str] = []
        ok, message = self.hotkeys.register("capture", self.config.hotkey_capture)
        if not ok:
            errors.append(message)
        ok, message = self.hotkeys.register("history", self.config.hotkey_history)
        if not ok:
            errors.append(message)
        if errors:
            QTimer.singleShot(
                1300,
                lambda: self._notify("热键注册失败", "\n".join(errors) + "\n可在托盘菜单 → 设置中更换。"),
            )

    def _update_tray(self) -> None:
        cfg = self.config
        self.capture_action.setText(f"截图识字\t{cfg.hotkey_capture}")
        self.history_action.setText(f"剪贴板历史\t{cfg.hotkey_history}")
        self.tray.setToolTip(
            f"截图助手\n{cfg.hotkey_capture} 截图识字\n{cfg.hotkey_history} 剪贴板历史"
        )
        for action, value in (
            (self.pause_action, cfg.clipboard_paused),
            (self.autostart_action, cfg.autostart),
        ):
            action.blockSignals(True)
            action.setChecked(value)
            action.blockSignals(False)

    def _notify(self, title: str, message: str) -> None:
        log.info("%s: %s", title, message)
        if self.tray.isVisible():
            self.tray.showMessage(
                title, message, QSystemTrayIcon.MessageIcon.Information, 4000
            )

    # ---------------------------------------------------------------- capture
    def _on_hotkey(self, name: str) -> None:
        if name == "capture":
            self.start_capture()
        elif name == "history":
            self.show_history()

    def start_capture(self) -> None:
        log.info("start_capture requested")
        if self._overlay is not None:
            self._overlay.raise_()
            self._overlay.activateWindow()
            return
        if self._capture_pending:
            return
        self._capture_pending = True
        self.result_window.hide()
        self.history_window.hide()
        QTimer.singleShot(90, self._create_overlay)

    def _create_overlay(self) -> None:
        self._capture_pending = False
        if self._overlay is not None:
            return
        overlay = CaptureOverlay()
        overlay.captured.connect(self._on_captured)
        overlay.canceled.connect(self._on_capture_canceled)
        overlay.failed.connect(self._on_capture_failed)
        self._overlay = overlay
        overlay.start()

    def _on_capture_canceled(self) -> None:
        log.info("截图已取消")
        self._overlay = None

    def _on_capture_failed(self, message: str) -> None:
        self._overlay = None
        self._notify("截图失败", message)

    def _on_captured(self, image: QImage) -> None:
        self._overlay = None
        path = self._save_screenshot(image)
        log.info("截图完成：%s×%s，保存到 %s", image.width(), image.height(), path)
        self.result_window.show_result(image, path)
        self._ocr_seq += 1
        seq = self._ocr_seq
        worker = OcrWorker(self.ocr, image, seq)
        worker.signals.finished.connect(self._on_ocr_done)
        worker.signals.failed.connect(self._on_ocr_failed)
        self._ocr_workers[seq] = worker
        QThreadPool.globalInstance().start(worker)

    def _save_screenshot(self, image: QImage) -> Path | None:
        folder = Path(self.config.screenshot_dir)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            target = unique_path(folder, "截图", ".png")
            if image.save(str(target), "PNG"):
                return target
            raise OSError("QImage.save 返回失败")
        except Exception:
            log.exception("保存截图失败: %s", folder)
            fallback = app_data_dir() / "screenshots"
            try:
                fallback.mkdir(parents=True, exist_ok=True)
                target = unique_path(fallback, "截图", ".png")
                if image.save(str(target), "PNG"):
                    self._notify("截图保存失败", f"无法写入 {folder}，已保存到 {fallback}")
                    return target
            except Exception:
                log.exception("备用目录保存截图也失败")
            self._notify("截图保存失败", "无法保存截图文件，仍可识别文字。")
            return None

    def _on_ocr_done(self, seq: int, text: str) -> None:
        self._ocr_workers.pop(seq, None)
        if seq != self._ocr_seq:
            return
        log.info("OCR 完成：%s 字，预览：%s", len(text), text[:80].replace("\n", " "))
        self.result_window.set_ocr_text(text)

    def _on_ocr_failed(self, seq: int, message: str) -> None:
        self._ocr_workers.pop(seq, None)
        if seq != self._ocr_seq:
            return
        self.result_window.set_error(message)

    def copy_result_text(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)
        log.info("已复制 OCR 文字（%s 字）", len(text))

    def copy_result_image(self, image: QImage) -> None:
        QGuiApplication.clipboard().setImage(image)

    def save_result_as(self) -> None:
        src = self.result_window.current_path()
        default = str(src) if src else str(Path(self.config.screenshot_dir) / "截图.png")
        filename, _ = QFileDialog.getSaveFileName(
            self.result_window,
            "另存截图",
            default,
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg)",
        )
        if not filename:
            return
        target = Path(filename)
        if not target.suffix:
            target = target.with_suffix(".png")
        try:
            if src is not None and src.exists():
                shutil.copy2(src, target)
            else:
                image = self.result_window.current_image()
                if not image.save(str(target)):
                    raise OSError("保存失败")
            self.result_window.set_saved_path(target)
            self.result_window.status.setText(f"已另存为：{target}")
        except Exception as exc:
            QMessageBox.warning(self.result_window, "另存为失败", str(exc))

    def open_result_folder(self) -> None:
        path = self.result_window.current_path()
        folder = path.parent if path is not None else Path(self.config.screenshot_dir)
        if folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # --------------------------------------------------------------- history
    def show_history(self) -> None:
        log.info("show_history requested")
        self.result_window.hide()
        self.history_window.set_paused(self.config.clipboard_paused)
        self.history_window.show_window()

    def _on_item_added(self, item_id: int) -> None:
        self.history_window.notify_new_item()

    def _on_monitor_error(self, message: str) -> None:
        self._notify("剪贴板记录异常", message)

    def copy_history_item(self, item_id: int) -> None:
        item = self.db.get_item(item_id)
        if item is None:
            return
        clipboard = QGuiApplication.clipboard()
        try:
            if item.kind == "text":
                self.monitor.suppress(item.content_hash or hash_for_text(item.text), 3.0)
                clipboard.setText(item.text)
            elif item.kind == "image":
                image = QImage(item.image_path)
                if image.isNull():
                    self._notify("复制失败", "图片文件已不存在")
                    return
                self.monitor.suppress(item.content_hash or image_hash(image), 5.0)
                clipboard.setImage(image)
            elif item.kind == "file":
                paths = item.file_paths
                if not paths:
                    return
                self.monitor.suppress(item.content_hash or hash_for_files(paths), 4.0)
                mime = QMimeData()
                mime.setUrls([QUrl.fromLocalFile(path) for path in paths])
                clipboard.setMimeData(mime)
        except Exception as exc:
            log.exception("从历史复制失败")
            self._notify("复制失败", str(exc))
            return
        self.history_window.show_toast("已复制到剪贴板")

    def pin_item(self, item_id: int, pinned: bool) -> None:
        self.db.set_pinned(item_id, pinned)
        self.history_window.refresh()

    def delete_item(self, item_id: int) -> None:
        image_path = self.db.delete_item(item_id)
        if image_path:
            self._cleanup_image(image_path)
        self.history_window.refresh()

    def clear_history(self) -> None:
        images = self.db.clear_all()
        for image_path in images:
            self._cleanup_image(image_path)
        self.history_window.refresh()

    def _cleanup_image(self, image_path: str) -> None:
        try:
            path = Path(image_path).resolve()
            root = (app_data_dir() / "clipboard_images").resolve()
            if path.is_relative_to(root):
                path.unlink(missing_ok=True)
        except Exception:
            log.exception("清理剪贴板图片失败: %s", image_path)

    def toggle_pause(self) -> None:
        self.set_paused(not self.config.clipboard_paused)

    def set_paused(self, paused: bool) -> None:
        self.config.clipboard_paused = bool(paused)
        self.config.save()
        self.monitor.paused = bool(paused)
        self.history_window.set_paused(bool(paused))
        self.pause_action.blockSignals(True)
        self.pause_action.setChecked(bool(paused))
        self.pause_action.blockSignals(False)

    def set_autostart(self, enabled: bool) -> None:
        if bool(enabled) == self.config.autostart:
            return
        if not autostart.set_enabled(bool(enabled)):
            self._notify("开机自启", "写入注册表失败，请检查权限。")
            self._update_tray()
            return
        self.config.autostart = bool(enabled)
        self.config.save()
        self._update_tray()

    def open_settings(self) -> None:
        log.info("open_settings requested")
        dialog = SettingsDialog(
            self.config,
            self.apply_settings,
            self.clear_history,
            self.open_data_dir,
            self.history_window,
        )
        dialog.exec()

    def apply_settings(self, new_config: Config) -> tuple[bool, str]:
        old = dataclasses.replace(self.config)
        self.hotkeys.unregister_all()
        ok, message = self.hotkeys.register("capture", new_config.hotkey_capture)
        if not ok:
            self._restore_hotkeys(old)
            return False, message
        ok, message = self.hotkeys.register("history", new_config.hotkey_history)
        if not ok:
            self.hotkeys.unregister_all()
            self._restore_hotkeys(old)
            return False, message

        try:
            Path(new_config.screenshot_dir).mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self.hotkeys.unregister_all()
            self._restore_hotkeys(old)
            return False, f"截图文件夹不可用：{exc}"

        self.config = new_config
        self.config.save()
        self.monitor.paused = new_config.clipboard_paused
        self.history_window.set_paused(new_config.clipboard_paused)
        if not autostart.set_enabled(new_config.autostart):
            self._notify("开机自启", "写入注册表失败，请检查权限。")
        self._update_tray()
        return True, ""

    def _restore_hotkeys(self, config: Config) -> None:
        ok, msg = self.hotkeys.register("capture", config.hotkey_capture)
        if not ok:
            log.error("恢复截图热键失败: %s", msg)
        ok, msg = self.hotkeys.register("history", config.hotkey_history)
        if not ok:
            log.error("恢复剪贴板热键失败: %s", msg)

    def open_data_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(app_data_dir())))

    def open_screenshot_dir(self) -> None:
        folder = Path(self.config.screenshot_dir)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        except Exception as exc:
            self._notify("打开文件夹失败", str(exc))

    def _on_single_message(self, command: str) -> None:
        if command == "capture":
            self.start_capture()
        elif command == "history":
            self.show_history()
        elif command == "quit":
            self.quit()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_history()

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        try:
            self.hotkeys.unregister_all()
            self.monitor.stop()
            self.tray.hide()
            self.result_window.hide()
            self.history_window.hide()
            if self.single.server is not None:
                self.single.server.close()
            self.db.close()
        finally:
            self.app.quit()


def run_selftest(app: QApplication) -> int:
    image, virtual, dpr = grab_virtual_desktop()
    log.info(
        "自检：screen=%sx%s dpr=%s image=%sx%s",
        virtual.width(), virtual.height(), dpr, image.width(), image.height(),
    )
    target = Path(tempfile.gettempdir()) / "截图助手_selftest.png"
    image.save(str(target), "PNG")
    log.info("自检截图已保存：%s", target)
    engine = OcrEngine()
    text = engine.recognize(image)
    log.info("自检 OCR 结果（%s 字）：%s", len(text), text[:200].replace("\n", " | "))
    return 0


def install_excepthook() -> None:
    def hook(exc_type, exc, tb):
        log.error("未捕获异常", exc_info=(exc_type, exc, tb))
        try:
            QMessageBox.critical(
                None,
                "截图助手出错",
                f"{exc_type.__name__}: {exc}\n\n详情已写入日志：{app_data_dir() / 'logs'}",
            )
        except Exception:
            pass

    sys.excepthook = hook


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--selftest", action="store_true", help="截屏并 OCR 自检")
    parser.add_argument("--capture", action="store_true", help="启动后立即进入截图")
    parser.add_argument("--history", action="store_true", help="启动后打开剪贴板历史")
    return parser.parse_args()


def main() -> int:
    setup_logging()
    try:
        if sys.stdout is not None:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    args = parse_args()
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("Local")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(APP_STYLE)
    app.setWindowIcon(app_icon())
    install_excepthook()

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("JieTuZhuShou")
    except Exception:
        pass

    if args.selftest:
        return run_selftest(app)

    second_command = "history" if args.history else "capture"
    single = SingleInstance()
    if single.notify_existing(second_command):
        return 0
    if not single.listen():
        if single.notify_existing(second_command):
            return 0
        QMessageBox.critical(None, "截图助手", "无法启动单实例服务，请检查系统权限。")
        return 1

    controller = AppController(app, single)
    controller.start()

    if args.capture:
        QTimer.singleShot(700, controller.start_capture)
    if args.history:
        QTimer.singleShot(400, controller.show_history)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
