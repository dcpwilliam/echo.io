"""答案预测接口：给定问题和答案数量 n，返回最可能的 n 个答案及各自成立的概率。"""
from ..core.errors import BadRequest
from ..services import answer_service


def register(router):
    @router.post("/api/answers/predict")
    def predict(req):
        """最可能的 n 个答案 + 概率。body: { question, n?, use_llm? }"""
        body = req.json(default={})
        n = body.get("n")
        if isinstance(n, str):
            try:
                n = int(n)
            except ValueError:
                n = None
        elif not isinstance(n, int):
            n = None
        return answer_service.predict(
            body.get("question", ""),
            n=n,
            use_llm=bool(body.get("use_llm")),
            provider=body.get("provider"),
        )

    return router
