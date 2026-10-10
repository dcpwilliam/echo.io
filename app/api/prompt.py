"""Prompt 处理接口：模板列表 / 渲染 / 一句话分析 / 自由补全。"""
from ..core.errors import BadRequest
from ..services import prompt_service


def register(router):
    @router.get("/api/prompt/templates")
    def templates(req):
        """列出所有可用模板与变量。"""
        return prompt_service.list_templates()

    @router.post("/api/prompt/render")
    def render(req):
        """只渲染模板，不调模型。body: { template, variables }"""
        body = req.json(default={})
        name = body.get("template") or body.get("name")
        if not name:
            raise BadRequest("缺少 template")
        return prompt_service.render(name, body.get("variables") or {})

    @router.post("/api/prompt/analyze")
    def analyze(req):
        """处理一句话。body: { text, user_id, use_llm }"""
        body = req.json(default={})
        return prompt_service.analyze(
            body.get("text", ""),
            user_id=body.get("user_id") or body.get("userId"),
            use_llm=bool(body.get("use_llm")),
            provider=body.get("provider"),
        )

    @router.post("/api/prompt/analyze-image")
    def analyze_image(req):
        """看懂一张图。body: { image(base64), mime?, text?, user_id? }"""
        body = req.json(default={})
        return prompt_service.describe_image(
            body.get("image", ""),
            mime=body.get("mime") or "image/jpeg",
            hint=body.get("text") or body.get("hint") or "",
            user_id=body.get("user_id") or body.get("userId"),
            provider=body.get("provider"),
        )

    @router.post("/api/prompt/complete")
    def complete(req):
        """自由补全。body: { template, variables } 或 { system, user }"""
        body = req.json(default={})
        return prompt_service.complete(
            name=body.get("template") or body.get("name"),
            variables=body.get("variables"),
            system=body.get("system"),
            user=body.get("user"),
            provider=body.get("provider"),
        )

    return router
