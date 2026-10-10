"""后台登录接口：登录 / 登出 / 当前用户。"""
from ..core import auth
from ..core.errors import Unauthorized
from ..core.http import Response


def register(router):
    @router.post("/api/auth/login")
    def login(req):
        """用户名 + 密码登录，成功下发 HttpOnly cookie。body: { username, password }"""
        body = req.json(default={})
        user = (body.get("username") or body.get("user") or "").strip()
        pwd = body.get("password") or ""
        if not auth.check_credentials(user, pwd):
            raise Unauthorized("用户名或密码错误")
        token = auth.create_token(user)
        return Response.json(
            {"ok": True, "user": user},
            headers={"Set-Cookie": auth.cookie_header(token)},
        )

    @router.post("/api/auth/logout")
    def logout(req):
        """清除登录 cookie。"""
        return Response.json(
            {"ok": True},
            headers={"Set-Cookie": auth.clear_cookie_header()},
        )

    @router.get("/api/auth/me")
    def me(req):
        """返回当前登录用户；未登录返回 401。"""
        u = auth.current_user(req)
        if not u:
            raise Unauthorized("未登录")
        return {"ok": True, "user": u}

    return router
