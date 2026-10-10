"""运维接口：健康检查 / 服务信息与路由清单 / 最近日志。"""
import time

from .. import __version__
from ..config import config
from ..core import tail_logs
from ..core.http import Response
from ..llm import registry
from ..storage import store as storage

_STARTED = time.time()


def register(router):
    @router.get("/health")
    def health(req):
        return {
            "ok": True,
            "service": "aiservice",
            "version": __version__,
            "uptime": round(time.time() - _STARTED, 1),
            "llmProvider": config.llm_provider(),
            "activeProvider": registry.get_default_id(),
            "providerCount": registry.count(),
            "storage": storage.stats(),
        }

    @router.get("/api/info")
    def info(req):
        return {
            "version": __version__,
            "config": config.public_dict(),
            "routes": router.listing(),
        }

    @router.get("/api/logs")
    def logs(req):
        """最近 N 行日志（默认 100，最多 2000）。"""
        try:
            lines = int(req.arg("lines", 100))
        except (TypeError, ValueError):
            lines = 100
        return Response.json({"lines": tail_logs(lines)})

    return router
