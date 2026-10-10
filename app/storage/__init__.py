"""存储层：可插拔后端（sqlite | json），对外暴露统一的 store 代理。

切换方式：
    AISERVICE_STORAGE=sqlite   （默认，单文件库，支持多进程并发锁）
    AISERVICE_STORAGE=json     （老方案，一个用户一个 JSON 文件）

两种用法都支持，且都按当前后端路由：
    from ..storage import store
    store.load(user_id)                 # 代理对象，转发到激活后端

    from ..storage import update, load  # 直接函数，同样转发到激活后端
    update(user_id, mutate)

无论底层是哪种，services / api 层都不碰具体后端，切换后端不用改业务代码。
`/health` 返回的 `storage.backend` 能看到当前用的是哪种。
"""
from . import schema
from . import json_store
from . import sqlite_store


def _backend():
    from ..config import config
    return sqlite_store if config.STORAGE_BACKEND == "sqlite" else json_store


class _Store:
    """把所有属性访问转发到当前激活的后端模块。"""

    def __getattr__(self, name):
        return getattr(_backend(), name)


store = _Store()


# 直接函数形式（转发到激活后端），兼容 `from ..storage import update / load` 这类写法。
def load(user_id):
    return _backend().load(user_id)


def save(user_id, state):
    return _backend().save(user_id, state)


def update(user_id, mutator):
    return _backend().update(user_id, mutator)


def exists(user_id):
    return _backend().exists(user_id)


def remove(user_id):
    return _backend().remove(user_id)


def list_users():
    return _backend().list_users()


def stats():
    return _backend().stats()


__all__ = ["schema", "store", "json_store", "sqlite_store",
           "load", "save", "update", "exists", "remove", "list_users", "stats"]
