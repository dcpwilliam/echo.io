"""本地规则 Provider：不联网、不需要 Key，永远可用。

它把 analyzer 的规则结果包成与 LLM 一致的 JSON 结构，
这样上层代码在「没配 Key」和「配了 Key」两种情况下拿到的数据形状是一样的。
"""
import json

from ..domain import analyzer
from .base import LLMProvider


class EchoProvider(LLMProvider):
    name = "echo"
    kind = "echo"
    available = True

    def complete(self, system, user, expect_json=False, temperature=None, max_tokens=None):
        # 从 user 段里把「用户说：xxx」抠出来，走本地规则分析
        text = user or ""
        for marker in ("用户说：", "原话："):
            if marker in text:
                text = text.split(marker, 1)[1].split("\n", 1)[0]
                break
        result = analyzer.analyze(text.strip())
        if not expect_json:
            return "%s\n\n下一步：%s" % (
                result["summary"],
                "；".join(s["title"] for s in result["suggestions"]),
            )
        return json.dumps({
            "intent": result["intent"],
            "intentLabel": result["intentLabel"],
            "category": result["category"]["key"],
            "summary": result["summary"],
            "goalTitle": result["suggestedTitle"],
            "criterion": result["criterion"],
            "suggestions": result["suggestions"],
            "provider": "echo",
        }, ensure_ascii=False)
