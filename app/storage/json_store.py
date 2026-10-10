"""JSON 文件存储：一个用户一个文件，原子写 + 线程锁。

    data/users/<user_id>.json
        { user, goals, records, messages, updatedAt }
"""
import json
import os
import threading
import time

from ..config import config
from . import schema

_LOCK = threading.RLock()


def _dir():
    path = os.path.join(config.DATA_DIR, "users")
    os.makedirs(path, exist_ok=True)
    return path


def _file(user_id):
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(user_id or "anonymous"))
    return os.path.join(_dir(), safe + ".json")


def _read(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return None


def _write(path, data):
    """先写临时文件再原子替换，避免写一半被读。"""
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ---------------- 对外 ----------------

def load(user_id):
    """读用户全量数据；不存在就返回一份空骨架（不落盘）。"""
    with _LOCK:
        data = _read(_file(user_id))
        return schema.normalize_state(data, user_id)


def exists(user_id):
    return os.path.exists(_file(user_id))


def save(user_id, state):
    state["updatedAt"] = int(time.time() * 1000)
    with _LOCK:
        _write(_file(user_id), state)
    return state


def update(user_id, mutator):
    """读-改-写一把锁完成，避免并发丢更新。"""
    with _LOCK:
        state = schema.normalize_state(_read(_file(user_id)), user_id)
        result = mutator(state)
        state["updatedAt"] = int(time.time() * 1000)
        _write(_file(user_id), state)
        return result if result is not None else state


def list_users():
    out = []
    for name in sorted(os.listdir(_dir())) if os.path.isdir(_dir()) else []:
        if not name.endswith(".json"):
            continue
        data = _read(os.path.join(_dir(), name))
        if data and isinstance(data.get("user"), dict):
            out.append(data["user"])
    return out


def remove(user_id):
    with _LOCK:
        path = _file(user_id)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False


def stats():
    return {
        "backend": "json",
        "dataDir": _dir(),
        "users": len(list_users()),
    }
