"""SQLite 存储后端：一个用户一行，state 整体存成 JSON 文本。

    data/aiservice.db
        users(user_id TEXT PRIMARY KEY, state TEXT, updated_at INTEGER)

设计要点：
  * 沿用 json_store 的「整份 state 是一个文档」模型，所以 services / api
    层的 mutator 逻辑完全不用改，只是底层从「一个文件」换成「数据库一行」。
  * 读-改-写统一在 threading.RLock 内完成，避免并发丢更新；SQLite 自身
    的事务 + WAL 模式还能挡住多进程同时写。
  * 零第三方依赖，用的是标准库 sqlite3。
"""
import json
import os
import sqlite3
import threading
import time

from ..config import config
from . import schema

_LOCK = threading.RLock()


def _db_path():
    return os.path.join(config.DATA_DIR, "aiservice.db")


def _connect():
    """每条操作单独开连接，读 config.DATA_DIR 最新值（run.py --data-dir 会改它）。"""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(_db_path(), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        " user_id TEXT PRIMARY KEY,"
        " state TEXT NOT NULL,"
        " updated_at INTEGER NOT NULL)"
    )
    conn.commit()
    return conn


def _read_row(conn, user_id):
    row = conn.execute(
        "SELECT state FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except (ValueError, TypeError):
        return None


def _write_row(conn, user_id, state):
    state["updatedAt"] = int(time.time() * 1000)
    conn.execute(
        "INSERT INTO users(user_id, state, updated_at) VALUES(?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET state=excluded.state, updated_at=excluded.updated_at",
        (user_id, json.dumps(state, ensure_ascii=False), state["updatedAt"]),
    )
    conn.commit()
    return state


# ---------------- 对外（与 json_store 同签名）----------------

def load(user_id):
    """读用户全量数据；不存在就返回一份空骨架（不落盘）。"""
    with _LOCK:
        conn = _connect()
        try:
            data = _read_row(conn, user_id)
            return schema.normalize_state(data, user_id)
        finally:
            conn.close()


def exists(user_id):
    with _LOCK:
        conn = _connect()
        try:
            return _read_row(conn, user_id) is not None
        finally:
            conn.close()


def save(user_id, state):
    with _LOCK:
        conn = _connect()
        try:
            return _write_row(conn, user_id, state)
        finally:
            conn.close()


def update(user_id, mutator):
    """读-改-写一把锁完成，避免并发丢更新。"""
    with _LOCK:
        conn = _connect()
        try:
            state = schema.normalize_state(_read_row(conn, user_id), user_id)
            result = mutator(state)
            _write_row(conn, user_id, state)
            return result if result is not None else state
        finally:
            conn.close()


def list_users():
    out = []
    with _LOCK:
        conn = _connect()
        try:
            for (blob,) in conn.execute("SELECT state FROM users"):
                try:
                    data = json.loads(blob)
                except (ValueError, TypeError):
                    continue
                if isinstance(data, dict) and isinstance(data.get("user"), dict):
                    out.append(data["user"])
            return sorted(out, key=lambda u: u.get("updatedAt", 0), reverse=True)
        finally:
            conn.close()


def remove(user_id):
    with _LOCK:
        conn = _connect()
        try:
            cur = conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def stats():
    with _LOCK:
        conn = _connect()
        try:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        finally:
            conn.close()
    return {
        "backend": "sqlite",
        "dataDir": _db_path(),
        "users": count,
    }
