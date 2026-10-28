"""三套界面配色：默认 / 护眼 / 夜间。"""

from __future__ import annotations

THEMES: dict[str, dict[str, str]] = {
    "day": {
        "name": "默认",
        "bg": "#f2f3f5",
        "surface": "#ffffff",
        "surface_alt": "#f7f8fa",
        "border": "#dcdfe4",
        "text": "#1f2329",
        "text_dim": "#6b7280",
        "accent": "#2f6fed",
        "accent_text": "#ffffff",
        "sel": "#d7e5ff",
        "view_bg": "#5b6068",
        "danger": "#c0392b",
        "ok": "#2e7d32",
    },
    "eye": {
        "name": "护眼",
        "bg": "#dfeee0",
        "surface": "#f2f8e9",
        "surface_alt": "#e6f2e1",
        "border": "#c3d8bd",
        "text": "#233322",
        "text_dim": "#5a6b57",
        "accent": "#3f7a4a",
        "accent_text": "#ffffff",
        "sel": "#cfe6c9",
        "view_bg": "#87907e",
        "danger": "#a3402f",
        "ok": "#2f6b3a",
    },
    "night": {
        "name": "夜间",
        "bg": "#1b1d21",
        "surface": "#24262b",
        "surface_alt": "#2c2f35",
        "border": "#3a3e46",
        "text": "#d8dbe0",
        "text_dim": "#8b919c",
        "accent": "#4b8cff",
        "accent_text": "#ffffff",
        "sel": "#33415c",
        "view_bg": "#111214",
        "danger": "#e2725b",
        "ok": "#5cb85c",
    },
}

THEME_ORDER = ["day", "eye", "night"]


def theme_name(key: str) -> str:
    return THEMES.get(key, THEMES["day"])["name"]


def make_qss(key: str) -> str:
    t = THEMES.get(key, THEMES["day"])
    return f"""
    QWidget {{
        background: {t['bg']};
        color: {t['text']};
        font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
        font-size: 13px;
    }}
    QMainWindow, QDialog {{ background: {t['bg']}; }}

    QMenuBar {{ background: {t['surface']}; border-bottom: 1px solid {t['border']}; }}
    QMenuBar::item {{ padding: 4px 10px; background: transparent; }}
    QMenuBar::item:selected {{ background: {t['sel']}; border-radius: 4px; }}
    QMenu {{ background: {t['surface']}; border: 1px solid {t['border']}; padding: 4px; }}
    QMenu::item {{ padding: 5px 26px 5px 22px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {t['sel']}; }}
    QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 8px; }}

    QToolBar {{ background: {t['surface']}; border-bottom: 1px solid {t['border']}; spacing: 4px; padding: 3px; }}

    QPlainTextEdit, QTextEdit, QTextBrowser, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {t['surface']};
        border: 1px solid {t['border']};
        border-radius: 5px;
        padding: 4px 6px;
        selection-background-color: {t['accent']};
        selection-color: {t['accent_text']};
    }}
    QPlainTextEdit:focus, QLineEdit:focus, QComboBox:focus {{ border: 1px solid {t['accent']}; }}
    QComboBox::drop-down {{ border: 0; width: 18px; }}
    QComboBox QAbstractItemView {{
        background: {t['surface']};
        border: 1px solid {t['border']};
        selection-background-color: {t['sel']};
        selection-color: {t['text']};
        outline: 0;
    }}

    QPushButton {{
        background: {t['surface_alt']};
        border: 1px solid {t['border']};
        border-radius: 5px;
        padding: 5px 12px;
    }}
    QPushButton:hover {{ background: {t['sel']}; }}
    QPushButton:pressed {{ background: {t['border']}; }}
    QPushButton#primary {{
        background: {t['accent']};
        color: {t['accent_text']};
        border: 1px solid {t['accent']};
    }}
    QPushButton#primary:hover {{ background: {t['accent']}; }}
    QPushButton:disabled {{ color: {t['text_dim']}; }}

    QCheckBox, QRadioButton {{ spacing: 6px; background: transparent; }}
    QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {t['border']}; border-radius: 3px; background: {t['surface']}; }}
    QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; }}

    QLabel {{ background: transparent; }}
    QLabel#dim {{ color: {t['text_dim']}; }}

    QTabWidget::pane {{ border: 1px solid {t['border']}; border-radius: 6px; background: {t['surface']}; }}
    QTabBar::tab {{ padding: 6px 16px; border: 1px solid transparent; border-top-left-radius: 5px; border-top-right-radius: 5px; }}
    QTabBar::tab:selected {{ background: {t['surface']}; border-color: {t['border']}; border-bottom-color: {t['surface']}; }}
    QTabBar::tab:!selected {{ color: {t['text_dim']}; }}

    QGroupBox {{
        border: 1px solid {t['border']};
        border-radius: 6px;
        margin-top: 10px;
        padding-top: 8px;
        background: {t['surface']};
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {t['text_dim']}; }}

    QSplitter::handle {{ background: {t['border']}; }}
    QSplitter::handle:horizontal {{ width: 1px; }}
    QSplitter::handle:vertical {{ height: 1px; }}

    QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {t['border']}; min-height: 30px; border-radius: 5px; }}
    QScrollBar::handle:vertical:hover {{ background: {t['text_dim']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {t['border']}; min-width: 30px; border-radius: 5px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    QStatusBar {{ background: {t['surface']}; border-top: 1px solid {t['border']}; color: {t['text_dim']}; }}
    QStatusBar::item {{ border: 0; }}

    QToolTip {{ background: {t['surface']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 4px; }}

    QListWidget {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 5px; }}
    QListWidget::item {{ padding: 4px 6px; }}
    QListWidget::item:selected {{ background: {t['sel']}; color: {t['text']}; }}
    """
