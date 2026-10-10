"""LLM 适配层：统一接口，echo（本地规则，默认）与 openai 兼容两种实现。

选择逻辑在 registry + get_provider()：默认 provider 由注册表决定，管理员可在后台实时改。
每次 get_provider() 都按注册表当前配置「现建」实例，因此修改 provider 配置后下一次请求立即生效，
不需要重启服务，也没有旧缓存污染的问题。
"""
from ..config import config
from . import registry
from .base import LLMProvider
from .echo_provider import EchoProvider
from .openai_compatible import OpenAICompatibleProvider


def get_active_provider_id():
    """当前默认 provider 的 id（echo / openai / 自定义 id）。"""
    return registry.get_default_id()


def get_provider(name=None):
    """返回 name 对应的 provider 实例；name 为空则取注册表默认。

    - echo：永远返回本地规则 provider。
    - openai 兼容类型：按注册表里的 baseUrl/apiKey/model 等现建实例；没配 Key 或禁用时自动回落 echo。
    - 未知的 id：回落 echo。
    """
    name = name or registry.get_default_id()
    if name == "echo":
        return EchoProvider()
    cfg = registry.get(name)
    if cfg and cfg.get("type") == "openai":
        if not cfg.get("enabled", True):
            return EchoProvider()
        provider = OpenAICompatibleProvider(
            base_url=cfg.get("baseUrl") or config.LLM_BASE_URL,
            api_key=cfg.get("apiKey") or config.LLM_API_KEY,
            model=cfg.get("model") or config.LLM_MODEL,
            timeout=cfg.get("timeout") or config.LLM_TIMEOUT,
        )
        # 用注册表里的逐 provider 覆盖项，覆盖 config 默认值
        provider.temperature = cfg.get("temperature", config.LLM_TEMPERATURE)
        provider.max_tokens = cfg.get("maxTokens", config.LLM_MAX_TOKENS)
        provider.json_mode = cfg.get("jsonMode", bool(config.LLM_JSON_MODE))
        provider.vision_model = cfg.get("visionModel") or config.LLM_VISION_MODEL
        if not provider.available:
            # 没配 Key：和「没开 LLM」一样走本地规则
            return EchoProvider()
        provider.name = cfg["id"]   # 让响应里的 provider 字段显示真实 id
        return provider
    return EchoProvider()


def complete(system, user, expect_json=False, provider=None, **kw):
    return get_provider(provider).complete(system, user, expect_json=expect_json, **kw)


def complete_json(system, user, provider=None, **kw):
    return get_provider(provider).complete_json(system, user, **kw)


def describe_image(image_b64, mime="image/jpeg", hint="", provider=None, **kw):
    """识图。返回一句话描述；不可用时抛 RuntimeError。"""
    return get_provider(provider).describe_image(image_b64, mime=mime, hint=hint, **kw)


__all__ = ["LLMProvider", "EchoProvider", "OpenAICompatibleProvider",
           "get_active_provider_id", "get_provider",
           "complete", "complete_json", "describe_image"]
