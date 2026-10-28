# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包脚本：目录模式（onedir）、无控制台、带图标与版本信息。

为什么不用 --onefile：
  单文件版本启动时要把 77MB 解压到 %TEMP%\_MEIxxxxx，本机安全策略会拦截
  这个临时目录创建（弹 "Could not create temporary directory!"），因此改用
  目录模式：不写临时目录、启动快、杀软误报也少。

用法：python -m PyInstaller --noconfirm --clean pdftrans.spec
产物：dist/PDFTrans/PDFTrans.exe（连同 _internal 一起分发）
"""

import os

ROOT = os.path.abspath(os.getcwd())

a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    binaries=[],
    datas=[
        ("assets/app.ico", "assets"),
        ("assets/app.png", "assets"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 这些模块本项目用不到，剔掉最省体积
    excludes=[
        "tkinter",
        "pydoc",
        "doctest",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtPositioning",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtWebSockets",
        "PySide6.QtWebChannel",
        "PySide6.QtTest",
        "PySide6.QtDesigner",
        "PySide6.QtHelp",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PDFTrans",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "assets", "app.ico"),
    version=os.path.join(ROOT, "tools", "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PDFTrans",
)
