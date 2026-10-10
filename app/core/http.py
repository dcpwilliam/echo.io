"""Request / Response 封装，屏蔽掉 http.server 的裸接口。"""
import json
from urllib.parse import urlparse, parse_qs


class Request:
    def __init__(self, method, path, query, headers, body):
        self.method = method
        self.path = path
        self.query = query          # {key: value}，多值只取第一个
        self.headers = headers      # 小写 key 的 dict
        self.body = body            # bytes

    @classmethod
    def from_handler(cls, handler, body):
        parsed = urlparse(handler.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}
        headers = {k.lower(): v for k, v in handler.headers.items()}
        return cls(handler.command.upper(), parsed.path, query, headers, body)

    def json(self, default=None):
        """解析 JSON body；解析失败且给了 default 就返回 default，否则抛 400。"""
        if not self.body:
            if default is not None:
                return default
            from .errors import BadRequest
            raise BadRequest("请求体为空")
        try:
            return json.loads(self.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            if default is not None:
                return default
            from .errors import BadRequest
            raise BadRequest("请求体不是合法 JSON")

    def arg(self, name, default=None, cast=None):
        """读 query 参数，可带类型转换。"""
        val = self.query.get(name, default)
        if cast and val is not None:
            try:
                val = cast(val)
            except (TypeError, ValueError):
                from .errors import BadRequest
                raise BadRequest("参数 %s 格式不对" % name)
        return val

    def bearer_token(self):
        auth = self.headers.get("authorization", "")
        return auth.replace("Bearer ", "").replace("bearer ", "").strip()


class Response:
    def __init__(self, status=200, body=b"", headers=None, content_type="application/json; charset=utf-8"):
        self.status = status
        self.body = body
        self.headers = headers or {}
        self.content_type = content_type

    @classmethod
    def json(cls, data, status=200, headers=None):
        body = json.dumps(data, ensure_ascii=False, default=_fallback).encode("utf-8")
        return cls(status, body, headers)

    @classmethod
    def text(cls, text, status=200, content_type="text/plain; charset=utf-8"):
        return cls(status, text.encode("utf-8"), content_type=content_type)

    @classmethod
    def empty(cls, status=204):
        return cls(status, b"")


def _fallback(obj):
    """让 set / 自定义对象也能被 json 序列化。"""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)
