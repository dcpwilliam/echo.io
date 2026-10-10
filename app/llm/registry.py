"""LLM Provider 注册表：动态管理 provider 配置，实时生效 + 持久化。

它是「provider 配置」的唯一真相来源，替代原来只能靠环境变量写死的 LLM_PROVIDER。

设计要点：
- 内存中持有 providers 列表与 defaultId；每次变更立即写盘到 data/llm_providers.json。
- llm.get_provider() 每次调用都按注册表现建实例，所以「改配置」天然实时生效，无需重启。
- 内置两个不可删的 provider：
    echo   —— 本地规则，永远可用、不联网、不需要 Key；
    openai —— 首次启动按 config 里的环境变量播种（LLM_BASE_URL / API_KEY / MODEL …）。
- 管理员可在后台「概览」里新增 / 编辑 / 删除任意 openai 兼容 provider（DeepSeek、通义、moonshot、
  Ollama 本地v1 等），并指定哪个是默认。
"""
import json
import os
import threading
import uuid

from ..config import config

_PATH = None          # 延迟计算，确保能拿到 config.DATA_DIR 的最新值
_LOCK = threading.Lock()
_CACHE = {"providers": None, "defaultId": None}


def _path():
    d = config.DATA_DIR
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return os.path.join(d, "llm_providers.json")


def _seed():
    """按 config 环境变量播种默认 providers（仅在没有持久化文件时）。"""
    openai_default = config.llm_provider() == "openai"
    return {
        "version": 1,
        "defaultId": "openai" if openai_default else "echo",
        "providers": [
            {
                "id": "echo",
                "name": "本地规则（免 Key）",
                "type": "echo",
                "enabled": True,
                "isDefault": not openai_default,
            },
            {
                "id": "openai",
                "name": "OpenAI 兼容（环境变量）",
                "type": "openai",
                "baseUrl": config.LLM_BASE_URL,
                "apiKey": config.LLM_API_KEY,
                "model": config.LLM_MODEL,
                "visionModel": config.LLM_VISION_MODEL,
                "temperature": config.LLM_TEMPERATURE,
                "maxTokens": config.LLM_MAX_TOKENS,
                "jsonMode": bool(config.LLM_JSON_MODE),
                "timeout": config.LLM_TIMEOUT,
                "enabled": True,
                "isDefault": openai_default,
            },
        ],
    }


def _load():
    """读盘；文件不存在或坏掉则用种子。结果缓存到 _CACHE。"""
    p = _path()
    data = None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("providers"), list):
        data = _seed()
        _write(data)
    # 规范化：确保每个 provider 字段完整
    providers = [_normalize(p) for p in data.get("providers", [])]
    if not any(p["id"] == "echo" for p in providers):
        providers.insert(0, _normalize(_seed()["providers"][0]))
    default_id = data.get("defaultId")
    if not default_id or not any(p["id"] == default_id for p in providers):
        default_id = next((p["id"] for p in providers if p.get("isDefault")), "echo")
    _CACHE["providers"] = providers
    _CACHE["defaultId"] = default_id
    return _CACHE


def _write(data):
    p = _path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)   # 原子替换，避免写到一半进程挂掉把文件写坏


def _normalize(p):
    """补齐字段并做类型规整，避免前端少传一个字段就炸。"""
    p = dict(p or {})
    p.setdefault("id", "p_" + uuid.uuid4().hex[:8])
    p.setdefault("name", p["id"])
    p.setdefault("type", "openai")
    p["type"] = "echo" if p.get("type") == "echo" else "openai"
    p["enabled"] = bool(p.get("enabled", True))
    p["isDefault"] = bool(p.get("isDefault", False))
    if p["type"] == "openai":
        p.setdefault("baseUrl", config.LLM_BASE_URL)
        p.setdefault("apiKey", "")
        p.setdefault("model", config.LLM_MODEL)
        p.setdefault("visionModel", "")
        try:
            p["temperature"] = float(p.get("temperature", config.LLM_TEMPERATURE))
        except (TypeError, ValueError):
            p["temperature"] = config.LLM_TEMPERATURE
        try:
            p["maxTokens"] = int(p.get("maxTokens", config.LLM_MAX_TOKENS))
        except (TypeError, ValueError):
            p["maxTokens"] = config.LLM_MAX_TOKENS
        p["jsonMode"] = bool(p.get("jsonMode", bool(config.LLM_JSON_MODE)))
        try:
            p["timeout"] = int(p.get("timeout", config.LLM_TIMEOUT))
        except (TypeError, ValueError):
            p["timeout"] = config.LLM_TIMEOUT
    else:
        # echo 类型忽略联网字段
        for k in ("baseUrl", "apiKey", "model", "visionModel", "temperature", "maxTokens", "jsonMode", "timeout"):
            p.pop(k, None)
    return p


def _mask(p, reveal=False):
    """列表/单条返回时脱敏 apiKey；reveal=True 才回明文。"""
    p = dict(p)
    if p.get("type") == "openai":
        has = bool(p.get("apiKey"))
        p["hasApiKey"] = has
        if not reveal:
            p["apiKey"] = "***" if has else ""
    return p


# ---------------- 对外 API ----------------

def list_providers(reveal=False):
    with _LOCK:
        store = _load()
        return {
            "defaultId": store["defaultId"],
            "providers": [_mask(p, reveal) for p in store["providers"]],
        }


def get(id, reveal=False):
    """返回带明文 apiKey 的原始配置（供构建 provider 实例 / 编辑回填用）。"""
    with _LOCK:
        store = _load()
        for p in store["providers"]:
            if p["id"] == id:
                return dict(p)
        return None


def get_default_id():
    with _LOCK:
        return _load()["defaultId"]


def count():
    with _LOCK:
        return len(_load()["providers"])


def _validate(cfg):
    """返回 (ok, errors)。"""
    errs = []
    if cfg.get("type") not in ("echo", "openai"):
        errs.append("type 只能是 echo 或 openai")
    if cfg.get("type") == "openai":
        if not str(cfg.get("baseUrl") or "").strip():
            errs.append("openai 类型必须填写 baseUrl")
        if not str(cfg.get("model") or "").strip():
            errs.append("openai 类型必须填写 model")
    return (len(errs) == 0, errs)


def create(cfg):
    """新增 provider；id 缺省自动生成。返回规范化后的配置（脱敏）。"""
    cfg = dict(cfg or {})
    cfg.pop("id", None)  # 强制重新生成，避免冲突
    pid = "p_" + uuid.uuid4().hex[:8]
    cfg["id"] = pid
    ok, errs = _validate(cfg)
    if not ok:
        raise ValueError("；".join(errs))
    norm = _normalize(cfg)
    with _LOCK:
        store = _load()
        store["providers"].append(norm)
        if norm.get("isDefault"):
            _apply_default(store, pid)
        _write(store)
    return _mask(norm)


def update(id, patch):
    """局部合并更新；apiKey 留空表示保留原值（不清空）。返回脱敏配置。"""
    with _LOCK:
        store = _load()
        idx = next((i for i, p in enumerate(store["providers"]) if p["id"] == id), None)
        if idx is None:
            raise KeyError("provider 不存在: %s" % id)
        cur = dict(store["providers"][idx])
        # 编辑表单若把 apiKey 留空但原本有值，则保留原值
        if "apiKey" in patch and patch.get("apiKey") == "" and cur.get("apiKey"):
            patch = dict(patch)
            patch["apiKey"] = cur["apiKey"]
        merged = dict(cur)
        merged.update({k: v for k, v in patch.items() if k != "id"})
        ok, errs = _validate(merged)
        if not ok:
            raise ValueError("；".join(errs))
        norm = _normalize(merged)
        store["providers"][idx] = norm
        if norm.get("isDefault"):
            _apply_default(store, id)
        _write(store)
    return _mask(norm)


def delete(id):
    """删除 provider；echo 不可删。若删的是默认，回退到 echo。"""
    if id == "echo":
        raise ValueError("echo 是内置 provider，不可删除")
    with _LOCK:
        store = _load()
        before = len(store["providers"])
        store["providers"] = [p for p in store["providers"] if p["id"] != id]
        if len(store["providers"]) == before:
            raise KeyError("provider 不存在: %s" % id)
        if store["defaultId"] == id:
            store["defaultId"] = "echo"
            for p in store["providers"]:
                if p["id"] == "echo":
                    p["isDefault"] = True
        _write(store)
    return {"removed": id}


def set_default(id):
    """把某个 provider 设为默认（同时清掉其它人的默认标记）。"""
    with _LOCK:
        store = _load()
        if not any(p["id"] == id for p in store["providers"]):
            raise KeyError("provider 不存在: %s" % id)
        _apply_default(store, id)
        _write(store)
    return {"defaultId": id}


def _apply_default(store, id):
    for p in store["providers"]:
        p["isDefault"] = (p["id"] == id)
    store["defaultId"] = id
