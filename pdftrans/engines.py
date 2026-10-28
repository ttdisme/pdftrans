"""翻译引擎集合。

三类通道：
  * 免费通道   —— Google / Bing 的免 key 接口（适合随手翻）
  * 厂商 key   —— 百度、有道、DeepL 的官方 API
  * AI 大模型 —— 任意 OpenAI 兼容端点（DeepSeek / 千问 / Kimi / 智谱 /
                 硅基流动 / OpenRouter / 本地 Ollama …），支持流式输出

所有引擎统一接口：
  translate(text, src, dst) -> str
  stream(text, src, dst)    -> Iterator[str]   （仅 AI 通道真正流式）
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import threading
import time
from typing import Iterator

import requests

from .config import AppConfig, EngineConfig


class TranslateError(RuntimeError):
    """翻译失败，消息直接展示给用户。"""


# ---------------------------------------------------------------- 工具


def chunk_text(text: str, limit: int) -> list[str]:
    """按段落 → 句子 → 硬切，尽量不切断语义。"""
    text = text.strip("\n")
    if len(text) <= limit:
        return [text] if text.strip() else []

    out: list[str] = []
    buf = ""
    for para in re.split(r"(?<=\n)", text):
        if len(buf) + len(para) <= limit:
            buf += para
            continue
        if buf:
            out.append(buf)
            buf = ""
        if len(para) <= limit:
            buf = para
            continue
        for sent in re.split(r"(?<=[.!?。！？；;])\s*", para):
            if not sent:
                continue
            if len(buf) + len(sent) <= limit:
                buf += sent
                continue
            if buf:
                out.append(buf)
                buf = ""
            while len(sent) > limit:
                out.append(sent[:limit])
                sent = sent[limit:]
            buf = sent
    if buf:
        out.append(buf)
    return [c for c in out if c.strip()]


def lang_google(code: str) -> str:
    return {"zh": "zh-CN", "zh-CN": "zh-CN"}.get(code, code)


def lang_baidu(code: str) -> str:
    return {"zh-CN": "zh", "zh": "zh"}.get(code, code)


def lang_youdao(code: str) -> str:
    return {"zh-CN": "zh-CHS", "zh": "zh-CHS"}.get(code, code)


def lang_deepl(code: str) -> str | None:
    if code == "auto":
        return None
    return {"zh-CN": "ZH", "zh": "ZH", "en": "EN", "ja": "JA", "ko": "KO"}.get(code, code.upper())


def lang_bing(code: str) -> str | None:
    if code == "auto":
        return None
    return {"zh-CN": "zh-Hans", "zh": "zh-Hans", "en": "en"}.get(code, code)


def lang_human(code: str) -> str:
    return {
        "auto": "自动识别",
        "zh-CN": "中文",
        "zh": "中文",
        "en": "英文",
        "ja": "日文",
        "ko": "韩文",
        "de": "德文",
        "fr": "法文",
        "ru": "俄文",
        "es": "西班牙文",
    }.get(code, code)


# ---------------------------------------------------------------- 基类


class Engine:
    id = "base"
    label = "base"
    supports_stream = False

    def __init__(self, cfg: EngineConfig, app: AppConfig):
        self.cfg = cfg
        self.app = app
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": _UA})

    # -- 子类实现
    def translate(self, text: str, src: str, dst: str) -> str:
        raise NotImplementedError

    def stream(self, text: str, src: str, dst: str) -> Iterator[str]:
        yield self.translate(text, src, dst)

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass

    # -- 便捷
    def _post_json(self, url: str, payload: dict, timeout: int = 30, headers: dict | None = None) -> dict:
        try:
            r = self.session.post(url, json=payload, timeout=timeout, headers=headers)
        except requests.RequestException as e:
            raise TranslateError(f"网络请求失败：{e}") from e
        return _json_or_raise(r)


_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _json_or_raise(r: requests.Response) -> dict:
    if r.status_code == 429:
        raise TranslateError("请求过于频繁（429），稍后再试或换通道")
    if r.status_code >= 400:
        snippet = (r.text or "")[:300]
        raise TranslateError(f"HTTP {r.status_code}：{snippet}")
    try:
        return r.json()
    except ValueError as e:
        raise TranslateError(f"返回内容不是 JSON：{(r.text or '')[:200]}") from e


def _parse_bing(payload) -> str:
    item = None
    if isinstance(payload, list) and payload:
        item = payload[0]
    elif isinstance(payload, dict):
        item = payload
    if not isinstance(item, dict):
        raise TranslateError("Bing 返回结构异常")
    rows = item.get("translations") or []
    if not rows:
        raise TranslateError(f"Bing 返回异常：{json.dumps(payload, ensure_ascii=False)[:200]}")
    return str(rows[0].get("text", "")).strip()


# ---------------------------------------------------------------- 免费通道


class GoogleFreeEngine(Engine):
    """translate_a/single 免 key 接口。"""

    id = "google_free"
    label = "Google 免费通道"
    URL = "https://translate.googleapis.com/translate_a/single"

    def translate(self, text: str, src: str, dst: str) -> str:
        if not text.strip():
            return ""
        parts: list[str] = []
        for chunk in chunk_text(text, 4500):
            parts.append(self._one(chunk, src, dst))
        return "\n".join(p for p in parts if p)

    def _one(self, text: str, src: str, dst: str) -> str:
        data = {
            "client": "gtx",
            "sl": lang_google(src) if src != "auto" else "auto",
            "tl": lang_google(dst),
            "dt": "t",
            "q": text,
        }
        try:
            r = self.session.post(self.URL, data=data, timeout=25)
        except requests.RequestException as e:
            raise TranslateError(f"Google 通道不可达：{e}") from e
        payload = _json_or_raise(r)
        try:
            segs = payload[0] or []
        except (IndexError, TypeError) as e:
            raise TranslateError("Google 返回结构异常") from e
        return "".join(seg[0] for seg in segs if seg and seg[0]).strip()


class BingFreeEngine(Engine):
    """Bing 网页翻译接口（ttranslatev3）：先取 IG/IID，再 POST 翻译。"""

    id = "bing_free"
    label = "Bing 免费通道"
    PAGE = "https://www.bing.com/translator"
    API = "https://www.bing.com/ttranslatev3"

    _ig: str = ""
    _iid: str = "translator.5023"
    _key: str = ""
    _token: str = ""
    _at: float = 0.0
    _lock = threading.Lock()

    def _session_params(self, force: bool = False) -> tuple[str, str, str, str]:
        with self._lock:
            now = time.time()
            if not force and self._ig and self._key and now - self._at < 600:
                return self._ig, self._iid, self._key, self._token
            try:
                r = self.session.get(
                    self.PAGE,
                    timeout=15,
                    headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"},
                )
            except requests.RequestException as e:
                raise TranslateError(f"Bing 页面不可达：{e}") from e
            if r.status_code >= 400:
                raise TranslateError(f"Bing 页面 HTTP {r.status_code}")
            html = r.text or ""
            m = re.search(r'IG:"([0-9A-Fa-f]+)"', html)
            if not m:
                raise TranslateError("Bing 页面结构变化，取不到 IG 参数；请改用 Google 或厂商通道")
            iid = re.search(r'data-iid="(translator\.[0-9.]+)"', html)
            abuse = re.search(r'params_AbusePreventionHelper\s*=\s*\[(\d+),"([^"]+)",(\d+)\]', html)
            BingFreeEngine._ig = m.group(1)
            BingFreeEngine._iid = iid.group(1) if iid else "translator.5023"
            BingFreeEngine._key = abuse.group(1) if abuse else ""
            BingFreeEngine._token = abuse.group(2) if abuse else ""
            BingFreeEngine._at = now
            return BingFreeEngine._ig, BingFreeEngine._iid, BingFreeEngine._key, BingFreeEngine._token

    def translate(self, text: str, src: str, dst: str) -> str:
        if not text.strip():
            return ""
        out: list[str] = []
        for chunk in chunk_text(text, 4000):
            out.append(self._one(chunk, src, dst))
        return "\n".join(o for o in out if o)

    def _one(self, text: str, src: str, dst: str) -> str:
        to_lang = lang_bing(dst) or "zh-Hans"
        from_lang = lang_bing(src) or "auto-detect"
        for attempt in range(2):
            ig, iid, key, token = self._session_params(force=attempt > 0)
            try:
                r = self.session.post(
                    self.API,
                    params={"isVertical": "1", "IG": ig, "IID": iid},
                    data={
                        "fromLang": from_lang,
                        "to": to_lang,
                        "text": text,
                        "token": token,
                        "key": key,
                    },
                    headers={
                        "User-Agent": _UA,
                        "Referer": self.PAGE,
                        "Origin": "https://www.bing.com",
                    },
                    timeout=25,
                )
            except requests.RequestException as e:
                raise TranslateError(f"Bing 通道不可达：{e}") from e
            if r.status_code in (401, 403, 429) and attempt == 0:
                continue
            payload = _json_or_raise(r)
            if isinstance(payload, dict) and payload.get("statusCode"):
                if attempt == 0:
                    continue
                raise TranslateError(
                    f"Bing 拒绝请求（{payload.get('statusCode')}），请改用 Google / 厂商 / AI 通道"
                )
            return _parse_bing(payload)
        raise TranslateError("Bing 通道重试后仍失败")


# ---------------------------------------------------------------- 厂商 key


class BaiduEngine(Engine):
    id = "baidu"
    label = "百度翻译"
    URL = "https://fanyi-api.baidu.com/api/trans/vip/translate"

    def translate(self, text: str, src: str, dst: str) -> str:
        if not self.cfg.appid or not self.cfg.secret:
            raise TranslateError("请在设置中填写百度翻译的 appid 与密钥")
        if not text.strip():
            return ""
        out: list[str] = []
        for chunk in chunk_text(text, 1800):
            out.append(self._one(chunk, src, dst))
        return "\n".join(o for o in out if o)

    def _one(self, text: str, src: str, dst: str) -> str:
        salt = str(random.randint(32768, 65536))
        sign_src = self.cfg.appid + text + salt + self.cfg.secret
        sign = hashlib.md5(sign_src.encode("utf-8")).hexdigest()
        params = {
            "q": text,
            "from": lang_baidu(src),
            "to": lang_baidu(dst),
            "appid": self.cfg.appid,
            "salt": salt,
            "sign": sign,
        }
        try:
            r = self.session.get(self.URL, params=params, timeout=25)
        except requests.RequestException as e:
            raise TranslateError(f"百度通道不可达：{e}") from e
        payload = _json_or_raise(r)
        if payload.get("error_code"):
            raise TranslateError(f"百度错误 {payload.get('error_code')}：{payload.get('error_msg', '')}")
        rows = payload.get("trans_result") or []
        return "\n".join(row.get("dst", "") for row in rows).strip()


class YoudaoEngine(Engine):
    id = "youdao"
    label = "有道智云"
    URL = "https://openapi.youdao.com/api"

    @staticmethod
    def _truncate(q: str) -> str:
        n = len(q)
        return q if n <= 20 else q[:10] + str(n) + q[-10:]

    def translate(self, text: str, src: str, dst: str) -> str:
        if not self.cfg.appid or not self.cfg.secret:
            raise TranslateError("请在设置中填写有道的 appKey 与 appSecret")
        if not text.strip():
            return ""
        out: list[str] = []
        for chunk in chunk_text(text, 1600):
            out.append(self._one(chunk, src, dst))
        return "\n".join(o for o in out if o)

    def _one(self, text: str, src: str, dst: str) -> str:
        salt = str(random.randint(1, 65535))
        curtime = str(int(time.time()))
        sign = hashlib.sha256(
            (self.cfg.appid + self._truncate(text) + salt + curtime + self.cfg.secret).encode("utf-8")
        ).hexdigest()
        data = {
            "q": text,
            "from": lang_youdao(src),
            "to": lang_youdao(dst),
            "appKey": self.cfg.appid,
            "salt": salt,
            "sign": sign,
            "signType": "v3",
            "curtime": curtime,
        }
        try:
            r = self.session.post(self.URL, data=data, timeout=25)
        except requests.RequestException as e:
            raise TranslateError(f"有道通道不可达：{e}") from e
        payload = _json_or_raise(r)
        code = payload.get("errorCode")
        if code not in ("0", 0, None):
            raise TranslateError(f"有道错误码 {code}")
        tr = payload.get("translation") or []
        return "\n".join(tr).strip()


class DeepLEngine(Engine):
    id = "deepl"
    label = "DeepL"

    def _endpoint(self) -> str:
        if self.cfg.base_url.strip():
            return self.cfg.base_url.strip().rstrip("/")
        return "https://api-free.deepl.com/v2/translate" if self.cfg.use_free_deepl else "https://api.deepl.com/v2/translate"

    def translate(self, text: str, src: str, dst: str) -> str:
        if not self.cfg.auth_key:
            raise TranslateError("请在设置中填写 DeepL 的 Auth Key")
        if not text.strip():
            return ""
        target = lang_deepl(dst) or "ZH"
        out: list[str] = []
        for chunk in chunk_text(text, 3000):
            data = {"text": chunk, "target_lang": target}
            source = lang_deepl(src)
            if source:
                data["source_lang"] = source
            try:
                r = self.session.post(
                    self._endpoint(),
                    data=data,
                    headers={"Authorization": f"DeepL-Auth-Key {self.cfg.auth_key}"},
                    timeout=25,
                )
            except requests.RequestException as e:
                raise TranslateError(f"DeepL 不可达：{e}") from e
            payload = _json_or_raise(r)
            rows = payload.get("translations") or []
            out.append("".join(row.get("text", "") for row in rows))
        return "\n".join(o for o in out if o)


# ---------------------------------------------------------------- AI 大模型


def chat_completions_url(base: str) -> str:
    b = (base or "").strip().rstrip("/")
    if not b:
        raise TranslateError("请先在设置里填写 API 地址（Base URL）")
    if b.endswith("/chat/completions"):
        return b
    if b.endswith("/v1") or b.endswith("/v4"):
        return b + "/chat/completions"
    return b + "/v1/chat/completions"


class AIEngine(Engine):
    """任意 OpenAI 兼容端点，支持 SSE 流式。"""

    id = "ai"
    label = "AI 大模型"
    supports_stream = True

    # -- payload 组装
    def _messages(self, text: str, src: str, dst: str) -> list[dict]:
        prompt = (self.app.prompt or "").format(src=lang_human(src), dst=lang_human(dst))
        return [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ]

    def _payload(self, text: str, src: str, dst: str, stream: bool) -> dict:
        if not self.cfg.api_key and "127.0.0.1" not in (self.cfg.base_url or "") and "localhost" not in (self.cfg.base_url or ""):
            raise TranslateError("请先在设置里填写 API Key")
        if not self.cfg.model:
            raise TranslateError("请先在设置里填写模型名（model）")
        payload: dict = {
            "model": self.cfg.model,
            "messages": self._messages(text, src, dst),
            "temperature": float(self.cfg.temperature or 0.2),
            "stream": stream,
        }
        if self.cfg.extra_body.strip():
            try:
                extra = json.loads(self.cfg.extra_body)
                if isinstance(extra, dict):
                    payload.update(extra)
                    payload.update({"messages": self._messages(text, src, dst), "stream": stream})
            except json.JSONDecodeError:
                raise TranslateError("设置里的「额外参数」不是合法 JSON")
        return payload

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            h["Authorization"] = f"Bearer {self.cfg.api_key}"
        return h

    # -- 非流式
    def translate(self, text: str, src: str, dst: str) -> str:
        if not text.strip():
            return ""
        out: list[str] = []
        for chunk in chunk_text(text, 3800):
            payload = self._payload(chunk, src, dst, stream=False)
            try:
                r = self.session.post(
                    chat_completions_url(self.cfg.base_url),
                    json=payload,
                    headers=self._headers(),
                    timeout=(15, 180),
                )
            except requests.RequestException as e:
                raise TranslateError(f"AI 通道不可达：{e}") from e
            data = _json_or_raise(r)
            try:
                out.append(data["choices"][0]["message"]["content"].strip())
            except (KeyError, IndexError, TypeError):
                raise TranslateError(f"AI 返回异常：{json.dumps(data, ensure_ascii=False)[:300]}")
        return "\n".join(o for o in out if o)

    # -- 流式
    def stream(self, text: str, src: str, dst: str) -> Iterator[str]:
        if not text.strip():
            return
        chunks = chunk_text(text, 3800)
        for idx, chunk in enumerate(chunks):
            payload = self._payload(chunk, src, dst, stream=True)
            try:
                resp = self.session.post(
                    chat_completions_url(self.cfg.base_url),
                    json=payload,
                    headers=self._headers(),
                    timeout=(15, 300),
                    stream=True,
                )
            except requests.RequestException as e:
                raise TranslateError(f"AI 通道不可达：{e}") from e
            if resp.status_code >= 400:
                body = ""
                try:
                    body = resp.text[:400]
                except Exception:
                    pass
                raise TranslateError(f"AI 通道 HTTP {resp.status_code}：{body}")
            got_any = False
            try:
                for delta in _iter_sse(resp):
                    got_any = True
                    yield delta
                if not got_any:
                    # 有些代理忽略 stream=true，回退一次性读取
                    try:
                        data = resp.json()
                        content = data["choices"][0]["message"]["content"]
                        yield content
                    except Exception:
                        raise TranslateError("AI 通道没有返回内容（检查模型名与配额）")
            finally:
                resp.close()
            if idx < len(chunks) - 1:
                yield "\n"


def _iter_sse(resp: requests.Response) -> Iterator[str]:
    for raw in resp.iter_lines(decode_unicode=False):
        if not raw:
            continue
        line = raw.decode("utf-8", "replace").strip()
        if line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            if data == "[DONE]":
                return
            continue
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = obj.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        piece = delta.get("content")
        if piece:
            yield piece
        elif choices[0].get("message", {}).get("content"):
            yield choices[0]["message"]["content"]


# ---------------------------------------------------------------- 工厂


ENGINE_CLASSES = {
    "google_free": GoogleFreeEngine,
    "bing_free": BingFreeEngine,
    "baidu": BaiduEngine,
    "youdao": YoudaoEngine,
    "deepl": DeepLEngine,
    "ai": AIEngine,
}


def make_engine(cfg: AppConfig, engine_id: str | None = None) -> Engine:
    eid = engine_id or cfg.engine
    cls = ENGINE_CLASSES.get(eid)
    if cls is None:
        raise TranslateError(f"未知翻译通道：{eid}")
    return cls(cfg.engine_config(eid), cfg)


__all__ = [
    "Engine",
    "AIEngine",
    "BaiduEngine",
    "BingFreeEngine",
    "DeepLEngine",
    "GoogleFreeEngine",
    "YoudaoEngine",
    "TranslateError",
    "make_engine",
    "chunk_text",
]
