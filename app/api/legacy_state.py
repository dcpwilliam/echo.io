"""兼容层：让小程序现有的 utils/oidc.js（pullState / pushState）不用改就能接进来。

小程序端调用的是：
    GET  /api/state   Authorization: Bearer <access_token>
    PUT  /api/state
这里用 Bearer 里的 token 当作 user_id（与 server/index.js 的行为一致）。
"""
from ..core.errors import BadRequest, Unauthorized
from ..services import user_service


def _user_id(req):
    token = req.bearer_token()
    if not token:
        # 没带 token 时退回 query / 默认用户，方便本地调试
        return req.query.get("user_id") or "anonymous"
    import hashlib
    return "u_" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def register(router):
    @router.get("/api/state")
    def pull(req):
        user_id = _user_id(req)
        if user_id == "anonymous":
            raise Unauthorized("缺少 Bearer token（调试可加 ?user_id=xxx）")
        return user_service.get_state(user_id)

    @router.put("/api/state")
    def push(req):
        user_id = _user_id(req)
        if user_id == "anonymous":
            raise Unauthorized("缺少 Bearer token（调试可加 ?user_id=xxx）")
        body = req.json(default={})
        if not isinstance(body, dict):
            raise BadRequest("请求体必须是对象")
        return user_service.put_state(user_id, body)

    return router
