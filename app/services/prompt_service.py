"""Prompt 处理服务：列模板 / 渲染 / 一句话分析 / 自由补全。

对外只有四个函数，内部串起 prompts 模板库 + llm provider + 用户上下文。
"""
import json
import logging
import time

from .. import llm
from ..config import config
from ..domain import analyzer
from ..prompts import templates
from ..storage import load
from ..storage import schema as _schema

log = logging.getLogger("aiservice.prompt")


def list_templates():
    return {"templates": templates.names(), "provider": llm.get_provider().name}


def render(name, variables=None):
    rendered = templates.render(name, variables)
    return rendered


def _goal_brief(goals, limit=5):
    if not goals:
        return "（暂无）"
    return "\n".join("- %s（%s%%）" % (g.get("title"), g.get("progress", 0)) for g in goals[:limit])


def analyze(text, user_id=None, use_llm=False, provider=None):
    """处理一句话。

    use_llm=False（默认）走本地规则；True 且配了 Key 才真的调模型。
    两种路径返回结构一致，前端不用分支。
    """
    text = (text or "").strip()
    if not text:
        from ..core.errors import BadRequest
        raise BadRequest("text 不能为空")

    goals = []
    if user_id:
        goals = load(user_id).get("goals") or []

    started = time.time()
    if not use_llm:
        result = analyzer.analyze(text)
        result["provider"] = "echo"
        result["matchedGoalId"] = _match(text, result, goals)
        log.info("analyze 规则引擎 | user=%s len=%d 意图=%s 领域=%s 耗时=%.1fms",
                 user_id or "-", len(text), result["intent"],
                 result["category"]["key"], (time.time() - started) * 1000)
        return result

    # 规则结果先算出来：模型出错 / 输出无效时直接顶上，接口不返回 500
    fallback = analyzer.analyze(text)

    # 没真正的大模型可用（provider 是 echo，或 openai 兼容但没配 Key）：直接走规则
    prov = llm.get_provider(provider)
    if prov.kind != "openai" or not prov.available:
        result = analyzer.analyze(text)
        result["provider"] = "echo"
        result["matchedGoalId"] = _match(text, result, goals)
        log.info("analyze 无可用大模型（provider=%s），走规则 | user=%s len=%d",
                 prov.name, user_id or "-", len(text))
        return result

    rendered = templates.render("analyze", {"text": text, "goals": _goal_brief(goals)})
    pname = prov.name
    log.info("analyze 调用模型 | user=%s provider=%s model=%s len=%d",
             user_id or "-", pname, getattr(config, "LLM_MODEL", "?"), len(text))
    try:
        data = llm.complete_json(rendered["system"], rendered["user"], provider=provider)
    except Exception as e:  # 超时 / 连不上 / 返回结构异常，一律降级
        log.warning("analyze 模型调用失败（%s），回退本地规则 | user=%s provider=%s",
                    e, user_id or "-", pname)
        data = dict(fallback)
        data["provider"] = "echo"
        data["llmFallback"] = True
        data["llmFallbackReason"] = "模型调用失败: %s" % e
        data["matchedGoalId"] = _match(text, fallback, goals)
        return data

    log.info("analyze 模型返回 | user=%s 耗时=%.1fms keys=%s",
             user_id or "-", (time.time() - started) * 1000, ",".join(sorted(data.keys())))
    log.debug("analyze 原始输出 | %s", json.dumps(data, ensure_ascii=False)[:600])

    bad = _placeholder_reason(data)
    if bad:
        # 小模型常见毛病：把模板里的字段说明/示例原样抄回来。
        # 这种输出对用户毫无价值，直接整体回退到本地规则。
        log.warning("analyze 模型输出无效（%s），回退本地规则 | user=%s provider=%s",
                    bad, user_id or "-", pname)
        data = dict(fallback)
        data["llmFallback"] = True
        data["llmFallbackReason"] = bad
        data["provider"] = "echo"
    else:
        data["provider"] = pname
        # 规则结果兜底字段，避免模型少给
        for key in ("intent", "intentLabel", "summary", "goalTitle", "criterion", "suggestions"):
            if not data.get(key):
                data[key] = fallback[key]
        data["suggestions"] = _sanitize_suggestions(data.get("suggestions"), fallback["suggestions"])
    if isinstance(data.get("category"), str):
        from ..domain import categories
        data["category"] = categories.find(data["category"])
    if not isinstance(data.get("category"), dict):
        data["category"] = fallback["category"]
    data["matchedGoalId"] = _match(text, fallback, goals)
    return data


# 模板里出现过的占位文字，模型照抄就判无效
_PLACEHOLDERS = ("怎么算达成", "下一步", "为什么", "一句话理解", "中文意图标签",
                 "归入或新建的目标标题", "说人话")


def _placeholder_reason(data):
    """返回问题原因，正常返回 None。"""
    if not isinstance(data, dict):
        return "返回不是对象"
    if "raw" in data and len(data) <= 1:
        return "返回的不是合法 JSON"
    for key in ("criterion", "summary", "goalTitle"):
        val = (data.get(key) or "").strip()
        if val in _PLACEHOLDERS:
            return "%s 是占位文字「%s」" % (key, val)
    sugg = data.get("suggestions")
    if isinstance(sugg, list):
        for s in sugg:
            if not isinstance(s, dict):
                continue
            if (s.get("title") or "").strip() in _PLACEHOLDERS:
                return "suggestion.title 是占位文字「%s」" % s.get("title")
            if (s.get("tip") or "").strip() in _PLACEHOLDERS:
                return "suggestion.tip 是占位文字「%s」" % s.get("tip")
    # 只要还有点实质内容（有 summary），就算截断也认；全空才判无效
    if not (data.get("suggestions") or []) and not (data.get("summary") or "").strip():
        return "内容基本为空"
    return None


# 模型可能用中文/近义词描述难度，统一归到 easy/medium/hard（定义见 schema.DIFFICULTY_ALIAS）


def _clean_steps(raw):
    """模型给的步骤洗成字符串数组，最多 5 条，每条截断。"""
    if not isinstance(raw, list):
        return []
    out = [str(x).strip()[:_schema.MAX_STEP_LEN] for x in raw if str(x).strip()]
    return out[:_schema.MAX_STEPS]


def _sanitize_suggestions(sugg, fallback_sugg):
    """模型给的建议常常缺字段 / minutes 是字符串，统一洗一遍；不够就补本地的。"""
    out = []
    for s in (sugg or []):
        if not isinstance(s, dict):
            continue
        title = (s.get("title") or s.get("name") or "").strip()
        if not title:
            continue
        try:
            minutes = int(s.get("minutes") or 15)
        except (TypeError, ValueError):
            minutes = 15
        difficulty = _schema.difficulty_meta(s.get("difficulty"))["key"]
        detail = (s.get("detail") or "").strip()[:120]
        steps = _clean_steps(s.get("steps"))
        # 没给步骤时，用 tip 兜底成一条，保证卡片有「怎么做」
        if not steps and (s.get("tip") or s.get("why")):
            steps = [(s.get("tip") or s.get("why")).strip()[:_schema.MAX_STEP_LEN]]
        out.append({
            "title": title[:24],
            "detail": detail,
            "difficulty": difficulty,
            "steps": steps,
            "tip": (s.get("tip") or s.get("why") or "").strip()[:60] or "先做起来，比想清楚更重要",
            "minutes": max(5, min(240, minutes)),
        })
    for s in fallback_sugg or []:
        if len(out) >= 3:
            break
        if not any(x["title"] == s["title"] for x in out):
            out.append(s)
    return out[:3]


def _match(text, analysis, goals):
    from ..domain import goals as g
    hit = g.match_goal(text, analysis["category"]["key"], goals)
    return hit["goal"]["id"] if hit else None


def describe_image(image, mime="image/jpeg", hint="", user_id=None, provider=None):
    """看懂一张图，返回一句话描述。

    不是所有模型都带视觉能力（本机 LFM2.5 就不带，服务端会报
    "image input is not supported"）。这种情况返回 ok=False + needText=True，
    由前端引导用户补一句话，而不是抛 500。
    """
    import base64
    import binascii

    started = time.time()
    raw = (image or "").strip()
    if not raw:
        from ..core.errors import BadRequest
        raise BadRequest("缺少 image")

    # 允许直接传 data:image/xxx;base64, 前缀
    if raw.startswith("data:"):
        head, _, raw = raw.partition(",")
        mime = head.split(";")[0].replace("data:", "") or mime
    try:
        base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        from ..core.errors import BadRequest
        raise BadRequest("image 不是合法的 base64")

    pname = llm.get_provider(provider).name
    log.info("识图 | user=%s provider=%s model=%s 大小=%dKB hint=%d字",
             user_id or "-", pname, getattr(config, "LLM_VISION_MODEL", "") or getattr(config, "LLM_MODEL", "?"),
             len(raw) // 1024, len(hint or ""))
    try:
        text = llm.describe_image(raw, mime=mime or "image/jpeg", hint=hint, provider=provider)
    except Exception as e:
        msg = str(e)
        no_vision = ("not supported" in msg.lower()
                     or "mmproj" in msg.lower()
                     or "image input" in msg.lower()
                     or "不支持识图" in msg)
        log.warning("识图失败 | user=%s provider=%s 原因=%s",
                    user_id or "-", pname, msg[:160])
        return {
            "ok": False,
            "needText": True,
            "text": "",
            "provider": pname,
            "reason": "no-vision" if no_vision else "error",
            "detail": msg[:200],
            "hint": "当前模型不支持识图，补一句话说明" if no_vision else "识图失败，补一句话说明",
        }

    log.info("识图完成 | user=%s 耗时=%.1fms 结果=%s",
             user_id or "-", (time.time() - started) * 1000, text[:60])
    if not text or "看不出来" in text:
        return {
            "ok": False,
            "needText": True,
            "text": text,
            "provider": pname,
            "reason": "unclear",
            "hint": "这张图看不出在说什么，补一句话吧",
        }
    return {"ok": True, "needText": False, "text": text, "provider": pname}


def complete(name=None, variables=None, system=None, user=None, provider=None):
    """自由补全：可以传模板名 + 变量，也可以直接给 system/user。"""
    started = time.time()
    if name:
        rendered = templates.render(name, variables)
        system, user, expect_json = rendered["system"], rendered["user"], rendered["expectJson"]
    else:
        if not user:
            from ..core.errors import BadRequest
            raise BadRequest("user 不能为空")
        expect_json = False

    text = llm.complete(system or "", user or "", expect_json=expect_json, provider=provider)
    log.info("complete | template=%s provider=%s 输出 %d 字 耗时=%.1fms",
             name or "-", llm.get_provider(provider).name, len(text or ""),
             (time.time() - started) * 1000)
    out = {"provider": llm.get_provider(provider).name, "text": text}
    if expect_json:
        import json
        try:
            out["json"] = json.loads(text)
        except ValueError:
            out["json"] = None
    return out
