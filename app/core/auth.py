"""极简后台鉴权：用户名/密码登录，签发 HMAC 签名 token，存 HttpOnly cookie。

零第三方依赖，全部用标准库。默认账号密码来自环境变量
AISERVICE_ADMIN_USER / AISERVICE_ADMIN_PASS（默认 admin / admin，仅本机调试用，启动会告警）。
token 为 base64url(payload).HMAC 签名，payload 含用户名与过期时间。
"""
import base64
import hashlib
import hmac
import json
import os
import time

SESSION_TTL = int(os.environ.get("AISERVICE_SESSION_TTL", "28800"))  # 会话有效期（秒），默认 8 小时

ADMIN_USER = os.environ.get("AISERVICE_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("AISERVICE_ADMIN_PASS", "admin")
# 签名密钥：优先用环境变量，否则用固定开发密钥（重启后仍可用，仅本机调试）
SECRET = os.environ.get("AISERVICE_SECRET") or "aiservice-default-dev-secret"

_COOKIE = "aisession"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(payload_b64: str) -> str:
    return hmac.new(SECRET.encode("utf-8"), payload_b64.encode("utf-8"),
                    hashlib.sha256).hexdigest()


def create_token(user: str) -> str:
    payload = json.dumps({"u": user, "exp": int(time.time()) + SESSION_TTL}).encode("utf-8")
    p = _b64(payload)
    return p + "." + _sign(p)


def verify_token(token: str):
    """返回用户名；无效/过期返回 None。"""
    if not token or "." not in token:
        return None
    p, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(p), sig):
        return None
    try:
        data = json.loads(_b64d(p))
    except Exception:
        return None
    if data.get("exp", 0) < int(time.time()):
        return None
    return data.get("u")


def check_credentials(user: str, password: str) -> bool:
    return user == ADMIN_USER and password == ADMIN_PASS


def current_user(req):
    """从 cookie 或 Authorization: Bearer 里取当前登录用户，未登录返回 None。"""
    cookie = req.headers.get("cookie", "")
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith(_COOKIE + "="):
            u = verify_token(part[len(_COOKIE) + 1:])
            if u:
                return u
    bearer = req.bearer_token()
    if bearer:
        return verify_token(bearer)
    return None


def cookie_header(token: str) -> str:
    return "%s=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=%d" % (_COOKIE, token, SESSION_TTL)


def clear_cookie_header() -> str:
    return "%s=; Path=/; HttpOnly; Max-Age=0" % _COOKIE


def using_default_credentials() -> bool:
    return ADMIN_PASS == "admin" and ADMIN_USER == "admin"
