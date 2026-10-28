"""设置对话框：通道、语向、交互、缓存、AI 参数。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..cache import TranslationCache
from ..config import (
    AI_PRESET_ORDER,
    AI_PRESETS,
    DEFAULT_PROMPT,
    ENGINE_LABELS,
    AppConfig,
)
from ..engines import make_engine

LANGS = [
    ("auto", "自动识别"),
    ("en", "英文"),
    ("zh-CN", "中文"),
    ("ja", "日文"),
    ("ko", "韩文"),
    ("de", "德文"),
    ("fr", "法文"),
    ("ru", "俄文"),
    ("es", "西班牙文"),
]

TARGET_LANGS = [x for x in LANGS if x[0] != "auto"]


class _TestWorker(QObject):
    done = Signal(bool, str)

    def __init__(self, cfg: AppConfig, text: str):
        super().__init__()
        self.cfg = cfg
        self.text = text

    def run(self) -> None:
        engine = None
        try:
            engine = make_engine(self.cfg, self.cfg.engine)
            out = engine.translate(self.text, "en", self.cfg.target_lang)
            self.done.emit(True, out)
        except Exception as e:  # noqa: BLE001
            self.done.emit(False, str(e))
        finally:
            if engine is not None:
                try:
                    engine.close()
                except Exception:
                    pass


class SettingsDialog(QDialog):
    def __init__(self, cfg: AppConfig, cache: TranslationCache | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(760, 640)
        self.cfg = AppConfig.from_json(cfg.to_json())
        self.cache = cache
        self._thread: QThread | None = None
        self._worker: _TestWorker | None = None

        tabs = QTabWidget()
        tabs.addTab(self._build_general(), "通用")
        tabs.addTab(self._build_vendor(), "在线引擎")
        tabs.addTab(self._build_ai(), "AI 大模型")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.addWidget(tabs, 1)
        root.addWidget(buttons)

        self._load()

    # ------------------------------------------------------------- 页面
    def _build_general(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(10)

        self.cb_engine = QComboBox()
        for eid, label in ENGINE_LABELS.items():
            self.cb_engine.addItem(label, eid)
        form.addRow("默认通道", self.cb_engine)

        self.cb_src = QComboBox()
        for code, label in LANGS:
            self.cb_src.addItem(label, code)
        self.cb_dst = QComboBox()
        for code, label in TARGET_LANGS:
            self.cb_dst.addItem(label, code)
        lang_row = QHBoxLayout()
        lang_row.addWidget(self.cb_src, 1)
        lang_row.addWidget(QLabel("→"))
        lang_row.addWidget(self.cb_dst, 1)
        form.addRow("语向", lang_row)

        self.cb_click = QComboBox()
        self.cb_click.addItem("整句（推荐）", "sentence")
        self.cb_click.addItem("整行", "line")
        self.cb_click.addItem("整段", "paragraph")
        form.addRow("单击取词粒度", self.cb_click)

        self.cb_theme = QComboBox()
        self.cb_theme.addItem("默认", "day")
        self.cb_theme.addItem("护眼", "eye")
        self.cb_theme.addItem("夜间", "night")
        form.addRow("界面主题", self.cb_theme)

        self.chk_auto = QCheckBox("划选后自动翻译")
        form.addRow("", self.chk_auto)

        self.chk_cache = QCheckBox("启用本地翻译缓存（重复段落不再请求）")
        form.addRow("", self.chk_cache)

        cache_row = QHBoxLayout()
        self.lbl_cache = QLabel("")
        btn_clear = QPushButton("清空缓存")
        btn_clear.clicked.connect(self._clear_cache)
        cache_row.addWidget(self.lbl_cache, 1)
        cache_row.addWidget(btn_clear)
        form.addRow("缓存", cache_row)

        self.sp_zoom = QDoubleSpinBox()
        self.sp_zoom.setRange(0.35, 4.5)
        self.sp_zoom.setSingleStep(0.05)
        self.sp_zoom.setDecimals(2)
        form.addRow("默认缩放", self.sp_zoom)

        form.addRow(QLabel(""))
        tip = QLabel(
            "提示：在 PDF 上单击翻整句、拖动翻任意片段、双击翻整段；\n"
            "Ctrl+Enter 翻整页，Ctrl+Shift+V 翻译剪贴板内容。"
        )
        tip.setObjectName("dim")
        form.addRow(tip)
        return page

    def _build_vendor(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        g_baidu = QGroupBox("百度翻译（通用文本翻译 API）")
        f1 = QFormLayout(g_baidu)
        self.ed_baidu_id = QLineEdit()
        self.ed_baidu_key = QLineEdit()
        self.ed_baidu_key.setEchoMode(QLineEdit.Password)
        f1.addRow("APPID", self.ed_baidu_id)
        f1.addRow("密钥", self.ed_baidu_key)

        g_youdao = QGroupBox("有道智云")
        f2 = QFormLayout(g_youdao)
        self.ed_youdao_id = QLineEdit()
        self.ed_youdao_key = QLineEdit()
        self.ed_youdao_key.setEchoMode(QLineEdit.Password)
        f2.addRow("应用 ID", self.ed_youdao_id)
        f2.addRow("应用密钥", self.ed_youdao_key)

        g_deepl = QGroupBox("DeepL")
        f3 = QFormLayout(g_deepl)
        self.ed_deepl_key = QLineEdit()
        self.ed_deepl_key.setEchoMode(QLineEdit.Password)
        self.chk_deepl_free = QCheckBox("使用免费版端点（api-free.deepl.com）")
        self.ed_deepl_url = QLineEdit()
        self.ed_deepl_url.setPlaceholderText("留空则用官方端点；可填自建代理地址")
        f3.addRow("Auth Key", self.ed_deepl_key)
        f3.addRow("", self.chk_deepl_free)
        f3.addRow("自定义端点", self.ed_deepl_url)

        root.addWidget(g_baidu)
        root.addWidget(g_youdao)
        root.addWidget(g_deepl)
        root.addStretch(1)
        return page

    def _build_ai(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        preset_row = QHBoxLayout()
        self.cb_preset = QComboBox()
        for key in AI_PRESET_ORDER:
            self.cb_preset.addItem(AI_PRESETS[key]["label"], key)
        btn_apply = QPushButton("套用预设")
        btn_apply.clicked.connect(self._apply_preset)
        preset_row.addWidget(QLabel("服务商"))
        preset_row.addWidget(self.cb_preset, 1)
        preset_row.addWidget(btn_apply)
        root.addLayout(preset_row)

        form = QFormLayout()
        form.setSpacing(8)
        self.ed_base = QLineEdit()
        self.ed_base.setPlaceholderText("https://api.deepseek.com/v1")
        self.ed_key = QLineEdit()
        self.ed_key.setEchoMode(QLineEdit.Password)
        self.ed_key.setPlaceholderText("sk-...")
        self.ed_model = QLineEdit()
        self.ed_model.setPlaceholderText("deepseek-chat")

        self.sp_temp = QDoubleSpinBox()
        self.sp_temp.setRange(0.0, 2.0)
        self.sp_temp.setSingleStep(0.1)
        self.sp_temp.setDecimals(1)

        self.ed_extra = QPlainTextEdit()
        self.ed_extra.setPlaceholderText('透传给接口的额外 JSON，例如 {"enable_thinking": false}')
        self.ed_extra.setMaximumHeight(64)

        form.addRow("Base URL", self.ed_base)
        form.addRow("API Key", self.ed_key)
        form.addRow("模型", self.ed_model)
        form.addRow("temperature", self.sp_temp)
        form.addRow("额外参数", self.ed_extra)
        root.addLayout(form)

        root.addWidget(QLabel("系统提示词（{src} / {dst} 会被替换）"))
        self.ed_prompt = QPlainTextEdit()
        self.ed_prompt.setPlaceholderText(DEFAULT_PROMPT)
        root.addWidget(self.ed_prompt, 1)

        test_row = QHBoxLayout()
        self.btn_test = QPushButton("测试当前通道")
        self.btn_test.clicked.connect(self._test)
        self.lbl_test = QLabel("")
        self.lbl_test.setWordWrap(True)
        test_row.addWidget(self.btn_test)
        test_row.addWidget(self.lbl_test, 1)
        root.addLayout(test_row)
        return page

    # ------------------------------------------------------------- 读写
    def _load(self) -> None:
        cfg = self.cfg
        idx = self.cb_engine.findData(cfg.engine)
        if idx >= 0:
            self.cb_engine.setCurrentIndex(idx)
        self.cb_src.setCurrentIndex(max(0, self.cb_src.findData(cfg.source_lang)))
        self.cb_dst.setCurrentIndex(max(0, self.cb_dst.findData(cfg.target_lang)))
        self.cb_click.setCurrentIndex(max(0, self.cb_click.findData(cfg.click_mode)))
        self.cb_theme.setCurrentIndex(max(0, self.cb_theme.findData(cfg.theme)))
        self.chk_auto.setChecked(cfg.auto_translate)
        self.chk_cache.setChecked(cfg.cache_enabled)
        self.sp_zoom.setValue(cfg.zoom)
        self._update_cache_label()

        baidu = cfg.engine_config("baidu")
        self.ed_baidu_id.setText(baidu.appid)
        self.ed_baidu_key.setText(baidu.secret)

        youdao = cfg.engine_config("youdao")
        self.ed_youdao_id.setText(youdao.appid)
        self.ed_youdao_key.setText(youdao.secret)

        deepl = cfg.engine_config("deepl")
        self.ed_deepl_key.setText(deepl.auth_key)
        self.chk_deepl_free.setChecked(deepl.use_free_deepl)
        self.ed_deepl_url.setText(deepl.base_url)

        ai = cfg.ai
        self.ed_base.setText(ai.base_url)
        self.ed_key.setText(ai.api_key)
        self.ed_model.setText(ai.model)
        self.sp_temp.setValue(float(ai.temperature or 0.2))
        self.ed_extra.setPlainText(ai.extra_body)
        self.ed_prompt.setPlainText(cfg.prompt or DEFAULT_PROMPT)
        pidx = self.cb_preset.findData(ai.preset)
        if pidx >= 0:
            self.cb_preset.setCurrentIndex(pidx)

    def _collect(self) -> None:
        cfg = self.cfg
        cfg.engine = self.cb_engine.currentData() or "google_free"
        cfg.source_lang = self.cb_src.currentData() or "auto"
        cfg.target_lang = self.cb_dst.currentData() or "zh-CN"
        cfg.click_mode = self.cb_click.currentData() or "sentence"
        cfg.theme = self.cb_theme.currentData() or "day"
        cfg.auto_translate = self.chk_auto.isChecked()
        cfg.cache_enabled = self.chk_cache.isChecked()
        cfg.zoom = float(self.sp_zoom.value())

        baidu = cfg.engine_config("baidu")
        baidu.appid = self.ed_baidu_id.text().strip()
        baidu.secret = self.ed_baidu_key.text().strip()

        youdao = cfg.engine_config("youdao")
        youdao.appid = self.ed_youdao_id.text().strip()
        youdao.secret = self.ed_youdao_key.text().strip()

        deepl = cfg.engine_config("deepl")
        deepl.auth_key = self.ed_deepl_key.text().strip()
        deepl.use_free_deepl = self.chk_deepl_free.isChecked()
        deepl.base_url = self.ed_deepl_url.text().strip()

        ai = cfg.ai
        ai.base_url = self.ed_base.text().strip()
        ai.api_key = self.ed_key.text().strip()
        ai.model = self.ed_model.text().strip()
        ai.temperature = float(self.sp_temp.value())
        ai.extra_body = self.ed_extra.toPlainText().strip()
        ai.preset = self.cb_preset.currentData() or "custom"
        cfg.prompt = self.ed_prompt.toPlainText().strip() or DEFAULT_PROMPT

    def accept(self) -> None:  # noqa: D102
        self._collect()
        super().accept()

    # ------------------------------------------------------------- 动作
    def _apply_preset(self) -> None:
        key = self.cb_preset.currentData()
        preset = AI_PRESETS.get(str(key))
        if not preset:
            return
        if preset["base_url"]:
            self.ed_base.setText(preset["base_url"])
        if preset["model"]:
            self.ed_model.setText(preset["model"])

    def _update_cache_label(self) -> None:
        if self.cache is None:
            self.lbl_cache.setText("缓存不可用")
            return
        self.lbl_cache.setText(f"已缓存 {self.cache.count()} 条")

    def _clear_cache(self) -> None:
        if self.cache is None:
            return
        if QMessageBox.question(self, "清空缓存", "确定要清空全部翻译缓存吗？") == QMessageBox.Yes:
            self.cache.clear()
            self._update_cache_label()

    def _test(self) -> None:
        self._collect()
        if self.cfg.engine not in ("google_free", "bing_free"):
            self._test_channel(self.cfg.engine)
        else:
            self._test_channel(self.cfg.engine)

    def _test_channel(self, engine_id: str) -> None:
        self.btn_test.setEnabled(False)
        self.lbl_test.setText("测试中…")

        test_cfg = AppConfig.from_json(self.cfg.to_json())
        test_cfg.engine = engine_id
        self._thread = QThread(self)
        self._worker = _TestWorker(test_cfg, "Photosynthesis converts light energy into chemical energy.")
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._on_test_done)
        self._thread.start()

    def _on_test_done(self, ok: bool, message: str) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(1500)
            self._thread = None
        self._worker = None
        self.btn_test.setEnabled(True)
        if ok:
            self.lbl_test.setText(f"✅ {message[:180]}")
            self.lbl_test.setStyleSheet("color:#2e7d32;")
        else:
            self.lbl_test.setText(f"❌ {message[:220]}")
            self.lbl_test.setStyleSheet("color:#c0392b;")
