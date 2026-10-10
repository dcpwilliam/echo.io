"""后台管理接口（需登录）：用户等级 / 金币 / 投票记录 的查看与设置、删除用户。

所有端点都先过 auth.current_user(req)，未登录一律 401，避免被匿名调用。
"""
from ..core import auth
from ..core.errors import BadRequest, NotFound, Unauthorized
from ..services import user_service


def _require_admin(req):
    u = auth.current_user(req)
    if not u:
        raise Unauthorized("请先登录")
    return u


def register(router):
    @router.get("/api/admin/users")
    def list_users(req):
        """列出全部用户，并附等级 / 金币 / 投票数摘要。"""
        _require_admin(req)
        data = user_service.list_users()
        for u in data.get("users", []):
            summary = user_service.get_profile_summary(u.get("id"))
            u["level"] = summary["level"]
            u["coins"] = summary["coins"]
            u["votesCount"] = summary["votesCount"]
        return data

    @router.get("/api/admin/users/{user_id}")
    def profile(req, user_id):
        """某用户的等级 / 金币 / 投票记录。"""
        _require_admin(req)
        return user_service.get_profile(user_id)

    @router.get("/api/admin/users/{user_id}/votes")
    def votes(req, user_id):
        """某用户的投票记录列表。"""
        _require_admin(req)
        return user_service.list_votes(user_id)

    @router.post("/api/admin/users/{user_id}/level")
    def set_level(req, user_id):
        """设置等级。body: { level }"""
        _require_admin(req)
        body = req.json(default={})
        try:
            level = int(body.get("level"))
        except (TypeError, ValueError):
            raise BadRequest("level 必须是整数")
        if level < 0:
            raise BadRequest("level 不能为负")
        return user_service.set_level(user_id, level)

    @router.post("/api/admin/users/{user_id}/coins")
    def set_coins(req, user_id):
        """设置金币数量。body: { coins }"""
        _require_admin(req)
        body = req.json(default={})
        try:
            coins = int(body.get("coins"))
        except (TypeError, ValueError):
            raise BadRequest("coins 必须是整数")
        if coins < 0:
            raise BadRequest("coins 不能为负")
        return user_service.set_coins(user_id, coins)

    @router.post("/api/admin/users/{user_id}/votes")
    def add_vote(req, user_id):
        """手动记录一条投票。body: { question, choice, detail?, weight? }"""
        _require_admin(req)
        return user_service.add_vote(user_id, req.json(default={}))

    @router.delete("/api/admin/users/{user_id}")
    def delete_user(req, user_id):
        """删除用户（含其全部数据）。"""
        _require_admin(req)
        return user_service.remove(user_id)

    return router
