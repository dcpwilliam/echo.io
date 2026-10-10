"""极简路由：支持路径参数 {id}、方法匹配、自动生成路由清单。"""
import re

from .errors import NotFound

_PARAM = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class Route:
    __slots__ = ("method", "path", "handler", "doc", "pattern", "names")

    def __init__(self, method, path, handler, doc=""):
        self.method = method
        self.path = path
        self.handler = handler
        self.doc = doc or (handler.__doc__ or "").strip().split("\n")[0]
        self.names = _PARAM.findall(path)
        # /api/users/{id} -> ^/api/users/([^/]+)$
        regex = "^" + _PARAM.sub(r"([^/]+)", path.replace(".", r"\.")) + "$"
        self.pattern = re.compile(regex)

    def match(self, path):
        m = self.pattern.match(path)
        if not m:
            return None
        return {name: _unquote(val) for name, val in zip(self.names, m.groups())}


def _unquote(s):
    from urllib.parse import unquote
    return unquote(s)


class Router:
    def __init__(self):
        self.routes = []

    # ---------- 注册 ----------
    def _add(self, method, path):
        def deco(fn):
            self.routes.append(Route(method, path, fn))
            return fn
        return deco

    def get(self, path):
        return self._add("GET", path)

    def post(self, path):
        return self._add("POST", path)

    def put(self, path):
        return self._add("PUT", path)

    def patch(self, path):
        return self._add("PATCH", path)

    def delete(self, path):
        return self._add("DELETE", path)

    def mount(self, other):
        """把子路由模块的路由合并进来。"""
        self.routes.extend(other.routes)

    # ---------- 匹配 ----------
    def resolve(self, method, path):
        for route in self.routes:
            if route.method != method:
                continue
            params = route.match(path)
            if params is not None:
                return route, params
        raise NotFound("没有这个接口: %s %s" % (method, path))

    def listing(self):
        """路由清单，供 /api/info 输出。"""
        out = []
        for r in self.routes:
            out.append({
                "method": r.method,
                "path": r.path,
                "doc": r.doc,
            })
        return out
