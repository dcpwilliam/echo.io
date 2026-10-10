#!/usr/bin/env python3
"""aiservice 入口。

    python run.py                 启动（默认 127.0.0.1:8100）
    python run.py --port 8200
    python run.py --host 0.0.0.0
    python run.py --selftest      起临时服务，把所有接口跑一遍后退出
    python run.py --routes        只打印接口清单
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import __version__                                    # noqa: E402
from app.api import build_router                               # noqa: E402
from app.config import config                                  # noqa: E402
from app.core import setup_logging as _setup, tail_logs        # noqa: E402
from app.core.logging import log_path                          # noqa: E402
from app.core.server import serve                              # noqa: E402


def setup_logging(level=None, log_dir=None):
    """控制台 + 滚动文件；返回 logger。"""
    return _setup(
        level=level or config.LOG_LEVEL,
        log_dir=log_dir or config.LOG_DIR,
        console=True,
    )


def print_routes(router):
    print("aiservice v%s 接口清单（%d 个）\n" % (__version__, len(router.routes)))
    width = max(len(r.path) for r in router.routes) + 2
    for r in sorted(router.routes, key=lambda x: (x.path, x.method)):
        print("  %-6s %-*s %s" % (r.method, width, r.path, r.doc))


def selftest():
    """起一个临时服务，用标准库跑一遍所有接口。不想装 curl / httpie 也能验证。"""
    import json
    import tempfile
    import threading
    import urllib.error
    import urllib.request
    from app.core.server import create_server

    # 用临时数据目录，避免污染真实 data/（无论后端是 json 还是 sqlite）
    _tmp = tempfile.mkdtemp(prefix="aiservice_selftest_")
    config.DATA_DIR = _tmp
    config.LOG_DIR = os.path.join(_tmp, "logs")

    router = build_router()
    httpd = create_server(router, "127.0.0.1", 0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % port

    def call(method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            base + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8", "ignore") or "{}")

    def call_full(method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            base + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )

        # 不跟随重定向，才能正确检测 302（GET / 未登录应跳 /login）
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None

        def _parse(raw):
            if not raw:
                return {}
            try:
                return json.loads(raw)
            except ValueError:
                return raw  # 非 JSON（如 HTML 页面）直接返回原文

        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(req, timeout=10) as resp:
                return resp.status, _parse(resp.read().decode("utf-8")), resp.headers
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "ignore") or "{}"
            return e.code, _parse(raw), e.headers

    def call_auth(method, path, body=None, cookie=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            base + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        if cookie:
            req.add_header("Cookie", cookie)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8", "ignore") or "{}")

    passed, failed = 0, 0

    def check(name, cond, extra=""):
        nonlocal passed, failed
        if cond:
            passed += 1
            print("  ✓ %s %s" % (name, extra))
        else:
            failed += 1
            print("  ✗ %s %s" % (name, extra))

    print("aiservice 自测 v%s\n" % __version__)

    code, data = call("GET", "/health")
    check("GET /health", code == 200 and data.get("ok"), "llm=%s" % data.get("llmProvider"))

    code, data = call("GET", "/api/info")
    check("GET /api/info", code == 200 and len(data.get("routes", [])) > 10,
          "%d 个接口" % len(data.get("routes", [])))

    # ---- prompt ----
    code, data = call("GET", "/api/prompt/templates")
    check("GET /api/prompt/templates", code == 200 and len(data.get("templates", [])) >= 4)

    code, data = call("POST", "/api/prompt/render", {"template": "analyze", "variables": {"text": "三个月内减重10斤"}})
    check("POST /api/prompt/render", code == 200 and "三个月内减重10斤" in data.get("user", ""))

    code, data = call("POST", "/api/prompt/analyze", {"text": "三个月内减重 10 斤"})
    cat = data.get("category")
    cat_key = cat.get("key") if isinstance(cat, dict) else cat
    check("POST /api/prompt/analyze", code == 200 and cat_key == "fitness",
          "意图=%s 领域=%s" % (data.get("intentLabel"), cat_key))

    code, data = call("POST", "/api/prompt/complete", {"template": "reframe", "variables": {"text": "最近又没坚持下来"}})
    check("POST /api/prompt/complete", code == 200 and bool(data.get("text")))

    # ---- 答案预测：问题 -> 最可能的 n 个答案 + 概率 ----
    code, data = call("POST", "/api/answers/predict",
                      {"question": "明天股市会涨还是跌？", "n": 3})
    check("POST /api/answers/predict（规则兜底）",
          code == 200 and data.get("n") == 3 and len(data.get("answers", [])) == 3,
          "provider=%s totalP=%.2f" % (data.get("provider"), data.get("totalProbability", 0)))

    # 概率须归一化到 ~1
    probs = [a.get("probability", 0) for a in data.get("answers", [])]
    check("  概率已归一化", abs(sum(probs) - 1.0) < 0.01,
          "sum=%.4f" % sum(probs))

    # ---- 用户 ----
    code, data = call("POST", "/api/users", {"name": "自测用户", "email": "selftest@timeline.dev"})
    uid = (data.get("user") or {}).get("id")
    check("POST /api/users", code == 200 and bool(uid), "user_id=%s" % uid)

    code, data = call("GET", "/api/users")
    check("GET /api/users", code == 200 and data.get("total", 0) >= 1)

    code, data = call("GET", "/api/users/%s" % uid)
    check("GET /api/users/{id}", code == 200 and data["user"]["name"] == "自测用户")

    code, data = call("PATCH", "/api/users/%s" % uid, {"name": "自测用户改名"})
    check("PATCH /api/users/{id}", code == 200 and data["user"]["name"] == "自测用户改名")

    # ---- 用户导出 / 导入（兼容既有数据模型）----
    code, data = call("GET", "/api/users/%s/export" % uid)
    check("GET 导出", code == 200 and isinstance(data, dict))

    code, data = call("POST", "/api/users/%s/import" % uid,
                      {"goals": [], "records": [], "mode": "replace"})
    check("POST 导入", code == 200 and "counts" in data)

    # ---- 兼容层 ----
    code, _ = call("GET", "/api/state")
    check("GET /api/state 无 token -> 401", code == 401)

    code, data = call("PUT", "/api/state?user_id=legacy_demo", {"goals": [], "records": []})
    check("PUT /api/state（调试模式）", code == 200 and data.get("sub") == "legacy_demo")

    # ---- 后台鉴权 + 管理页面 ----
    from app.core import auth as _auth
    code, _, _ = call_full("POST", "/api/auth/login",
                           {"username": _auth.ADMIN_USER, "password": "wrong-pass"})
    check("POST /api/auth/login 错误密码 -> 401", code == 401)

    code, _, hdr = call_full("POST", "/api/auth/login",
                             {"username": _auth.ADMIN_USER, "password": _auth.ADMIN_PASS})
    has_cookie = any(h.lower() == "set-cookie" for h in hdr)
    check("POST /api/auth/login 正确密码 -> 200 + Set-Cookie", code == 200 and has_cookie,
          "user=%s" % _auth.ADMIN_USER)

    code, _, _ = call_full("GET", "/")
    check("GET / 未登录 -> 302 跳登录", code == 302)

    code, _, _ = call_full("GET", "/login")
    check("GET /login -> 200 返回管理页", code == 200)

    # ---- 后台管理接口（需登录）：等级 / 金币 / 投票 / 删除 ----
    code, data = call("POST", "/api/users", {"name": "管理测试用户"})
    muid = (data.get("user") or {}).get("id")
    check("POST /api/users（管理用）", code == 200 and bool(muid))

    code, _ = call_auth("GET", "/api/admin/users")
    check("GET /api/admin/users 未登录 -> 401", code == 401)

    # 登录拿 cookie
    _, _, hdr = call_full("POST", "/api/auth/login",
                          {"username": _auth.ADMIN_USER, "password": _auth.ADMIN_PASS})
    ck = hdr.get("Set-Cookie")

    code, data = call_auth("GET", "/api/admin/users", cookie=ck)
    check("GET /api/admin/users 登录后 -> 200", code == 200 and "users" in data)

    code, data = call_auth("POST", "/api/admin/users/%s/level" % muid, {"level": 5}, cookie=ck)
    check("POST 设置等级 -> 200 level=5", code == 200 and data.get("level") == 5,
          "level=%s" % data.get("level"))

    code, data = call_auth("POST", "/api/admin/users/%s/coins" % muid, {"coins": 100}, cookie=ck)
    check("POST 设置金币 -> 200 coins=100", code == 200 and data.get("coins") == 100,
          "coins=%s" % data.get("coins"))

    code, data = call_auth("POST", "/api/admin/users/%s/votes" % muid,
                          {"question": "喜欢哪个?", "choice": "A"}, cookie=ck)
    check("POST 记录投票 -> 200", code == 200 and data.get("votesCount") == 1)

    code, data = call_auth("GET", "/api/admin/users/%s/votes" % muid, cookie=ck)
    check("GET 投票记录 -> 200 且含 1 条", code == 200 and data.get("count") == 1)

    code, data = call_auth("DELETE", "/api/admin/users/%s" % muid, cookie=ck)
    check("DELETE 删除用户 -> 200", code == 200 and data.get("removed") == muid)

    # ---- 后台管理接口（需登录）：LLM Provider 管理（新增/编辑/设默认/测试/删除 + 实时生效）----
    code, _ = call_auth("GET", "/api/admin/providers")
    check("GET /api/admin/providers 未登录 -> 401", code == 401)

    code, data = call_auth("GET", "/api/admin/providers", cookie=ck)
    has_echo = code == 200 and isinstance(data.get("providers"), list) \
        and any(p["id"] == "echo" for p in data["providers"])
    check("GET /api/admin/providers 登录后 -> 200 含 echo", has_echo)

    code, data = call_auth("POST", "/api/admin/providers",
                           {"name": "自测 Provider", "type": "openai",
                            "baseUrl": "https://example.com/v1", "model": "test-model",
                            "isDefault": True}, cookie=ck)
    pid = data.get("id")
    check("POST 新增 Provider -> 200", code == 200 and bool(pid), "id=%s" % pid)

    # 实时生效：无需重启，/health 的默认 Provider 应已切到新建的 provider
    code, hdata = call("GET", "/health")
    check("实时生效：/health 默认 Provider 已切换",
          hdata.get("activeProvider") == pid, "active=%s" % hdata.get("activeProvider"))

    code, data = call_auth("PUT", "/api/admin/providers/%s" % pid,
                           {"name": "自测改名", "baseUrl": "https://other.com/v1"}, cookie=ck)
    check("PUT 更新 Provider -> 200", code == 200 and data.get("name") == "自测改名")

    code, data = call_auth("POST", "/api/admin/providers/%s/default" % pid, {}, cookie=ck)
    check("POST 设为默认 -> 200", code == 200 and data.get("defaultId") == pid)

    code, data = call_auth("POST", "/api/admin/providers/%s/test" % pid, {}, cookie=ck)
    check("POST 测试连通性 -> 200 无 Key 返回 no-api-key",
          code == 200 and data.get("ok") is False and data.get("reason") == "no-api-key")

    # echo 不可删除
    code, _ = call_auth("DELETE", "/api/admin/providers/echo", cookie=ck)
    check("DELETE echo -> 400 不可删除", code == 400)

    code, data = call_auth("DELETE", "/api/admin/providers/%s" % pid, cookie=ck)
    check("DELETE 删除 Provider -> 200", code == 200 and data.get("removed") == pid)

    # 回退默认到 echo，保证后续测试与真实运行一致
    call_auth("POST", "/api/admin/providers/echo/default", {}, cookie=ck)

    # ---- 清理 ----
    code, _ = call("DELETE", "/api/users/%s" % uid)
    check("DELETE /api/users/{id}", code == 200)

    httpd.shutdown()
    print("\n通过 %d 项，失败 %d 项" % (passed, failed))
    return 0 if failed == 0 else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="aiservice · Timeline 的 Python 侧服务")
    parser.add_argument("--host", default=config.HOST)
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--data-dir", dest="data_dir")
    parser.add_argument("--log", dest="log_level")
    parser.add_argument("--routes", action="store_true", help="只打印接口清单")
    parser.add_argument("--selftest", action="store_true", help="起临时服务跑一遍所有接口")
    parser.add_argument("--logs", type=int, nargs="?", const=50, metavar="N",
                        help="打印最近 N 行日志")
    args = parser.parse_args(argv)

    if args.data_dir:
        config.DATA_DIR = args.data_dir
        config.LOG_DIR = os.path.join(args.data_dir, "logs")
    setup_logging(args.log_level)

    if args.logs is not None:
        path = log_path()
        print("日志文件:", path or "（未启用文件日志）")
        for line in tail_logs(args.logs):
            print(line)
        return 0

    if args.selftest:
        return selftest()

    router = build_router()
    if args.routes:
        print_routes(router)
        return 0

    serve(router, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
