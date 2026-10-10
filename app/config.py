"""配置：全部可用环境变量覆盖，默认值开箱即用。

    AISERVICE_HOST       监听地址        默认 127.0.0.1
    AISERVICE_PORT       端口            默认 8100
    AISERVICE_DATA_DIR   数据目录        默认 ./data
    AISERVICE_STORAGE    存储后端        默认 sqlite（sqlite | json）
    AISERVICE_LOG        日志级别        默认 INFO
    LLM_PROVIDER         echo | openai   默认 echo（本地规则，不联网）
    LLM_BASE_URL         OpenAI 兼容地址 默认 https://api.deepseek.com/v1
    LLM_API_KEY          API Key         默认空（空则自动回落到 echo）
    LLM_MODEL            模型名          默认 deepseek-chat
    LLM_TIMEOUT          超时秒          默认 90
    LLM_MAX_TOKENS       最大生成 token   默认 1024
    LLM_JSON_MODE        是否发 response_format，默认 0（本机推理模型会卡死）
"""
import os

# app/config.py -> app/ -> aiservice/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env(name, default, cast=str):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return cast(raw)
    except (TypeError, ValueError):
        return default


class Config:
    HOST = _env("AISERVICE_HOST", "127.0.0.1")
    PORT = _env("AISERVICE_PORT", 8100, int)
    DATA_DIR = _env("AISERVICE_DATA_DIR", os.path.join(BASE_DIR, "data"))
    # 存储后端：sqlite（默认，单文件库，支持多进程并发锁）或 json（老的单文件方案）
    STORAGE_BACKEND = _env("AISERVICE_STORAGE", "sqlite")
    LOG_LEVEL = _env("AISERVICE_LOG", "INFO").upper()
    LOG_DIR = _env("AISERVICE_LOG_DIR", os.path.join(DATA_DIR, "logs"))

    # ---- LLM ----
    # 默认指向本机的 ollama / llama.cpp OpenAI 兼容端点（见 env.sh）
    LLM_PROVIDER = _env("LLM_PROVIDER", "echo")
    LLM_BASE_URL = _env("LLM_BASE_URL", "http://127.0.0.1:1337/v1")
    LLM_API_KEY = _env("LLM_API_KEY", "")
    LLM_MODEL = _env("LLM_MODEL", "LiquidAI/LFM2_5-2_6B-Q4_K_M")
    LLM_TIMEOUT = _env("LLM_TIMEOUT", 90, int)
    LLM_TEMPERATURE = _env("LLM_TEMPERATURE", 0.3, float)
    # 不是所有 OpenAI 兼容实现都认 response_format，报错时用 LLM_JSON_MODE=0 关掉。
    # 本机推理模型（LFM2.5）带 json_object 语法时会陷入无限 chain-of-thought，
    # 实测 content 直接为空、烧掉全部 token，所以默认关掉，靠正则兜底抽 JSON。
    LLM_JSON_MODE = _env("LLM_JSON_MODE", 0, int)
    LLM_MAX_TOKENS = _env("LLM_MAX_TOKENS", 2048, int)
    # 视觉模型：留空就用 LLM_MODEL。本机文本模型不带 mmproj，识图会失败并自动降级
    LLM_VISION_MODEL = _env("LLM_VISION_MODEL", "")

    # ---- 业务默认值 ----
    DEFAULT_WINDOW = _env("AISERVICE_WINDOW", 7, int)   # 时间线默认窗口天数
    MAX_MENTIONS = 20                                    # 单个目标保留的提及条数
    MAX_MESSAGES = 60                                    # 每个用户保留的会话条数

    @classmethod
    def public_dict(cls):
        """可以暴露给客户端的配置（不含任何密钥）。"""
        return {
            "host": cls.HOST,
            "port": cls.PORT,
            "dataDir": cls.DATA_DIR,
            "storage": cls.STORAGE_BACKEND,
            "llmProvider": cls.llm_provider(),
            "llmModel": cls.LLM_MODEL if cls.llm_provider() == "openai" else None,
            "window": cls.DEFAULT_WINDOW,
        }

    @classmethod
    def llm_provider(cls):
        """配了 key 才真的走 openai，否则一律本地规则。"""
        if cls.LLM_PROVIDER == "openai" and cls.LLM_API_KEY:
            return "openai"
        return "echo"


config = Config()
