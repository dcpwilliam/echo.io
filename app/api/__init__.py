"""API 层：只负责接参数、调 service、回 JSON。"""
from ..core.router import Router
from . import admin, answers, auth, health, legacy_state, prompt, providers, users

MODULES = [health, prompt, users, legacy_state, answers, auth, admin, providers]


def build_router():
    """按模块顺序注册路由，返回可直接交给 server 的 Router。"""
    router = Router()
    for module in MODULES:
        module.register(router)
    return router


__all__ = ["build_router", "MODULES"]
