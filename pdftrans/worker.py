"""后台翻译 worker：独立线程跑 HTTP，流式增量回到 UI。"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, Signal, Slot

from .cache import TranslationCache, cache_key
from .engines import Engine, TranslateError


class TranslateWorker(QObject):
    delta = Signal(str)          # 增量文本
    finished = Signal(str, bool)  # 完整译文, 是否来自缓存
    failed = Signal(str)

    def __init__(
        self,
        engine: Engine,
        text: str,
        src: str,
        dst: str,
        cache: TranslationCache | None = None,
    ):
        super().__init__()
        self.engine = engine
        self.text = text
        self.src = src
        self.dst = dst
        self.cache = cache
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    @Slot()
    def run(self) -> None:
        try:
            key = cache_key(self.engine.id, self.src, self.dst, self.text)
            if self.cache is not None:
                hit = self.cache.get(key)
                if hit:
                    self.delta.emit(hit)
                    self.finished.emit(hit, True)
                    return

            parts: list[str] = []
            if self.engine.supports_stream:
                for piece in self.engine.stream(self.text, self.src, self.dst):
                    if self._cancel.is_set():
                        return
                    if piece:
                        parts.append(piece)
                        self.delta.emit(piece)
            else:
                result = self.engine.translate(self.text, self.src, self.dst)
                if self._cancel.is_set():
                    return
                if result:
                    parts.append(result)
                    self.delta.emit(result)

            text = "".join(parts).strip()
            if not text:
                self.failed.emit("没有拿到译文（原文为空，或该区域是扫描图）")
                return
            if self.cache is not None:
                self.cache.put(key, self.engine.id, text)
            self.finished.emit(text, False)

        except TranslateError as e:
            if not self._cancel.is_set():
                self.failed.emit(str(e))
        except Exception as e:  # 兜底，别让线程静默死掉
            if not self._cancel.is_set():
                self.failed.emit(f"{type(e).__name__}: {e}")
        finally:
            try:
                self.engine.close()
            except Exception:
                pass


class TranslateTask(QThread):
    """把 worker 装进 QThread 子类，生命周期由主窗口持有。"""

    delta = Signal(str)
    done = Signal(str, bool)
    error = Signal(str)

    def __init__(self, engine, text, src, dst, cache=None, parent=None):
        super().__init__(parent)
        self._worker = TranslateWorker(engine, text, src, dst, cache)
        self._worker.delta.connect(self.delta)
        self._worker.finished.connect(self.done)
        self._worker.failed.connect(self.error)

    def run(self) -> None:  # noqa: D102
        self._worker.run()

    def cancel(self) -> None:
        self._worker.cancel()
