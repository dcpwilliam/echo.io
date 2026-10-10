"""统一异常：API 层只抛 ApiError，由 server 转成 JSON 错误响应。"""


class ApiError(Exception):
    def __init__(self, message, status=400, detail=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.detail = detail

    def to_dict(self):
        out = {"error": self.message}
        if self.detail is not None:
            out["detail"] = self.detail
        return out


class NotFound(ApiError):
    def __init__(self, message="not found", detail=None):
        super().__init__(message, 404, detail)


class BadRequest(ApiError):
    def __init__(self, message="bad request", detail=None):
        super().__init__(message, 400, detail)


class Unauthorized(ApiError):
    def __init__(self, message="unauthorized", detail=None):
        super().__init__(message, 401, detail)
