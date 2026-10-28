"""生成应用图标：assets/app.png（1024）与 assets/app.ico（多尺寸）。

设计：蓝紫渐变的圆角方块底 + 白色文档（三条文本行）+ 右下角对话气泡，
表示「文档 → 译文」。全部矢量绘制，16px 下仍能辨认轮廓。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

S = 1024


def build_png() -> Path:
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841

    img = QImage(S, S, QImage.Format_ARGB32)
    img.fill(Qt.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)

    # 背景：圆角方块 + 对角渐变
    bg = QPainterPath()
    bg.addRoundedRect(QRectF(0, 0, S, S), 0.23 * S, 0.23 * S)
    grad = QLinearGradient(0, 0, S, S)
    grad.setColorAt(0.0, QColor("#2f6fed"))
    grad.setColorAt(1.0, QColor("#6a3bf0"))
    p.fillPath(bg, grad)

    # 文档
    paper = QPainterPath()
    paper.addRoundedRect(QRectF(0.17 * S, 0.15 * S, 0.53 * S, 0.62 * S), 0.07 * S, 0.07 * S)
    p.fillPath(paper, QColor("#ffffff"))

    # 文本行
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#b9cdfb"))
    for row, width in ((0.30, 0.33), (0.42, 0.33), (0.54, 0.20)):
        p.drawRoundedRect(QRectF(0.25 * S, row * S, width * S, 0.048 * S), 0.024 * S, 0.024 * S)

    # 气泡 + 尾巴
    bubble = QPainterPath()
    bubble.addRoundedRect(QRectF(0.50 * S, 0.50 * S, 0.35 * S, 0.27 * S), 0.09 * S, 0.09 * S)
    tail = QPainterPath()
    tail.moveTo(0.57 * S, 0.72 * S)
    tail.lineTo(0.54 * S, 0.87 * S)
    tail.lineTo(0.70 * S, 0.755 * S)
    tail.closeSubpath()
    bubble = bubble.united(tail)
    p.fillPath(bubble, QColor("#ffffff"))

    # 气泡里的三个点（省略号 = 正在生成译文）
    p.setBrush(QColor("#3a56e0"))
    for i in range(3):
        p.drawEllipse(QPointF((0.578 + i * 0.082) * S, 0.635 * S), 0.027 * S, 0.027 * S)

    p.end()

    ASSETS.mkdir(parents=True, exist_ok=True)
    out = ASSETS / "app.png"
    img.save(str(out))
    return out


def build_ico(png: Path) -> Path:
    from PIL import Image

    ico = ASSETS / "app.ico"
    im = Image.open(png).convert("RGBA")
    im.save(
        ico,
        format="ICO",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)],
    )
    return ico


if __name__ == "__main__":
    png_path = build_png()
    ico_path = build_ico(png_path)
    print("png:", png_path, png_path.stat().st_size, "bytes")
    print("ico:", ico_path, ico_path.stat().st_size, "bytes")
