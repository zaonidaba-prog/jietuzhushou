from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtWidgets import QApplication, QWidget

log = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_user32 = ctypes.windll.user32

_KEY_NAMES = {
    "PRINTSCREEN": 0x2C,
    "PRTSC": 0x2C,
    "INSERT": 0x2D,
    "INS": 0x2D,
    "DELETE": 0x2E,
    "DEL": 0x2E,
    "HOME": 0x24,
    "END": 0x23,
    "PAGEUP": 0x21,
    "PGUP": 0x21,
    "PAGEDOWN": 0x22,
    "PGDN": 0x22,
    "SPACE": 0x20,
    "TAB": 0x09,
}


def parse_hotkey(text: str) -> tuple[int, int]:
    """Return (modifiers, virtual-key code). Raises ValueError when invalid."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("热键不能为空")

    parts = [p.strip() for p in raw.replace("＋", "+").split("+") if p.strip()]
    if not parts:
        raise ValueError("热键格式不正确")

    key = parts[-1].upper()
    mods = 0
    for part in parts[:-1]:
        p = part.upper()
        if p == "ALT":
            mods |= MOD_ALT
        elif p in ("CTRL", "CONTROL"):
            mods |= MOD_CONTROL
        elif p == "SHIFT":
            mods |= MOD_SHIFT
        elif p in ("WIN", "WINDOWS", "META"):
            mods |= MOD_WIN
        else:
            raise ValueError(f"无法识别的修饰键：{part}")

    if len(key) == 1 and ("A" <= key <= "Z" or "0" <= key <= "9"):
        vk = ord(key)
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    elif key in _KEY_NAMES:
        vk = _KEY_NAMES[key]
    else:
        raise ValueError(f"无法识别的按键：{parts[-1]}")

    if mods == 0 and not (key.startswith("F") and key[1:].isdigit()):
        raise ValueError("请使用 Alt / Ctrl / Shift / Win 组合，避免占用普通按键")

    return mods, vk


class _NativeFilter(QAbstractNativeEventFilter):
    def __init__(self, manager: "HotkeyManager"):
        super().__init__()
        self.manager = manager

    @staticmethod
    def _event_name(eventType) -> str:
        # PySide6 passes a QByteArray here, while some builds pass bytes/str.
        try:
            data = eventType.data()
            if isinstance(data, (bytes, bytearray)):
                return bytes(data).decode("ascii", errors="ignore")
        except Exception:
            pass
        if isinstance(eventType, (bytes, bytearray)):
            return bytes(eventType).decode("ascii", errors="ignore")
        return str(eventType)

    def nativeEventFilter(self, eventType, message):  # noqa: N802
        try:
            et = self._event_name(eventType)
            if et in ("windows_generic_MSG", "windows_dispatcher_MSG"):
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    self.manager._dispatch(int(msg.wParam))
        except Exception:
            log.exception("处理全局热键消息失败")
        return False, 0


class HotkeyManager(QObject):
    activated = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._widget = QWidget()
        self._widget.setObjectName("hotkeyHost")
        self._widget.resize(1, 1)
        self._widget.setWindowTitle("截图助手")
        self._hwnd = int(self._widget.winId())
        self._ids: dict[str, int] = {}
        self._next_id = 0x4A00
        self._last_dispatch: dict[int, float] = {}
        self._filter = _NativeFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._filter)

    def _dispatch(self, hotkey_id: int) -> None:
        now = time.monotonic()
        if now - self._last_dispatch.get(hotkey_id, 0.0) < 0.35:
            return
        self._last_dispatch[hotkey_id] = now
        for name, hid in self._ids.items():
            if hid == hotkey_id:
                self.activated.emit(name)
                return

    def register(self, name: str, hotkey: str) -> tuple[bool, str]:
        try:
            mods, vk = parse_hotkey(hotkey)
        except ValueError as exc:
            return False, str(exc)

        if name in self._ids:
            self.unregister(name)

        hotkey_id = self._next_id
        self._next_id += 1
        ok = _user32.RegisterHotKey(self._hwnd, hotkey_id, mods | MOD_NOREPEAT, vk)
        if not ok:
            return False, f"热键 {hotkey} 注册失败，可能已被其他程序占用"

        self._ids[name] = hotkey_id
        log.info("注册热键 %s -> %s", name, hotkey)
        return True, ""

    def unregister(self, name: str) -> None:
        hotkey_id = self._ids.pop(name, None)
        if hotkey_id is not None:
            _user32.UnregisterHotKey(self._hwnd, hotkey_id)

    def unregister_all(self) -> None:
        for name in list(self._ids):
            self.unregister(name)
