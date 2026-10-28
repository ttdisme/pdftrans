"""右侧翻译面板：原文 / 流式译文 / 状态。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..engines import lang_human
from .styles import THEMES


class TranslatePanel(QWidget):
    channelChanged = Signal(str)
    retranslateRequested = Signal(str)
    pageRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "day"
        self._busy = False
        self._buffer = ""

        # ---- 顶部：通道切换
        self.channel = QComboBox()
        self.channel.setMinimumWidth(180)
        self.channel.currentIndexChanged.connect(self._on_channel_changed)

        self.lang_label = QLabel("自动识别 → 中文")
        self.lang_label.setObjectName("dim")

        top = QHBoxLayout()
        top.setContentsMargins(10, 8, 10, 2)
        top.setSpacing(8)
        top.addWidget(QLabel("通道"))
        top.addWidget(self.channel)
        top.addWidget(self.lang_label)
        top.addStretch(1)

        # ---- 原文
        self.src_title = QLabel("原文")
        self.src_title.setObjectName("dim")
        self.src = QPlainTextEdit()
        self.src.setPlaceholderText("在左侧 PDF 上划选文字，这里会显示原文")
        self.src.setMinimumHeight(70)
        self.src.setAcceptDrops(False)  # 让拖进来的 PDF 冒泡到主窗口

        src_box = QWidget()
        v1 = QVBoxLayout(src_box)
        v1.setContentsMargins(10, 4, 10, 0)
        v1.setSpacing(2)
        v1.addWidget(self.src_title)
        v1.addWidget(self.src)

        # ---- 译文
        self.dst_title = QLabel("译文")
        self.dst_title.setObjectName("dim")
        self.dst = QPlainTextEdit()
        self.dst.setObjectName("translation")
        self.dst.setReadOnly(True)
        self.dst.setPlaceholderText("选中文本后自动翻译；Ctrl+Enter 翻译整页")
        self.dst.setAcceptDrops(False)
        f = QFont()
        f.setPointSizeF(11.0)
        self.dst.setFont(f)

        dst_box = QWidget()
        v2 = QVBoxLayout(dst_box)
        v2.setContentsMargins(10, 6, 10, 0)
        v2.setSpacing(2)
        v2.addWidget(self.dst_title)
        v2.addWidget(self.dst)

        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.addWidget(src_box)
        self.splitter.addWidget(dst_box)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes([170, 430])

        # ---- 底部
        self.status = QLabel("就绪")
        self.status.setObjectName("dim")
        self.status.setWordWrap(True)

        self.btn_page = QPushButton("整页翻译")
        self.btn_page.setObjectName("primary")
        self.btn_page.setToolTip("翻译当前页全部正文（Ctrl+Enter）")
        self.btn_retry = QPushButton("重译")
        self.btn_retry.setToolTip("用原文框里的内容（可先手动修正）重新翻译")
        self.btn_copy = QPushButton("复制译文")

        self.btn_page.clicked.connect(self.pageRequested.emit)
        self.btn_retry.clicked.connect(self._on_retry)
        self.btn_copy.clicked.connect(self._on_copy)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(10, 4, 10, 8)
        bottom.setSpacing(6)
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.btn_page)
        bottom.addWidget(self.btn_retry)
        bottom.addWidget(self.btn_copy)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addLayout(top)
        root.addWidget(self.splitter, 1)
        root.addLayout(bottom)

        self.setMinimumWidth(320)

    # ------------------------------------------------------------- 通道
    def set_channels(self, channels: list[tuple[str, str]], current: str) -> None:
        self.channel.blockSignals(True)
        self.channel.clear()
        for cid, label in channels:
            self.channel.addItem(label, cid)
        idx = self.channel.findData(current)
        if idx >= 0:
            self.channel.setCurrentIndex(idx)
        self.channel.blockSignals(False)

    def current_channel(self) -> str:
        data = self.channel.currentData()
        return str(data) if data else ""

    def _on_channel_changed(self, _index: int) -> None:
        self.channelChanged.emit(self.current_channel())

    def set_language_labels(self, src: str, dst: str) -> None:
        self.lang_label.setText(f"{lang_human(src)} → {lang_human(dst)}")

    # ------------------------------------------------------------- 内容
    def set_original(self, text: str) -> None:
        self.src.setPlainText(text)
        self.src_title.setText(f"原文 · {len(text)} 字符")

    def begin(self, note: str = "翻译中…") -> None:
        self._busy = True
        self._buffer = ""
        self.dst.clear()
        self.btn_page.setEnabled(False)
        self.btn_retry.setEnabled(False)
        self.dst_title.setText("译文")
        self.set_status(note, "busy")

    def append_delta(self, piece: str) -> None:
        if not piece:
            return
        self._buffer += piece
        cursor = self.dst.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(piece)
        bar = self.dst.verticalScrollBar()
        bar.setValue(bar.maximum())

    def finish(self, text: str, cached: bool = False) -> None:
        self._busy = False
        self._buffer = text
        self.dst.setPlainText(text)
        self.btn_page.setEnabled(True)
        self.btn_retry.setEnabled(True)
        self.dst_title.setText(f"译文 · {len(text)} 字符" + ("（缓存）" if cached else ""))

    def fail(self, message: str) -> None:
        self._busy = False
        self.btn_page.setEnabled(True)
        self.btn_retry.setEnabled(True)
        self.set_status(message, "error")

    # ------------------------------------------------------------- 状态
    def set_status(self, text: str, kind: str = "info") -> None:
        t = THEMES.get(self._theme, THEMES["day"])
        color = {
            "error": t["danger"],
            "busy": t["accent"],
            "ok": t["ok"],
            "info": t["text_dim"],
        }.get(kind, t["text_dim"])
        self.status.setStyleSheet(f"color:{color};")
        self.status.setText(text)

    def set_theme(self, key: str) -> None:
        self._theme = key

    def set_click_hint(self, text: str) -> None:
        if not self._buffer:
            self.dst.setPlaceholderText(text)

    # ------------------------------------------------------------- 槽
    def _on_retry(self) -> None:
        text = self.src.toPlainText().strip()
        if text:
            self.retranslateRequested.emit(text)

    def _on_copy(self) -> None:
        text = self.dst.toPlainText()
        if text:
            QGuiApplication.clipboard().setText(text)
            self.set_status("译文已复制到剪贴板", "ok")
