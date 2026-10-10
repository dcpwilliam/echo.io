#!/usr/bin/env python3
"""存储层双后端一致性测试：json 与 sqlite 走同一套接口，行为应一致。

    python tools/test_storage.py
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.config import config                                  # noqa: E402
from app.storage import store, schema                          # noqa: E402


def run_backend(backend_name, data_dir):
    config.STORAGE_BACKEND = backend_name
    config.DATA_DIR = data_dir
    passed = 0
    failed = 0

    def check(name, cond, extra=""):
        nonlocal passed, failed
        if cond:
            passed += 1
            print("    ✓ %s %s" % (name, extra))
        else:
            failed += 1
            print("    ✗ %s %s" % (name, extra))

    # 初始不存在
    check("exists(新用户)=False", not store.exists("u1"))
    st = store.load("u1")
    check("load 空骨架有 user", isinstance(st.get("user"), dict))
    check("load 后 exists 仍为 False", not store.exists("u1"))

    # save
    st["user"]["name"] = "测试用户"
    st["goals"].append(schema.normalize_goal({"title": "目标A"}))
    store.save("u1", st)
    check("save 后 exists=True", store.exists("u1"))

    # load 回来
    st2 = store.load("u1")
    check("load 回来 name 一致", st2["user"]["name"] == "测试用户")
    check("load 回来 goals 数量=1", len(st2["goals"]) == 1)

    # update（mutator 返回新目标数）
    def add_goal(state):
        state["goals"].append(schema.normalize_goal({"title": "目标B"}))
        return len(state["goals"])
    n = store.update("u1", add_goal)
    check("update 返回新目标数=2", n == 2)
    check("update 生效", len(store.load("u1")["goals"]) == 2)

    # update 再追加 record
    store.update("u1", lambda s: s["records"].append(
        schema.normalize_record({"goal": "g", "tasks": [{"title": "做点事"}]})))
    check("update 追加 record", len(store.load("u1")["records"]) == 1)

    # list_users 含 u1
    ids = [u.get("id") for u in store.list_users()]
    check("list_users 含 u1", "u1" in ids)

    # stats
    s = store.stats()
    check("stats.users>=1", s["users"] >= 1)
    check("stats.backend=%s" % backend_name, s.get("backend") == backend_name)

    # remove
    store.remove("u1")
    check("remove 后 exists=False", not store.exists("u1"))

    return passed, failed


def main():
    tmp = tempfile.mkdtemp(prefix="aiservice_storage_test_")
    total_passed = 0
    total_failed = 0
    try:
        for backend in ("json", "sqlite"):
            print("后端: %s" % backend)
            data_dir = os.path.join(tmp, backend)
            os.makedirs(data_dir, exist_ok=True)
            p, f = run_backend(backend, data_dir)
            total_passed += p
            total_failed += f
            print()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("通过 %d 项，失败 %d 项" % (total_passed, total_failed))
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
