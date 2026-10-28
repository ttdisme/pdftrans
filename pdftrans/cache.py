"""翻译缓存：SQLite 落盘，跨会话复用。"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from pathlib import Path

from .config import config_dir


def cache_key(engine: str, src: str, dst: str, text: str) -> str:
    norm = " ".join(text.split())
    blob = f"{engine}|{src}|{dst}|{norm}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _note_failure(message: str) -> None:
    """缓存不可用时留一条记录，不打断主流程。"""
    try:
        log = config_dir() / "cache-error.log"
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass


class TranslationCache:
    def __init__(self, path: Path | None = None, limit: int = 20000, enabled: bool = True):
        self.enabled = enabled
        self.limit = limit
        self.last_error: str | None = None
        self.path = Path(path) if path is not None else (config_dir() / "cache.sqlite3")
        self._local = threading.local()
        if self.enabled:
            try:
                self._init_schema()
            except Exception as exc:  # 磁盘/权限等异常时降级为无缓存，程序照常跑
                self.enabled = False
                self.last_error = f"{type(exc).__name__}: {exc} (path={self.path})"
                _note_failure(self.last_error)

    def _init_schema(self) -> None:
        conn = self._conn()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tr ("
            " key TEXT PRIMARY KEY,"
            " engine TEXT NOT NULL,"
            " text TEXT NOT NULL,"
            " created REAL NOT NULL"
            ")"
        )
        conn.commit()


    # 每线程独立连接，避免跨线程使用 sqlite 对象
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    def get(self, key: str) -> str | None:
        if not self.enabled:
            return None
        try:
            row = self._conn().execute("SELECT text FROM tr WHERE key = ?", (key,)).fetchone()
            return row[0] if row else None
        except sqlite3.Error:
            return None

    def put(self, key: str, engine: str, text: str) -> None:
        if not self.enabled or not text.strip():
            return
        try:
            conn = self._conn()
            conn.execute(
                "INSERT OR REPLACE INTO tr (key, engine, text, created) VALUES (?, ?, ?, ?)",
                (key, engine, text, time.time()),
            )
            conn.commit()
            self._trim(conn)
        except sqlite3.Error:
            pass

    def _trim(self, conn: sqlite3.Connection) -> None:
        try:
            (count,) = conn.execute("SELECT COUNT(1) FROM tr").fetchone()
            if count > self.limit:
                conn.execute(
                    "DELETE FROM tr WHERE key IN ("
                    " SELECT key FROM tr ORDER BY created ASC LIMIT ?)",
                    (count - self.limit,),
                )
                conn.commit()
        except sqlite3.Error:
            pass

    def clear(self) -> None:
        if not self.enabled:
            return
        try:
            conn = self._conn()
            conn.execute("DELETE FROM tr")
            conn.commit()
        except sqlite3.Error:
            pass

    def count(self) -> int:
        if not self.enabled:
            return 0
        try:
            return int(self._conn().execute("SELECT COUNT(1) FROM tr").fetchone()[0])
        except sqlite3.Error:
            return 0
