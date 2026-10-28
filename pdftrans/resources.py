"""资源路径：源码运行与 PyInstaller 打包后都能找到 assets。"""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(relative: str) -> Path:
    """相对项目根的路径；单文件打包时根目录是 sys._MEIPASS。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative
    return Path(__file__).resolve().parent.parent / relative


def icon_path() -> Path:
    for rel in ("assets/app.ico", "assets/app.png"):
        candidate = resource_path(rel)
        if candidate.exists():
            return candidate
    return resource_path("assets/app.ico")
