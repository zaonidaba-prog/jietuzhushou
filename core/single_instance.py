from __future__ import annotations

import getpass
import hashlib
import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)


class SingleInstance(QObject):
    message_received = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        user = getpass.getuser()
        digest = hashlib.md5(user.encode("utf-8", errors="replace")).hexdigest()[:8]
        self.key = f"JieTuZhuShou-{digest}"
        self.server: QLocalServer | None = None

    def notify_existing(self, command: str = "capture") -> bool:
        sock = QLocalSocket()
        sock.connectToServer(self.key)
        if not sock.waitForConnected(350):
            return False
        sock.write(command.encode("utf-8"))
        sock.flush()
        sock.waitForBytesWritten(350)
        sock.disconnectFromServer()
        return True

    def listen(self) -> bool:
        QLocalServer.removeServer(self.key)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._on_new_connection)
        if not self.server.listen(self.key):
            log.error("单实例服务启动失败: %s", self.server.errorString())
            return False
        return True

    def _on_new_connection(self) -> None:
        if not self.server:
            return
        while self.server.hasPendingConnections():
            conn = self.server.nextPendingConnection()
            if conn is None:
                continue
            conn.waitForReadyRead(200)
            data = bytes(conn.readAll()).decode("utf-8", errors="replace").strip()
            conn.disconnectFromServer()
            if data:
                self.message_received.emit(data)
