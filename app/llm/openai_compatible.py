"""OpenAI 兼容 Provider：DeepSeek / 通义 /  moonshot / 本地 Ollama(v1) 都能用。

只依赖标准库 urllib。没配 API Key 时 available=False，上层会自动回落到 echo。
"""
import json
import urllib.error
import urllib.request

from ..config import config
from .base import LLMProvider


_VISION_SYSTEM = (
    "你是一个目标管理助手。用户会发来一张图（截图、单据、运动记录、聊天记录等）。\n"
    "你要判断这张图跟哪件正在推进的事有关，并用一句中文说清楚。\n"
    "只输出这一句话，不要解释，不要列表，不要 JSON。"
)

_VISION_PROMPT = (
    "看图后用一句话说明：这张图记录了什么、跟什么事有关。"
    "尽量带上图里能看清的关键数字（金额、里程、天数、体重等）。"
    "如果实在看不出来，就说「看不出来」。"
)


class OpenAICompatibleProvider(LLMProvider):
    name = "openai"
    kind = "openai"   # 与 echo 区分：只有 kind=="openai" 且 available 才是真·联网模型

    def __init__(self, base_url=None, api_key=None, model=None, timeout=None,
                 temperature=None, max_tokens=None, json_mode=None, vision_model=None):
        self.base_url = (base_url or config.LLM_BASE_URL).rstrip("/")
        self.api_key = api_key or config.LLM_API_KEY
        self.model = model or config.LLM_MODEL
        self.timeout = timeout or config.LLM_TIMEOUT
        # 逐 provider 可覆盖的参数（默认取 config，registry 里可逐条覆盖）
        self.temperature = config.LLM_TEMPERATURE if temperature is None else temperature
        self.max_tokens = config.LLM_MAX_TOKENS if max_tokens is None else max_tokens
        self.json_mode = config.LLM_JSON_MODE if json_mode is None else json_mode
        self.vision_model = vision_model or config.LLM_VISION_MODEL

    @property
    def available(self):
        return bool(self.api_key)

    def complete(self, system, user, expect_json=False, temperature=None, max_tokens=None):
        if not self.available:
            raise RuntimeError("未配置 LLM_API_KEY")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system or ""},
                {"role": "user", "content": user or ""},
            ],
            "temperature": self.temperature if temperature is None else temperature,
        }
        # 一定要给上限：推理型模型没有 max_tokens 会一直写 chain-of-thought 直到超时
        payload["max_tokens"] = self.max_tokens if max_tokens is None else max_tokens
        # 主流兼容端都支持；ollama / llama.cpp 有些实现会报错，用 LLM_JSON_MODE=0 关掉。
        # 本机 LFM2.5 带 json_object 语法会陷入死循环，默认关。
        if self.json_mode:
            payload["response_format"] = {"type": "json_object" if expect_json else "text"}

        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:300]
            raise RuntimeError("LLM 返回 %s: %s" % (e.code, detail))
        except urllib.error.URLError as e:
            raise RuntimeError("连不上 LLM 服务: %s" % e.reason)

        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("LLM 返回结构异常: %s" % json.dumps(body, ensure_ascii=False)[:300])

    def describe_image(self, image_b64, mime="image/jpeg", hint="", system=None, max_tokens=None):
        """看图说话。返回一句话描述；模型不支持视觉能力时抛 RuntimeError。

        只支持单张图。多模态请求不走 complete()，因为 content 是数组而不是字符串。
        """
        if not self.available:
            raise RuntimeError("未配置 LLM_API_KEY")

        content = []
        if hint:
            content.append({"type": "text", "text": hint})
        content.append({"type": "text", "text": _VISION_PROMPT})
        content.append({
            "type": "image_url",
            "image_url": {"url": "data:%s;base64,%s" % (mime or "image/jpeg", image_b64)},
        })

        payload = {
            "model": self.vision_model or self.model,
            "messages": [
                {"role": "system", "content": system or _VISION_SYSTEM},
                {"role": "user", "content": content},
            ],
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }

        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:300]
            raise RuntimeError(detail)
        except urllib.error.URLError as e:
            raise RuntimeError("连不上 LLM 服务: %s" % e.reason)

        try:
            text = (body["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("LLM 返回结构异常")
        if not text:
            raise RuntimeError("模型没有给出任何描述")
        return text
