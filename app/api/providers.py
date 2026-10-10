"""后台管理接口（需登录）：LLM Provider 的增删改查、设默认、连通性测试。

所有端点都先过 auth.current_user(req)，未登录一律 401。
配置改动通过 llm.registry 实时生效并持久化到 data/llm_providers.json，无需重启。
"""
import logging

from ..core import auth
from ..core.errors import BadRequest, NotFound, Unauthorized
from .. import llm
from ..llm import registry

log = logging.getLogger("aiservice.providers")


def _require_admin(req):
    u = auth.current_user(req)
    if not u:
        raise Unauthorized("请先登录")
    return u


def _wrap(fn):
    """把 registry 的 ValueError/KeyError 翻译成合适的 HTTP 错误。"""
    try:
        return fn()
    except ValueError as e:
        raise BadRequest(str(e))
    except KeyError as e:
        raise NotFound(str(e))


def register(router):
    @router.get("/api/admin/providers")
    def list_providers(req):
        """列出全部 provider（apiKey 默认脱敏，?reveal=1 看明文）。"""
        _require_admin(req)
        reveal = req.arg("reveal", "") == "1"
        return registry.list_providers(reveal=reveal)

    @router.get("/api/admin/providers/{id}")
    def get_provider(req, id):
        """单个 provider（含明文 apiKey，供编辑回填）。"""
        _require_admin(req)
        cfg = _wrap(lambda: registry.get(id, reveal=True))
        if not cfg:
            raise NotFound("provider 不存在: %s" % id)
        return cfg

    @router.post("/api/admin/providers")
    def create_provider(req):
        """新增 provider。body 即配置（id 会被忽略并自动生成）。"""
        _require_admin(req)
        body = req.json(default={})
        if not isinstance(body, dict):
            raise BadRequest("body 必须是对象")
        return _wrap(lambda: registry.create(body))

    @router.put("/api/admin/providers/{id}")
    def update_provider(req, id):
        """更新 provider。局部合并；apiKey 留空表示保留原值。"""
        _require_admin(req)
        body = req.json(default={})
        if not isinstance(body, dict):
            raise BadRequest("body 必须是对象")
        return _wrap(lambda: registry.update(id, body))

    @router.delete("/api/admin/providers/{id}")
    def delete_provider(req, id):
        """删除 provider（echo 不可删）。"""
        _require_admin(req)
        return _wrap(lambda: registry.delete(id))

    @router.post("/api/admin/providers/{id}/default")
    def set_default(req, id):
        """把该 provider 设为默认（实时生效）。"""
        _require_admin(req)
        return _wrap(lambda: registry.set_default(id))

    @router.post("/api/admin/providers/{id}/test")
    def test_provider(req, id):
        """连通性测试：现建 provider 跑一句极短补全，返回成功/失败与样本。"""
        _require_admin(req)
        cfg = registry.get(id)
        if not cfg:
            raise NotFound("provider 不存在: %s" % id)
        if cfg.get("type") == "echo":
            return {"ok": True, "provider": "echo", "note": "本地规则，无需联网测试"}
        provider = llm.get_provider(id)
        if provider.kind != "openai" or not provider.available:
            return {"ok": False, "provider": id, "reason": "no-api-key",
                    "detail": "未配置 API Key，无法联通测试"}
        try:
            sample = provider.complete(
                "你是一个用于自检的助手。", "只回复两个字：正常",
                max_tokens=16, temperature=0,
            )
            return {"ok": True, "provider": id, "sample": (sample or "").strip()[:200]}
        except Exception as e:
            return {"ok": False, "provider": id, "reason": "error",
                    "detail": str(e)[:300]}

    return router
