from __future__ import annotations

import logging
import threading

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage

log = logging.getLogger(__name__)


def qimage_to_bgr(image: QImage) -> np.ndarray:
    img = image.convertToFormat(QImage.Format.Format_RGB888)
    w, h = img.width(), img.height()
    bpl = img.bytesPerLine()
    raw = img.constBits().tobytes()
    arr = np.frombuffer(raw, dtype=np.uint8).reshape((h, bpl))
    arr = arr[:, : w * 3].reshape((h, w, 3))
    return np.ascontiguousarray(arr[:, :, ::-1])


class OcrEngine:
    def __init__(self) -> None:
        self._engine = None
        self._lock = threading.Lock()
        self._init_lock = threading.Lock()

    def _ensure(self):
        if self._engine is not None:
            return self._engine
        with self._init_lock:
            if self._engine is None:
                from rapidocr_onnxruntime import RapidOCR

                log.info("正在加载 RapidOCR 模型…")
                self._engine = RapidOCR()
                log.info("RapidOCR 模型加载完成")
        return self._engine

    def preload(self) -> None:
        try:
            self._ensure()
        except Exception:
            log.exception("OCR 模型预加载失败")

    def recognize(self, image: QImage) -> str:
        if image.isNull():
            return ""

        work = image
        # Small selections benefit a lot from upscaling.
        longest = max(image.width(), image.height())
        if 0 < longest < 1400:
            from PySide6.QtCore import Qt

            factor = min(2.0, max(1.4, 1400 / longest))
            work = image.scaled(
                int(image.width() * factor),
                int(image.height() * factor),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        bgr = qimage_to_bgr(work)
        engine = self._ensure()
        with self._lock:
            result, _ = engine(bgr)

        if not result:
            return ""

        lines: list[tuple[float, float, str]] = []
        for item in result:
            try:
                box, text, score = item[0], item[1], float(item[2])
            except Exception:
                continue
            if not text or not str(text).strip():
                continue
            if score < 0.3:
                continue
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
            lines.append((min(ys), min(xs), str(text).strip()))

        lines.sort(key=lambda x: (round(x[0] / 8), x[1]))
        return "\n".join(x[2] for x in lines)


class OcrSignals(QObject):
    finished = Signal(int, str)
    failed = Signal(int, str)


class OcrWorker(QRunnable):
    def __init__(self, engine: OcrEngine, image: QImage, seq: int = 0):
        super().__init__()
        self.engine = engine
        self.image = image.copy()
        self.seq = seq
        self.signals = OcrSignals()

    def run(self) -> None:
        try:
            text = self.engine.recognize(self.image)
            self.signals.finished.emit(self.seq, text)
        except Exception as exc:
            log.exception("OCR 识别失败")
            self.signals.failed.emit(self.seq, str(exc))


class OcrPreloader(QRunnable):
    def __init__(self, engine: OcrEngine):
        super().__init__()
        self.engine = engine

    def run(self) -> None:
        self.engine.preload()


def preload_async(engine: OcrEngine) -> None:
    QThreadPool.globalInstance().start(OcrPreloader(engine))
