#!/usr/bin/env python3
"""把老的 JSON 文件存储迁移到 SQLite。

用法：
    python tools/migrate_json_to_sqlite.py
    python tools/migrate_json_to_sqlite.py --data-dir /path/to/data
    python tools/migrate_json_to_sqlite.py --dry-run        # 只统计，不写库

行为：
  * 扫描 <data-dir>/users/*.json
  * 逐个 normalize_state 后 upsert 进 <data-dir>/aiservice.db
  * 已存在的用户会被覆盖（以 JSON 文件为准）
  * 不删除任何 JSON 文件，迁移后可自行归档
"""
import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.config import config                              # noqa: E402
from app.storage import sqlite_store, schema               # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="JSON -> SQLite 迁移")
    parser.add_argument("--data-dir", default=config.DATA_DIR,
                        help="数据目录（默认 %s）" % config.DATA_DIR)
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    args = parser.parse_args()

    config.DATA_DIR = args.data_dir
    users_dir = os.path.join(config.DATA_DIR, "users")
    files = sorted(glob.glob(os.path.join(users_dir, "*.json")))

    if not files:
        print("没有找到 JSON 用户文件：%s" % users_dir)
        return 0

    print("数据目录：%s" % config.DATA_DIR)
    print("发现 %d 个 JSON 用户文件\n" % len(files))

    ok, skip = 0, 0
    for path in files:
        name = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (ValueError, OSError) as e:
            print("  ✗ %s  读取失败：%s" % (name, e))
            skip += 1
            continue

        user_id = (raw.get("user") or {}).get("id") or os.path.splitext(name)[0]
        state = schema.normalize_state(raw, user_id)
        n_goals = len(state.get("goals") or [])
        n_records = len(state.get("records") or [])

        if args.dry_run:
            print("  · %s  user=%s  目标=%d 记录=%d" % (name, user_id, n_goals, n_records))
            ok += 1
            continue

        sqlite_store.save(user_id, state)
        print("  ✓ %s  user=%s  目标=%d 记录=%d" % (name, user_id, n_goals, n_records))
        ok += 1

    print("\n迁移完成：成功 %d，跳过 %d" % (ok, skip))
    if not args.dry_run:
        print("SQLite 库：%s" % os.path.join(config.DATA_DIR, "aiservice.db"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
