"""主窗口：多标签 PDF 阅读 + 共享右侧翻译栏。

每个标签页是一个独立的 PdfView（各自的文档、页码、缩放、选区），
右侧翻译面板与通道设置由所有标签共享。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QGuiApplication, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolBar,
)

from ..cache import TranslationCache
from ..config import (
    ENGINE_LABELS,
    AppConfig,
    export_config,
    import_config,
    save_config,
)
from ..engines import TranslateError, make_engine
from ..worker import TranslateTask
from .panel import TranslatePanel
from .pdfview import PdfView
from .settings import SettingsDialog
from .styles import THEME_ORDER, THEMES, make_qss, theme_name


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self.cache = TranslationCache(limit=config.cache_limit, enabled=True)
        self._tasks: list[TranslateTask] = []
        self._theme_actions: dict[str, QAction] = {}
        self._channel_actions: dict[str, QAction] = {}

        self.setWindowTitle("PDF 论文翻译")
        self.resize(1360, 880)
        self.setAcceptDrops(True)

        from ..resources import icon_path

        icon_file = icon_path()
        if icon_file.exists():
            self.setWindowIcon(QIcon(str(icon_file)))

        self._build_center()
        self._build_toolbar()
        self._build_menus()
        self._apply_theme(config.theme)
        self._restore_window()
        self._refresh_status()
        self._update_title()

    # ------------------------------------------------------------- 当前视图
    @property
    def view(self) -> PdfView | None:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, PdfView) else None

    # ------------------------------------------------------------- 界面
    def _build_center(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setUsesScrollButtons(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.empty_hint = QLabel(
            "把 PDF 拖进窗口，或按 Ctrl+O 打开\n"
            "支持一次选多个文件，标签之间可自由切换"
        )
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setStyleSheet(
            "background:#383c42; color:#9aa0a6; font-size:14px; border:0;"
        )

        self.stack = QStackedWidget()
        self.stack.addWidget(self.tabs)
        self.stack.addWidget(self.empty_hint)
        self.stack.setCurrentWidget(self.empty_hint)
        self.stack.setMinimumWidth(420)

        self.panel = TranslatePanel()
        self.panel.set_channels(
            [(eid, label) for eid, label in ENGINE_LABELS.items()], self.config.engine
        )
        self.panel.set_language_labels(self.config.source_lang, self.config.target_lang)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.stack)
        splitter.addWidget(self.panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([920, 440])
        self.splitter = splitter
        self.setCentralWidget(splitter)

        self.panel.channelChanged.connect(self._on_channel_changed)
        self.panel.pageRequested.connect(self.translate_page)
        self.panel.retranslateRequested.connect(lambda t: self.start_translate(t, kind="retry"))

    def _new_view(self) -> PdfView:
        view = PdfView()
        view.click_mode = self.config.click_mode
        view.selectionCommitted.connect(self._on_selection)
        view.selectionLive.connect(self._on_live_selection)
        view.pageChanged.connect(self._on_page_changed)
        view.zoomChanged.connect(self._on_zoom_changed)
        view.fileDropped.connect(lambda p: self._open_paths([p]))
        return view

    def _build_toolbar(self) -> None:
        bar = QToolBar("主工具栏")
        bar.setMovable(False)
        self.addToolBar(bar)

        self.act_open = QAction("打开 PDF", self)
        self.act_open.setShortcut(QKeySequence.Open)
        self.act_open.triggered.connect(lambda: self.open_pdf())
        bar.addAction(self.act_open)

        self.act_new_tab = QAction("＋", self)
        self.act_new_tab.setToolTip("再打开一个 PDF（新标签，Ctrl+O）")
        self.act_new_tab.triggered.connect(lambda: self.open_pdf())
        bar.addAction(self.act_new_tab)
        bar.addSeparator()

        self.act_prev = QAction("上一页", self)
        self.act_prev.triggered.connect(lambda: self._step_page(-1))
        bar.addAction(self.act_prev)

        self.spin_page = QSpinBox()
        self.spin_page.setMinimum(1)
        self.spin_page.setMaximum(1)
        self.spin_page.setFixedWidth(64)
        self.spin_page.setToolTip("跳转到指定页")
        self.spin_page.valueChanged.connect(lambda v: self._goto_page(v - 1))
        bar.addWidget(self.spin_page)

        self.lbl_pages = QLabel(" / 0 ")
        bar.addWidget(self.lbl_pages)

        self.act_next = QAction("下一页", self)
        self.act_next.triggered.connect(lambda: self._step_page(1))
        bar.addAction(self.act_next)
        bar.addSeparator()

        self.act_fit_w = QAction("适应宽度", self)
        self.act_fit_w.triggered.connect(self._fit_width)
        bar.addAction(self.act_fit_w)

        self.lbl_zoom = QLabel("--")
        self.lbl_zoom.setMinimumWidth(48)
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        bar.addWidget(self.lbl_zoom)

    def _build_menus(self) -> None:
        bar = self.menuBar()

        # 文件
        m_file = bar.addMenu("文件")
        m_file.addAction(self.act_open)
        act = m_file.addAction("再打开一个…（新标签）")
        act.triggered.connect(lambda: self.open_pdf())
        act_close = m_file.addAction("关闭当前标签")
        act_close.setShortcut(QKeySequence("Ctrl+W"))
        act_close.triggered.connect(self._close_current_tab)
        m_file.addSeparator()
        self.menu_recent = m_file.addMenu("最近打开")
        self._rebuild_recent_menu()
        m_file.addSeparator()
        act_imp = m_file.addAction("导入设置…")
        act_imp.triggered.connect(self._import_settings)
        act_exp = m_file.addAction("导出设置…")
        act_exp.triggered.connect(self._export_settings)
        m_file.addSeparator()
        act_quit = m_file.addAction("退出")
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)

        # 翻译
        m_tr = bar.addMenu("翻译")
        act_sel = m_tr.addAction("翻译选区")
        act_sel.setShortcut(QKeySequence("Ctrl+Shift+T"))
        act_sel.triggered.connect(self.translate_selection)
        act_page = m_tr.addAction("翻译当前整页")
        act_page.setShortcut(QKeySequence("Ctrl+Return"))
        act_page.triggered.connect(self.translate_page)
        act_clip = m_tr.addAction("翻译剪贴板")
        act_clip.setShortcut(QKeySequence("Ctrl+Shift+V"))
        act_clip.triggered.connect(self.translate_clipboard)
        m_tr.addSeparator()

        m_ch = m_tr.addMenu("翻译通道")
        group = QActionGroup(self)
        group.setExclusive(True)
        for eid, label in ENGINE_LABELS.items():
            a = QAction(label, self, checkable=True)
            a.setData(eid)
            a.setChecked(eid == self.config.engine)
            a.triggered.connect(lambda _c=False, e=eid: self._set_channel(e))
            group.addAction(a)
            m_ch.addAction(a)
            self._channel_actions[eid] = a
        m_tr.addSeparator()
        act_set = m_tr.addAction("设置…")
        act_set.setShortcut(QKeySequence("Ctrl+,"))
        act_set.triggered.connect(self.open_settings)

        # 视图
        m_view = bar.addMenu("视图")
        a = m_view.addAction("放大")
        a.setShortcut(QKeySequence.ZoomIn)
        a.triggered.connect(self._zoom_in)
        a = m_view.addAction("缩小")
        a.setShortcut(QKeySequence.ZoomOut)
        a.triggered.connect(self._zoom_out)
        a = m_view.addAction("适应宽度")
        a.setShortcut(QKeySequence("Ctrl+0"))
        a.triggered.connect(self._fit_width)
        a = m_view.addAction("适应整页")
        a.setShortcut(QKeySequence("Ctrl+9"))
        a.triggered.connect(self._fit_page)
        a = m_view.addAction("清除选区")
        a.setShortcut(QKeySequence("Ctrl+D"))
        a.triggered.connect(self._clear_selection)
        m_view.addSeparator()
        a = m_view.addAction("下一个标签")
        a.setShortcut(QKeySequence("Ctrl+Tab"))
        a.triggered.connect(lambda: self._cycle_tab(1))
        a = m_view.addAction("上一个标签")
        a.setShortcut(QKeySequence("Ctrl+Shift+Tab"))
        a.triggered.connect(lambda: self._cycle_tab(-1))
        m_view.addSeparator()

        m_theme = m_view.addMenu("主题")
        tgroup = QActionGroup(self)
        tgroup.setExclusive(True)
        for key in THEME_ORDER:
            a = QAction(theme_name(key), self, checkable=True)
            a.setChecked(key == self.config.theme)
            a.triggered.connect(lambda _c=False, k=key: self._apply_theme(k))
            tgroup.addAction(a)
            m_theme.addAction(a)
            self._theme_actions[key] = a

        # 帮助
        m_help = bar.addMenu("帮助")
        a = m_help.addAction("使用说明")
        a.triggered.connect(self._show_help)
        a = m_help.addAction("关于")
        a.triggered.connect(self._show_about)

    # ------------------------------------------------------------- 状态
    def _refresh_status(self) -> None:
        label = ENGINE_LABELS.get(self.config.engine, self.config.engine)
        self.statusBar().showMessage(f"通道：{label}")

    def _on_live_selection(self, text: str) -> None:
        if text.strip():
            self.statusBar().showMessage(f"已选 {len(text)} 字符", 1500)

    def _show_page_info(self, page: int, total: int) -> None:
        self.spin_page.blockSignals(True)
        self.spin_page.setMaximum(max(1, total))
        self.spin_page.setValue(page + 1 if total else 1)
        self.spin_page.blockSignals(False)
        self.lbl_pages.setText(f" / {total} ")

    def _on_page_changed(self, page: int, total: int) -> None:
        # 只有当前标签的翻页才更新工具栏
        if self.sender() is not None and self.sender() is not self.view:
            return
        self._show_page_info(page, total)

    def _on_zoom_changed(self, zoom: float) -> None:
        if self.sender() is not None and self.sender() is not self.view:
            return
        self.lbl_zoom.setText(f"{int(round(zoom * 100))}%")

    def _on_tab_changed(self, _index: int) -> None:
        view = self.view
        if view is None:
            self._show_page_info(0, 0)
            self.lbl_zoom.setText("--")
        else:
            self._show_page_info(view.current_page(), view.page_count)
            self.lbl_zoom.setText(f"{int(round(view.zoom * 100))}%")
        self._update_title()

    def _update_title(self) -> None:
        view = self.view
        if view is None:
            self.setWindowTitle("PDF 论文翻译")
            return
        index = self.tabs.currentIndex()
        total = self.tabs.count()
        name = getattr(view, "doc_title", None) or self.tabs.tabText(index)
        suffix = f"（{index + 1}/{total}）" if total > 1 else ""
        self.setWindowTitle(f"{name}{suffix} — PDF 论文翻译")

    def _cycle_tab(self, step: int) -> None:
        count = self.tabs.count()
        if count < 2:
            return
        self.tabs.setCurrentIndex((self.tabs.currentIndex() + step) % count)

    # ------------------------------------------------------------- 打开/关闭
    def open_pdf(self, path: str | None = None) -> None:
        if path:
            self._open_paths([path])
            return
        start = self.config.last_dir or str(Path.home())
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "打开 PDF（可按住 Ctrl / Shift 多选）",
            start,
            "PDF 文件 (*.pdf);;所有文件 (*.*)",
        )
        if paths:
            self._open_paths(paths)

    def _open_paths(self, paths: list[str]) -> None:
        pdfs = [p for p in paths if p and p.lower().endswith(".pdf")]
        if not pdfs:
            return

        opened = 0
        errors: list[str] = []
        last_dir = self.config.last_dir

        for path in pdfs:
            view = self._new_view()
            try:
                view.load_pdf(path)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{Path(path).name}：{e}")
                view.deleteLater()
                continue

            name = Path(path).name
            view.doc_title = name
            short = name[:-4] if name.lower().endswith(".pdf") else name
            if len(short) > 20:
                short = short[:19] + "…"
            index = self.tabs.addTab(view, short)
            self.tabs.setTabToolTip(index, path)
            self.tabs.setCurrentIndex(index)
            self.stack.setCurrentWidget(self.tabs)
            view.set_zoom(self.config.zoom)
            QTimer.singleShot(70, view.fit_width)

            last_dir = str(Path(path).parent)
            recents = [path] + [p for p in self.config.recent_files if p != path]
            self.config.recent_files = recents[:12]
            opened += 1

        if opened:
            self.config.last_dir = last_dir
            save_config(self.config)
            self._rebuild_recent_menu()
            self.panel.set_status(f"共 {self.tabs.count()} 个标签", "info")
            self._refresh_status()

        if errors:
            QMessageBox.warning(self, "有文件打不开", "\n".join(errors[:8]))

    def close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is None:
            return
        self.tabs.removeTab(index)
        if isinstance(widget, PdfView):
            widget.close_doc()
            widget.deleteLater()
        if self.tabs.count() == 0:
            self.stack.setCurrentWidget(self.empty_hint)
            self._show_page_info(0, 0)
            self.lbl_zoom.setText("--")
            self._update_title()

    def _close_current_tab(self) -> None:
        index = self.tabs.currentIndex()
        if index >= 0:
            self.close_tab(index)

    def _rebuild_recent_menu(self) -> None:
        self.menu_recent.clear()
        files = [p for p in self.config.recent_files if Path(p).exists()]
        if not files:
            a = self.menu_recent.addAction("（暂无）")
            a.setEnabled(False)
            return
        for p in files:
            a = self.menu_recent.addAction(Path(p).name)
            a.setToolTip(p)
            a.triggered.connect(lambda _c=False, path=p: self.open_pdf(path))

    # ------------------------------------------------------------- 视图操作
    def _step_page(self, delta: int) -> None:
        view = self.view
        if view is None or not view.page_count:
            return
        target = max(0, min(view.page_count - 1, view.current_page() + delta))
        view.goto_page(target)

    def _goto_page(self, index: int) -> None:
        view = self.view
        if view is not None:
            view.goto_page(index)

    def _zoom_in(self) -> None:
        view = self.view
        if view is not None:
            view.zoom_in()

    def _zoom_out(self) -> None:
        view = self.view
        if view is not None:
            view.zoom_out()

    def _fit_width(self) -> None:
        view = self.view
        if view is not None:
            view.fit_width()

    def _fit_page(self) -> None:
        view = self.view
        if view is not None:
            view.fit_page()

    def _clear_selection(self) -> None:
        view = self.view
        if view is not None:
            view.clear_selection()

    # ------------------------------------------------------------- 翻译
    def _on_selection(self, text: str) -> None:
        if not text.strip():
            return
        self.panel.set_original(text)
        if self.config.auto_translate:
            self.start_translate(text, kind="selection")
        else:
            self.panel.set_status("已选中，Ctrl+Shift+T 翻译", "info")

    def translate_selection(self) -> None:
        view = self.view
        text = view.selected_text().strip() if view is not None else ""
        if not text:
            self.panel.set_status("先在 PDF 里划选一段文字", "error")
            return
        self.start_translate(text, kind="selection")

    def translate_page(self) -> None:
        view = self.view
        if view is None or view.doc is None:
            self.panel.set_status("先打开一个 PDF", "error")
            return
        page = view.current_page()
        text = view.doc.page_text_for_translation(page)
        if not text.strip():
            self.panel.set_status("这一页没有文字层（可能是扫描件）", "error")
            return
        self.start_translate(text, kind="page")

    def translate_clipboard(self) -> None:
        text = QGuiApplication.clipboard().text().strip()
        if not text:
            self.panel.set_status("剪贴板是空的", "error")
            return
        self.start_translate(text, kind="clipboard")

    def start_translate(self, text: str, kind: str = "selection") -> None:
        text = (text or "").strip()
        if not text:
            self.panel.set_status("没有可翻译的内容", "error")
            return
        if kind != "retry":
            self.panel.set_original(text)

        self._cancel_tasks()
        src = self.config.source_lang
        dst = self.config.target_lang
        try:
            engine = make_engine(self.config)
        except TranslateError as e:
            self.panel.fail(str(e))
            return

        self.panel.begin(f"{engine.label} 翻译中…")
        self.panel.set_status(f"{engine.label} · {len(text)} 字符", "busy")

        cache = self.cache if self.config.cache_enabled else None
        task = TranslateTask(engine, text, src, dst, cache, self)
        task.delta.connect(self.panel.append_delta)
        task.done.connect(self._on_task_done)
        task.error.connect(self._on_task_error)
        task.finished.connect(lambda t=task: self._retire_task(t))
        self._tasks.append(task)
        task.start()

    def _on_task_done(self, text: str, cached: bool) -> None:
        self.panel.finish(text, cached)
        note = "完成（来自缓存）" if cached else f"完成 · {len(text)} 字符"
        self.panel.set_status(note, "ok")

    def _on_task_error(self, message: str) -> None:
        self.panel.fail(message)
        self.statusBar().showMessage(message, 8000)

    def _retire_task(self, task: TranslateTask) -> None:
        if task in self._tasks:
            self._tasks.remove(task)
        task.deleteLater()

    def _cancel_tasks(self) -> None:
        for task in list(self._tasks):
            task.cancel()

    # ------------------------------------------------------------- 通道
    def _set_channel(self, engine_id: str) -> None:
        self.config.engine = engine_id
        action = self._channel_actions.get(engine_id)
        if action is not None and not action.isChecked():
            action.setChecked(True)
        self.panel.blockSignals(True)
        idx = self.panel.channel.findData(engine_id)
        if idx >= 0:
            self.panel.channel.setCurrentIndex(idx)
        self.panel.blockSignals(False)
        save_config(self.config)
        self._refresh_status()

    def _on_channel_changed(self, engine_id: str) -> None:
        if not engine_id or engine_id == self.config.engine:
            return
        self._set_channel(engine_id)

    # ------------------------------------------------------------- 主题
    def _apply_theme(self, key: str) -> None:
        if key not in THEMES:
            key = "day"
        self.config.theme = key
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(make_qss(key))
        self.panel.set_theme(key)
        for view in self._all_views():
            view.setBackgroundBrush(QColor(THEMES[key]["view_bg"]))
        for k, action in self._theme_actions.items():
            action.setChecked(k == key)

    def _all_views(self) -> list[PdfView]:
        return [
            self.tabs.widget(i)
            for i in range(self.tabs.count())
            if isinstance(self.tabs.widget(i), PdfView)
        ]

    # ------------------------------------------------------------- 设置
    def open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self.cache, self)
        if dialog.exec():
            new_cfg = dialog.cfg
            self.config = new_cfg
            self.cache.enabled = bool(new_cfg.cache_enabled)
            for view in self._all_views():
                view.click_mode = new_cfg.click_mode
            self._apply_theme(new_cfg.theme)
            self.panel.set_language_labels(new_cfg.source_lang, new_cfg.target_lang)
            self._set_channel(new_cfg.engine)
            save_config(self.config)
            self._refresh_status()

    def _export_settings(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出设置", str(Path.home() / "pdftrans-settings.json"), "JSON (*.json)"
        )
        if not path:
            return
        try:
            export_config(self.config, path)
            self.statusBar().showMessage(f"已导出到 {path}", 5000)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "导出失败", str(e))

    def _import_settings(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入设置", str(Path.home()), "JSON (*.json);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            cfg = import_config(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "导入失败", str(e))
            return
        self.config = cfg
        for view in self._all_views():
            view.click_mode = cfg.click_mode
        self.panel.set_channels(
            [(eid, label) for eid, label in ENGINE_LABELS.items()], cfg.engine
        )
        self.panel.set_language_labels(cfg.source_lang, cfg.target_lang)
        self._apply_theme(cfg.theme)
        save_config(cfg)
        self.statusBar().showMessage("设置已导入", 4000)
        self._refresh_status()

    # ------------------------------------------------------------- 帮助
    def _show_help(self) -> None:
        QMessageBox.information(
            self,
            "使用说明",
            "<b>多标签</b><br>"
            "• Ctrl+O 可一次选多个 PDF，每个开一个标签<br>"
            "• 把 PDF 拖进窗口也可以（支持一次拖多个）<br>"
            "• Ctrl+Tab / Ctrl+Shift+Tab 切标签，Ctrl+W 关当前标签<br><br>"
            "<b>阅读与取词</b><br>"
            "• 单击一段 → 翻整句（可在设置里改成整行 / 整段）<br>"
            "• 按住拖动 → 翻任意片段，可跨行跨页<br>"
            "• 双击 → 翻整段<br><br>"
            "<b>快捷键</b><br>"
            "• Ctrl+Shift+T 翻译选区<br>"
            "• Ctrl+Enter 翻译当前整页<br>"
            "• Ctrl+Shift+V 翻译剪贴板<br>"
            "• Ctrl+滚轮 缩放，Ctrl+0 适应宽度<br>"
            "• PageUp / PageDown 翻页，Esc 清除选区<br><br>"
            "<b>通道</b><br>"
            "Google / Bing 免 key 可直接用；百度、有道、DeepL 需在设置里填 key；"
            "AI 通道填任意 OpenAI 兼容的 Base URL + Key + 模型名即可。",
        )

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于",
            "<h3>PDF 论文翻译</h3>"
            "<p>多标签连续阅读 PDF，"
            "划词即译，右侧流式显示。</p>"
            "<p>通道：Google / Bing 免费通道，百度 / 有道 / DeepL 官方 API，"
            "以及任意 OpenAI 兼容大模型。</p>"
            "<p>基于 PySide6 + PyMuPDF 构建，MIT 许可开源。</p>",
        )

    # ------------------------------------------------------------- 拖放
    @staticmethod
    def _pdfs_from_mime(mime) -> list[str]:
        if not mime.hasUrls():
            return []
        return [
            url.toLocalFile()
            for url in mime.urls()
            if url.toLocalFile().lower().endswith(".pdf")
        ]

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._pdfs_from_mime(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if self._pdfs_from_mime(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = self._pdfs_from_mime(event.mimeData())
        if paths:
            event.setDropAction(Qt.CopyAction)
            event.accept()
            self._open_paths(paths)
        else:
            event.ignore()

    # ------------------------------------------------------------- 生命周期
    def _restore_window(self) -> None:
        if self.config.window_geometry:
            try:
                self.restoreGeometry(QByteArray.fromBase64(self.config.window_geometry.encode()))
            except Exception:
                pass
        if self.config.splitter_state:
            try:
                self.splitter.restoreState(
                    QByteArray.fromBase64(self.config.splitter_state.encode())
                )
            except Exception:
                pass

    def closeEvent(self, event) -> None:  # noqa: N802
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            task.wait(2500)
        try:
            self.config.window_geometry = bytes(self.saveGeometry().toBase64()).decode()
            self.config.splitter_state = bytes(self.splitter.saveState().toBase64()).decode()
            view = self.view
            if view is not None:
                self.config.zoom = view.zoom
            save_config(self.config)
        except Exception:
            pass
        for view in self._all_views():
            view.close_doc()
        super().closeEvent(event)
