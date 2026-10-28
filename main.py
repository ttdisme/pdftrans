"""程序入口。"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path


def _log_startup_error(text: str) -> Path | None:
    """把 traceback 尽力写到几个候选位置，返回成功写下的路径。"""
    candidates: list[Path] = [Path.cwd()]
    try:
        from pdftrans.config import config_dir

        candidates.append(config_dir())
    except Exception:
        pass
    try:
        candidates.append(Path(tempfile.gettempdir()))
    except Exception:
        pass
    try:
        candidates.append(Path(sys.executable).parent)
    except Exception:
        pass

    for base in candidates:
        try:
            target = Path(base) / "startup-error.log"
            with open(target, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{text}\n")
            return target
        except Exception:
            continue
    return None


def _install_exception_hook() -> None:
    """打包成无控制台的 exe 后，未捕获异常也要留痕。"""

    def hook(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        # console 版：先打到 stderr
        try:
            if sys.stderr is not None:
                sys.stderr.write(text + "\n")
                sys.stderr.flush()
        except Exception:
            pass
        log_file = _log_startup_error(text)

        # 设了 PDFTRANS_SILENT=1 就只记录、不弹框（自动化测试用）
        if os.environ.get("PDFTRANS_SILENT") == "1":
            return

        try:
            from PySide6.QtWidgets import QMessageBox

            message = f"{exc_type.__name__}: {exc}"
            if log_file is not None:
                message += f"\n\n详情已写入：\n{log_file}"
            QMessageBox.critical(None, "程序出错了", message)
        except Exception:
            pass

    sys.excepthook = hook


def _selftest(
    app,
    window,
    shot: str | None,
    pdfs: list[str],
    translate: bool = False,
    drop: bool = False,
) -> int:
    """打包后的自检：起窗口、可选打开多个 PDF、可选真翻一句、截图、写日志、退出。

    用法：
      PDFTrans.exe --selftest a.pdf [b.pdf ...] [--shot out.png]
                              [--translate] [--drop]
    退出码 0 = 正常；2 = 窗口/截图异常。
    """
    import time as _time
    from pathlib import Path

    from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QTimer, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    from PySide6.QtWidgets import QApplication

    result = {"ok": False, "text": "", "drop_pages": "-"}
    started = _time.time()
    pdf = pdfs[0] if pdfs else None

    def simulate_drop() -> None:
        """用真实的 QDropEvent 走一遍拖放链路（等价于把文件拖进窗口）。"""
        view = window.view
        if not pdf or view is None:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(pdf)])
        widget = view.viewport()
        pos = QPoint(80, 80)
        enter = QDragEnterEvent(
            pos,
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(widget, enter)
        dropped = QDropEvent(
            QPointF(80, 80),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(widget, dropped)
        cur = window.view
        result["drop_pages"] = (
            f"{cur.page_count}(accepted={enter.isAccepted()})" if cur else "no-view"
        )

    def finish() -> None:
        try:
            for task in list(window._tasks):
                task.cancel()
            pix = window.grab()
            if shot:
                Path(shot).parent.mkdir(parents=True, exist_ok=True)
                pix.save(shot)
            from pdftrans.config import config_dir

            cur = window.view
            lines = [
                f"window={pix.width()}x{pix.height()}",
                f"tabs={window.tabs.count()}",
                f"pages={cur.page_count if cur else 0}",
                f"channel={window.config.engine}",
                f"theme={window.config.theme}",
                f"data_dir={config_dir()}",
                f"cache_enabled={window.cache.enabled}",
                f"cache_error={window.cache.last_error or '-'}",
                f"drop_pages={result['drop_pages']}",
                f"translate={result['text'] or '-'}",
                f"pdf={'; '.join(Path(p).name for p in pdfs) or '-'}",
                f"shot={shot or '-'}",
            ]
            log = Path(shot).with_suffix(".log") if shot else Path("selftest.log")
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")
            result["ok"] = pix.width() > 300 and pix.height() > 200
        except Exception as e:  # noqa: BLE001
            result["text"] = f"{type(e).__name__}: {e}"
        finally:
            app.quit()

    if drop:
        QTimer.singleShot(600, simulate_drop)
        QTimer.singleShot(2200, finish)
    elif translate and pdf:
        # 真跑一次「划词 → 请求 → 流式显示」，验证打包后的 HTTPS 与线程
        view = window.view
        if view is not None:
            view.select_span(0, 320, "sentence")
            window.start_translate(view.selected_text())

        def poll() -> None:
            out = window.panel.dst.toPlainText().strip()
            if out:
                result["text"] = out[:400].replace("\n", " ⏎ ")
                finish()
                return
            if _time.time() - started > 25:
                result["text"] = "EMPTY/TIMEOUT"
                finish()
                return
            QTimer.singleShot(400, poll)

        QTimer.singleShot(800, poll)
    else:
        QTimer.singleShot(1800, finish)

    app.exec()
    return 0 if result["ok"] else 2


def main() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    from pdftrans.config import load_config
    from pdftrans.resources import icon_path
    from pdftrans.ui.mainwindow import MainWindow

    argv = list(sys.argv[1:])
    selftest = "--selftest" in argv
    shot = None
    if "--shot" in argv:
        idx = argv.index("--shot")
        if idx + 1 < len(argv):
            shot = argv[idx + 1]
    pdf_args = [a for a in argv if a.lower().endswith(".pdf")]
    drop_test = "--drop" in argv

    app = QApplication(sys.argv)
    app.setApplicationName("PDFTrans")
    app.setApplicationDisplayName("PDF 论文翻译")

    icon_file = icon_path()
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    _install_exception_hook()

    config = load_config()
    window = MainWindow(config)
    window.show()

    if pdf_args and not drop_test:
        for one_pdf in pdf_args:
            window.open_pdf(one_pdf)

    if selftest:
        return _selftest(
            app, window, shot, pdf_args, translate="--translate" in argv, drop=drop_test
        )

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
