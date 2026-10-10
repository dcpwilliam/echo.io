"""用户数据接口：增删改查 / 导出导入。"""
from ..core.errors import BadRequest
from ..services import user_service


def register(router):
    @router.get("/api/users")
    def index(req):
        """列出所有用户（只含 profile，不含明细数据）。"""
        return user_service.list_users()

    @router.post("/api/users")
    def create(req):
        """body: { id?, name?, email?, sub? }"""
        return user_service.create(req.json(default={}))

    @router.get("/api/users/{user_id}")
    def detail(req, user_id):
        return user_service.get(user_id)

    @router.patch("/api/users/{user_id}")
    def update(req, user_id):
        body = req.json(default={})
        if not body:
            raise BadRequest("请求体为空")
        return user_service.update_user(user_id, body)

    @router.delete("/api/users/{user_id}")
    def remove(req, user_id):
        return user_service.remove(user_id)

    @router.get("/api/users/{user_id}/export")
    def export(req, user_id):
        """全量导出：用户 + 目标 + 时间线 + 会话。"""
        return user_service.export(user_id)

    @router.post("/api/users/{user_id}/import")
    def import_data(req, user_id):
        """body: { goals?, records?, messages?, mode: replace|merge }"""
        body = req.json(default={})
        return user_service.import_data(user_id, body, body.get("mode", "replace"))

    return router
