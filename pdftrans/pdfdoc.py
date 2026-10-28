"""PDF 文本层：字符级坐标、行列结构、区间取文、句/段扩展。

用 PyMuPDF 的 rawdict 拿到每个字符的 bbox，实现"整句/整段可拖选"的字符级选择。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

try:  # PyMuPDF >= 1.24 推荐 pymupdf，旧包名 fitz 仍兼容
    import pymupdf as fitz  # type: ignore
except ImportError:  # pragma: no cover
    import fitz  # type: ignore


SENT_END = re.compile(r"[.!?。！？；;]\s*")


@dataclass
class Char:
    ch: str
    x0: float
    y0: float
    x1: float
    y1: float
    line: int
    block: int


@dataclass
class Line:
    index: int
    block: int
    x0: float
    y0: float
    x1: float
    y1: float
    first: int
    last: int
    text: str


@dataclass
class PageText:
    page: int
    width: float
    height: float
    chars: list[Char]
    lines: list[Line]

    @property
    def plain(self) -> str:
        return " ".join(ln.text for ln in self.lines)


class PdfDocument:
    def __init__(self, path: str):
        self.path = path
        self._doc = fitz.open(path)
        if self._doc.needs_pass and not self._doc.authenticate(""):
            raise RuntimeError("这个 PDF 有密码保护，暂不支持。")
        self.page_count = int(self._doc.page_count)
        self._texts: dict[int, PageText] = {}

    # ------------------------------------------------------------- 基础
    def close(self) -> None:
        try:
            self._doc.close()
        except Exception:
            pass

    def page(self, index: int):
        return self._doc.load_page(index)

    def page_size(self, index: int) -> tuple[float, float]:
        rect = self.page(index).rect
        return rect.width, rect.height

    def text(self, index: int) -> PageText:
        cached = self._texts.get(index)
        if cached is None:
            cached = self._parse(index)
            self._texts[index] = cached
        return cached

    def _parse(self, index: int) -> PageText:
        page = self.page(index)
        width, height = page.rect.width, page.rect.height
        raw = page.get_text("rawdict", sort=False)

        chars: list[Char] = []
        lines: list[Line] = []
        block_no = -1
        line_no = -1

        for block in raw.get("blocks", []):
            block_no += 1
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_no += 1
                first = len(chars)
                for span in line.get("spans", []):
                    for ch in span.get("chars", []):
                        c = ch.get("c")
                        if c is None:
                            continue
                        x0, y0, x1, y1 = ch.get("bbox", (0, 0, 0, 0))
                        chars.append(Char(c, x0, y0, x1, y1, line_no, block_no))
                if len(chars) == first:
                    continue
                seg = chars[first:]
                lines.append(
                    Line(
                        index=line_no,
                        block=block_no,
                        x0=min(c.x0 for c in seg),
                        y0=min(c.y0 for c in seg),
                        x1=max(c.x1 for c in seg),
                        y1=max(c.y1 for c in seg),
                        first=first,
                        last=len(chars) - 1,
                        text="".join(c.ch for c in seg),
                    )
                )
        return PageText(index, width, height, chars, lines)

    # ------------------------------------------------------------- 区间
    def range_text(self, a: tuple[int, int], b: tuple[int, int]) -> str:
        """(page, char_index) 起止，含两端，自动处理跨页/跨行/跨段。"""
        if a > b:
            a, b = b, a
        pieces: list[str] = []
        for p in range(a[0], min(b[0], self.page_count - 1) + 1):
            pt = self.text(p)
            if not pt.chars:
                continue
            lo = a[1] if p == a[0] else 0
            hi = b[1] if p == b[0] else len(pt.chars) - 1
            lo = max(0, min(lo, len(pt.chars) - 1))
            hi = max(0, min(hi, len(pt.chars) - 1))
            if lo > hi:
                continue
            buf: list[str] = []
            prev_line: Optional[int] = None
            prev_block: Optional[int] = None
            for i in range(lo, hi + 1):
                c = pt.chars[i]
                if prev_line is not None and c.line != prev_line:
                    buf.append("\n" if c.block != prev_block else " ")
                buf.append(c.ch)
                prev_line = c.line
                prev_block = c.block
            pieces.append("".join(buf))
        return "\n".join(p for p in pieces if p.strip()).strip()

    def block_span(self, page: int, char_index: int) -> tuple[tuple[int, int], tuple[int, int]]:
        """包含该字符的段落（PyMuPDF block）首尾。"""
        pt = self.text(page)
        if not pt.chars:
            return (page, 0), (page, 0)
        idx = max(0, min(char_index, len(pt.chars) - 1))
        block = pt.chars[idx].block
        first = idx
        last = idx
        while first > 0 and pt.chars[first - 1].block == block:
            first -= 1
        while last < len(pt.chars) - 1 and pt.chars[last + 1].block == block:
            last += 1
        return (page, first), (page, last)

    def line_span(self, page: int, char_index: int) -> tuple[tuple[int, int], tuple[int, int]]:
        pt = self.text(page)
        if not pt.chars:
            return (page, 0), (page, 0)
        idx = max(0, min(char_index, len(pt.chars) - 1))
        line_no = pt.chars[idx].line
        first = idx
        last = idx
        while first > 0 and pt.chars[first - 1].line == line_no:
            first -= 1
        while last < len(pt.chars) - 1 and pt.chars[last + 1].line == line_no:
            last += 1
        return (page, first), (page, last)

    def sentence_span(self, page: int, char_index: int) -> tuple[tuple[int, int], tuple[int, int]]:
        """当前字符所在句子：在段落范围内按句末标点切开。"""
        start, end = self.block_span(page, char_index)
        pt = self.text(page)
        first, last = start[1], end[1]
        idx = max(first, min(char_index, last))
        text = "".join(c.ch for c in pt.chars[first : last + 1])
        rel = idx - first

        cut_points = [0]
        for m in SENT_END.finditer(text):
            if m.end() < len(text):
                cut_points.append(m.end())
        cut_points = sorted(set(cut_points))

        seg_start = 0
        for cp in cut_points:
            if cp <= rel:
                seg_start = cp
            else:
                break
        seg_end = len(text) - 1
        for cp in cut_points:
            if cp > rel:
                seg_end = cp - 1
                break
        seg_start = max(0, min(seg_start, len(text) - 1))
        seg_end = max(seg_start, min(seg_end, len(text) - 1))
        return (page, first + seg_start), (page, first + seg_end)

    # ------------------------------------------------------------- 整页
    def page_text_for_translation(self, page: int) -> str:
        """整页文本：按段落拼装，去掉孤立页码之类的噪声行。"""
        pt = self.text(page)
        paras: list[str] = []
        cur_block = None
        buf: list[str] = []
        for ln in pt.lines:
            stripped = ln.text.strip()
            if not stripped:
                continue
            if ln.block != cur_block:
                if buf:
                    paras.append(" ".join(buf))
                buf = [stripped]
                cur_block = ln.block
            else:
                buf.append(stripped)
        if buf:
            paras.append(" ".join(buf))
        out: list[str] = []
        for p in paras:
            if len(p) <= 3 and p.isdigit():
                continue
            out.append(p)
        return "\n\n".join(out)


# ---------------------------------------------------------------- 命中测试


def hit_char(pt: PageText, x: float, y: float) -> Optional[int]:
    """页面坐标 → 字符下标；空白处回退到最近行的最近字符。"""
    if not pt.chars:
        return None

    # 1) 直接落在字符框内
    for i, c in enumerate(pt.chars):
        if c.x0 - 0.5 <= x <= c.x1 + 0.5 and c.y0 - 0.5 <= y <= c.y1 + 0.5:
            return i

    # 2) 找纵向最近的行
    best_line: Optional[Line] = None
    best_dist = float("inf")
    for ln in pt.lines:
        if ln.y0 - 6 <= y <= ln.y1 + 6:
            dist = 0.0
        else:
            dist = min(abs(y - ln.y0), abs(y - ln.y1))
        if dist < best_dist:
            best_dist = dist
            best_line = ln

    if best_line is None or best_dist > 200:
        return None

    # 3) 行内按 x 最近
    idx = best_line.first
    for i in range(best_line.first, best_line.last + 1):
        c = pt.chars[i]
        if x <= c.x1:
            idx = i
            break
        idx = i
    return idx
