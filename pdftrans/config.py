"""配置层：翻译通道、语向、主题、缓存与设置导入导出。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

APP_NAME = "PDFTrans"

# ---------------------------------------------------------------- 引擎目录

#: 免费通道（无需 key），开箱可用
FREE_ENGINES = ("google_free", "bing_free")

#: 需要厂商 key 的传统在线翻译
KEY_ENGINES = ("baidu", "youdao", "deepl")

#: OpenAI 兼容的 AI 通道，预设只负责填 base_url / model
AI_PRESETS: dict[str, dict[str, str]] = {
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "qwen": {
        "label": "阿里千问 (DashScope)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "kimi": {
        "label": "Kimi (Moonshot)",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    "glm": {
        "label": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
    "siliconflow": {
        "label": "硅基流动",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen2.5-7B-Instruct",
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4o-mini",
    },
    "ollama": {
        "label": "本地 Ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "qwen2.5:7b",
    },
    "custom": {
        "label": "自定义 (手填)",
        "base_url": "",
        "model": "",
    },
}

AI_PRESET_ORDER = list(AI_PRESETS)

ENGINE_LABELS: dict[str, str] = {
    "google_free": "Google 免费通道",
    "bing_free": "Bing 免费通道",
    "baidu": "百度翻译 (需 appid)",
    "youdao": "有道智云 (需 appKey)",
    "deepl": "DeepL (需 auth key)",
    "ai": "AI 大模型 (OpenAI 兼容)",
}

DEFAULT_PROMPT = (
    "你是一位专业的学术文献翻译引擎，精通{src}与{dst}互译，熟悉各学科术语。\n"
    "规则：\n"
    "1. 忠实传达原文信息，不增删、不解释、不总结、不评论；\n"
    "2. 术语采用领域内通用译法，必要时首次出现可在括号内保留英文原词；\n"
    "3. 数字、单位、公式、基因/蛋白名称、缩写与引用标记（如 [12]、(Fig. 1)）保持原样；\n"
    "4. 保留原文的换行与段结构；\n"
    "5. 只输出译文本身，不要任何前言、注释、译注或 Markdown 代码块标记。"
)


def app_root() -> Path:
    """程序所在目录：打包后是 exe 同目录，源码运行时是项目根。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _is_writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


_DATA_DIR: Path | None = None


def config_dir() -> Path:
    """数据目录：优先 %APPDATA%，不可写则退回程序旁边的 data（便携模式）。

    有些环境下未签名的 exe 写不了 %APPDATA% / %TEMP%，这里做一次可写探测，
    保证配置与缓存永远有地方落。
    """
    global _DATA_DIR
    if _DATA_DIR is not None:
        return _DATA_DIR

    candidates: list[Path] = []
    override = os.environ.get("PDFTRANS_DATA_DIR")
    if override:
        candidates.append(Path(override))
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            candidates.append(Path(base) / APP_NAME)
        candidates.append(Path.home() / "AppData" / "Roaming" / APP_NAME)
    elif sys.platform == "darwin":
        candidates.append(Path.home() / "Library" / "Application Support" / APP_NAME)
    else:
        candidates.append(
            Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / APP_NAME
        )
    try:
        candidates.append(app_root() / "data")
    except Exception:
        pass
    candidates.append(Path(tempfile.gettempdir()) / APP_NAME)

    for candidate in candidates:
        if _is_writable(candidate):
            _DATA_DIR = candidate
            return candidate

    _DATA_DIR = candidates[0]
    return _DATA_DIR



def config_path() -> Path:
    return config_dir() / "config.json"


# ---------------------------------------------------------------- 数据结构


@dataclass
class EngineConfig:
    """单引擎参数。AI 通道复用 base_url / api_key / model。"""

    appid: str = ""
    secret: str = ""
    auth_key: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    extra_body: str = ""          # JSON 文本，透传给 /chat/completions
    temperature: float = 0.2
    use_free_deepl: bool = True
    preset: str = "deepseek"      # 当前选中的 AI 预设

    def clone(self) -> "EngineConfig":
        return EngineConfig(**asdict(self))


@dataclass
class AppConfig:
    # 引擎
    engine: str = "google_free"
    engines: dict[str, EngineConfig] = field(default_factory=dict)
    prompt: str = DEFAULT_PROMPT

    # 语向
    source_lang: str = "auto"
    target_lang: str = "zh-CN"

    # 交互
    auto_translate: bool = True     # 划词后自动翻译
    click_mode: str = "sentence"    # line / sentence / paragraph
    keep_original: bool = True      # 面板保留原文

    # 外观
    theme: str = "day"              # day / eye / night
    zoom: float = 1.2

    # 窗口
    window_geometry: str = ""
    splitter_state: str = ""

    # 缓存
    cache_enabled: bool = True
    cache_limit: int = 20000

    # 杂项
    recent_files: list[str] = field(default_factory=list)
    last_dir: str = ""

    # ------------------------------------------------ 访问器
    def engine_config(self, engine_id: str) -> EngineConfig:
        ec = self.engines.get(engine_id)
        if ec is None:
            ec = EngineConfig()
            if engine_id in AI_PRESETS:
                p = AI_PRESETS[engine_id]
                ec.base_url = p["base_url"]
                ec.model = p["model"]
                ec.preset = engine_id
            self.engines[engine_id] = ec
        # AI 通道：老配置或空值时补上预设骨架，方便直接改成自己的 key
        if engine_id == "ai" and not ec.base_url.strip():
            p = AI_PRESETS.get(ec.preset) or AI_PRESETS["deepseek"]
            ec.base_url = p["base_url"]
            if not ec.model.strip():
                ec.model = p["model"]
        return ec

    @property
    def ai(self) -> EngineConfig:
        return self.engine_config("ai")

    # ------------------------------------------------ 序列化
    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("engines", None)
        d["engines"] = {k: asdict(v) for k, v in self.engines.items()}
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "AppConfig":
        d = dict(d or {})
        raw_engines = d.pop("engines", {}) or {}
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        base = {k: v for k, v in d.items() if k in known and k != "engines"}
        cfg = cls(**base)
        for k, v in raw_engines.items():
            if isinstance(v, dict):
                valid = {f for f in EngineConfig.__dataclass_fields__}  # type: ignore[attr-defined]
                cfg.engines[k] = EngineConfig(**{kk: vv for kk, vv in v.items() if kk in valid})
        return cfg


# ---------------------------------------------------------------- 读写


def load_config() -> AppConfig:
    p = config_path()
    if p.exists():
        try:
            return AppConfig.from_json(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    cfg = AppConfig()
    # 预置 AI 预设，方便用户在设置里直接切
    for key in AI_PRESET_ORDER:
        cfg.engine_config(key)
    # AI 通道给一个能直接改 key 的默认骨架
    ai = cfg.engine_config("ai")
    if not ai.base_url:
        ai.base_url = AI_PRESETS["deepseek"]["base_url"]
        ai.model = AI_PRESETS["deepseek"]["model"]
    return cfg


def save_config(cfg: AppConfig) -> None:
    p = config_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def export_config(cfg: AppConfig, path: str) -> None:
    Path(path).write_text(json.dumps(cfg.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")


def import_config(path: str) -> AppConfig:
    return AppConfig.from_json(json.loads(Path(path).read_text(encoding="utf-8")))
