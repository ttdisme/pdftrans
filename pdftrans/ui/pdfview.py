"""PDF 阅读视图：连续滚动、懒渲染、字符级拖选。"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView

try:
    import pymupdf as fitz  # type: ignore
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from ..pdfdoc import PageText, PdfDocument, hit_char

SEL_COLOR = QColor(64, 132, 255, 70)
SEL_BORDER = QColor(64, 132, 255, 130)


def _selection_rects(pt: PageText, a: int, b: int, zoom: float) -> list[QRectF]:
    rects: list[QRectF] = []
    if not pt.chars:
        return rects
    lo = max(0, min(a, len(pt.chars) - 1))
    hi = max(0, min(b, len(pt.chars) - 1))
    cur: Optional[QRectF] = None
    cur_line: Optional[int] = None
    for i in range(lo, hi + 1):
        c = pt.chars[i]
        r = QRectF(
            c.x0 * zoom,
            c.y0 * zoom,
            max(c.x1 - c.x0, 0.8) * zoom,
            max(c.y1 - c.y0, 0.6) * zoom,
        )
        if cur is not None and c.line == cur_line:
            cur = cur.united(r)
        else:
            if cur is not None:
                rects.append(cur)
            cur = r
            cur_line = c.line
    if cur is not None:
        rects.append(cur)
    return rects


class PageItem(QGraphicsItem):
    def __init__(self, doc: PdfDocument, index: int, zoom: float):
        super().__init__()
        self.doc = doc
        self.index = index
        self.zoom = zoom
        page_w, page_h = doc.page_size(index)
        self.page_w = page_w
        self.page_h = page_h
        self._pix: Optional[QPixmap] = None
        self.selection: list[tuple[int, int]] = []
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)

    # -- 几何
    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(0, 0, self.page_w * self.zoom, self.page_h * self.zoom)

    @property
    def w(self) -> float:
        return self.page_w * self.zoom

    @property
    def h(self) -> float:
        return self.page_h * self.zoom

    # -- 渲染
    def ensure_rendered(self, dpr: float) -> None:
        if self._pix is not None:
            return
        page = self.doc.page(self.index)
        matrix = fitz.Matrix(self.zoom * dpr, self.zoom * dpr)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        img = img.copy()
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        self._pix = pm

    def invalidate(self) -> None:
        self._pix = None
        self.update()

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: N802
        if self._pix is not None:
            painter.drawPixmap(QRectF(0, 0, self.w, self.h), self._pix, QRectF(self._pix.rect()))
        else:
            painter.fillRect(self.boundingRect(), QColor("#ffffff"))
        if not self.selection:
            return
        pt = self.doc.text(self.index)
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(SEL_COLOR)
        for a, b in self.selection:
            for r in _selection_rects(pt, a, b, self.zoom):
                painter.drawRect(r)
        painter.restore()


class PdfView(QGraphicsView):
    selectionLive = Signal(str)       # 拖动过程中的实时文本
    selectionCommitted = Signal(str)  # 松手后用于触发翻译
    pageChanged = Signal(int, int)    # 当前页, 总页数
    zoomChanged = Signal(float)
    fileDropped = Signal(str)         # 拖进来的 PDF 路径

    MARGIN = 16
    GAP = 14

    def __init__(self, parent=None):
        scene = QGraphicsScene()
        super().__init__(scene, parent)
        self._scene = scene
        self.doc: Optional[PdfDocument] = None
        self.zoom = 1.2
        self.click_mode = "sentence"
        self.items: list[PageItem] = []
        self._anchor: Optional[tuple[int, int]] = None
        self._current: Optional[tuple[int, int]] = None
        self._dragging = False
        self._dpr = 1.0

        self.setRenderHints(
            QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing
        )
        self.setBackgroundBrush(QColor(56, 60, 66))
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setStyleSheet("QGraphicsView{border:0;}")
        # 拖放：QGraphicsView 的内容落在 viewport 上，两处都要开，否则光标是「禁止」
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(60)
        self._render_timer.timeout.connect(self._render_visible)

    # ------------------------------------------------------------- 拖放
    @staticmethod
    def _dropped_pdf(mime) -> Optional[str]:
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            path = url.toLocalFile()
            if path and path.lower().endswith(".pdf"):
                return path
        return None

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._dropped_pdf(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()  # 非 PDF 不给「可放置」光标

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if self._dropped_pdf(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        path = self._dropped_pdf(event.mimeData())
        if path:
            event.setDropAction(Qt.CopyAction)
            event.accept()
            self.fileDropped.emit(path)
        else:
            event.ignore()

    # ------------------------------------------------------------- 文档
    def load_pdf(self, path: str) -> None:
        self.close_doc()
        self.doc = PdfDocument(path)
        self._build_items()
        if self.items:
            self.verticalScrollBar().setValue(0)
        self.pageChanged.emit(self.current_page(), self.page_count)
        self._schedule_render()

    def close_doc(self) -> None:
        self._clear_selection()
        if self.doc is not None:
            self.doc.close()
            self.doc = None
        self.items = []
        self._scene.clear()

    @property
    def page_count(self) -> int:
        return self.doc.page_count if self.doc else 0

    def _build_items(self) -> None:
        self._scene.clear()
        self.items = []
        if not self.doc:
            return
        y = 0.0
        max_w = 0.0
        for i in range(self.doc.page_count):
            it = PageItem(self.doc, i, self.zoom)
            it.setPos(self.MARGIN, y)
            self._scene.addItem(it)
            self.items.append(it)
            y += it.h + self.GAP
            max_w = max(max_w, it.w)
        self._scene.setSceneRect(
            QRectF(-self.MARGIN, -self.MARGIN, max_w + self.MARGIN * 2, y + self.MARGIN)
        )

    # ------------------------------------------------------------- 渲染
    def _schedule_render(self) -> None:
        self._render_timer.start()

    def _render_visible(self) -> None:
        if not self.doc or not self.items:
            return
        dpr = self.devicePixelRatioF() or 1.0
        self._dpr = dpr
        area = self.mapToScene(self.viewport().rect()).boundingRect().adjusted(0, -600, 0, 600)
        for it in self.items:
            if it.sceneBoundingRect().intersects(area):
                it.ensure_rendered(dpr)
                it.update()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._dpr = self.devicePixelRatioF() or 1.0
        self._schedule_render()

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802
        super().scrollContentsBy(dx, dy)
        self._schedule_render()
        self.pageChanged.emit(self.current_page(), self.page_count)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._schedule_render()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        if self.items:
            return
        painter.save()
        painter.resetTransform()
        painter.setPen(QColor("#9aa0a6"))
        painter.drawText(
            self.viewport().rect(),
            Qt.AlignCenter,
            "打开一个 PDF 开始（Ctrl+O，或直接把文件拖进来）",
        )
        painter.restore()

    # ------------------------------------------------------------- 缩放
    def set_zoom(self, z: float) -> None:
        z = max(0.35, min(4.5, float(z)))
        if abs(z - self.zoom) < 0.004:
            return
        if not self.items:
            self.zoom = z
            self.zoomChanged.emit(self.zoom)
            return

        page_idx = self.current_page()
        center = self.mapToScene(self.viewport().rect().center())
        it = self.items[min(page_idx, len(self.items) - 1)]
        ratio = (center.y() - it.pos().y()) / max(it.h, 1.0)

        self.zoom = z
        self._build_items()

        it2 = self.items[min(page_idx, len(self.items) - 1)]
        target_y = it2.pos().y() + max(0.0, min(1.0, ratio)) * it2.h
        self.centerOn(it2.pos().x() + it2.w / 2, target_y)
        self._reapply_selection()
        self.zoomChanged.emit(self.zoom)
        self._schedule_render()

    def zoom_in(self) -> None:
        self.set_zoom(self.zoom * 1.15)

    def zoom_out(self) -> None:
        self.set_zoom(self.zoom / 1.15)

    def fit_width(self) -> None:
        if not self.items:
            return
        avail = self.viewport().width() - self.MARGIN * 2 - 8
        if avail <= 50:
            return
        self.set_zoom(avail / max(self.items[0].page_w, 1.0))

    def fit_page(self) -> None:
        if not self.items:
            return
        avail_w = self.viewport().width() - self.MARGIN * 2 - 8
        avail_h = self.viewport().height() - self.MARGIN * 2 - 8
        it = self.items[0]
        if avail_w <= 50 or avail_h <= 50 or it.page_h <= 0:
            return
        self.set_zoom(min(avail_w / it.page_w, avail_h / it.page_h))

    # ------------------------------------------------------------- 页码
    def current_page(self) -> int:
        if not self.items:
            return 0
        center = self.mapToScene(self.viewport().rect().center())
        best = 0
        best_d = float("inf")
        for it in self.items:
            r = it.sceneBoundingRect()
            if r.contains(center):
                return it.index
            d = abs((r.top() + r.bottom()) / 2 - center.y())
            if d < best_d:
                best_d = d
                best = it.index
        return best

    def goto_page(self, index: int) -> None:
        if not self.items:
            return
        index = max(0, min(int(index), len(self.items) - 1))
        it = self.items[index]
        self.centerOn(it.pos().x() + it.w / 2, it.pos().y() + self.viewport().height() * 0.45)
        self._schedule_render()

    # ------------------------------------------------------------- 选择
    def selected_text(self) -> str:
        if not self.doc or self._anchor is None or self._current is None:
            return ""
        return self.doc.range_text(self._anchor, self._current)

    def _hit(self, pos: QPointF) -> Optional[tuple[int, int]]:
        if not self.items:
            return None
        sp = self.mapToScene(pos.toPoint())
        for it in self.items:
            if it.sceneBoundingRect().contains(sp):
                local = it.mapFromScene(sp)
                idx = hit_char(it.doc.text(it.index), local.x() / it.zoom, local.y() / it.zoom)
                if idx is None:
                    return None
                return (it.index, idx)
        return None

    def _apply_selection(self) -> None:
        if self._anchor is None or self._current is None:
            return
        a, b = self._anchor, self._current
        if a > b:
            a, b = b, a
        for it in self.items:
            it.selection.clear()
        for p in range(a[0], min(b[0], len(self.items) - 1) + 1):
            it = self.items[p]
            n = len(it.doc.text(p).chars)
            if n == 0:
                continue
            lo = a[1] if p == a[0] else 0
            hi = b[1] if p == b[0] else n - 1
            lo = max(0, min(lo, n - 1))
            hi = max(0, min(hi, n - 1))
            if lo <= hi:
                it.selection.append((lo, hi))
            it.update()
        self.selectionLive.emit(self.selected_text())

    def _reapply_selection(self) -> None:
        if self._anchor is not None and self._current is not None:
            self._apply_selection()

    def _clear_selection(self) -> None:
        self._anchor = None
        self._current = None
        self._dragging = False
        for it in self.items:
            it.selection.clear()
            it.update()
        self.selectionLive.emit("")

    def clear_selection(self) -> None:
        self._clear_selection()

    def select_span(self, page: int, char_index: int, mode: str = "sentence") -> str:
        if not self.doc:
            return ""
        if mode == "line":
            a, b = self.doc.line_span(page, char_index)
        elif mode in ("paragraph", "block"):
            a, b = self.doc.block_span(page, char_index)
        else:
            a, b = self.doc.sentence_span(page, char_index)
        self._anchor, self._current = a, b
        self._apply_selection()
        return self.selected_text()

    def select_current_page(self) -> str:
        if not self.doc or not self.items:
            return ""
        p = self.current_page()
        n = len(self.doc.text(p).chars)
        if n == 0:
            return ""
        self._anchor, self._current = (p, 0), (p, n - 1)
        self._apply_selection()
        return self.selected_text()

    # ------------------------------------------------------------- 事件
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.doc is not None:
            hit = self._hit(event.position())
            if hit is not None:
                self._anchor = hit
                self._current = hit
                self._dragging = True
                self._apply_selection()
                event.accept()
                return
            self._clear_selection()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging and self._anchor is not None:
            hit = self._hit(event.position())
            if hit is not None and hit != self._current:
                self._current = hit
                self._apply_selection()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            self._dragging = False
            if self._anchor is not None and self._anchor == self._current and self.doc:
                self.select_span(self._anchor[0], self._anchor[1], self.click_mode)
            text = self.selected_text()
            if text.strip():
                self.selectionCommitted.emit(text)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        hit = self._hit(event.position())
        if hit is not None and self.doc:
            self._dragging = False
            a, b = self.doc.block_span(*hit)
            self._anchor, self._current = a, b
            self._apply_selection()
            self.selectionCommitted.emit(self.selected_text())
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.set_zoom(self.zoom * (1.1 if delta > 0 else 1 / 1.1))
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key_PageDown, Qt.Key_PageUp):
            step = 1 if key == Qt.Key_PageDown else -1
            self.goto_page(min(self.page_count - 1, max(0, self.current_page() + step)))
            event.accept()
            return
        if key == Qt.Key_Escape:
            self._clear_selection()
            event.accept()
            return
        super().keyPressEvent(event)
