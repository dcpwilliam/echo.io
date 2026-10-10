"""答案预测服务：给定一个问题 + 数量 n，借 LLM 找出最可能的 n 个答案，并给出各自成立的概率。

对外只有一个 predict()，内部串起 prompts 模板 + llm provider + 本地规则兜底。
模式完全对齐 prompt_service.analyze：
  - use_llm=False 走本地规则（provider=echo，不带 llmFallback）；
  - use_llm=True 且配了 Key 才真调模型；
  - 模型超时/连不上/输出无效，一律降级到本地规则，接口永远不返回 500，并打 llmFallback 标记。
"""
import logging
import time

from .. import llm
from ..config import config
from ..domain import answers as _answers
from ..prompts import templates

log = logging.getLogger("aiservice.answers")


# 模型照抄模板里的占位/示例文字就判无效
_PLACEHOLDERS = ("一句话说明为什么", "最可能的答案", "因为可能性高", "概率", "答案描述")


def predict(question, n=3, use_llm=False, provider=None):
    """预测问题最可能的 n 个答案及各自概率。

    use_llm=False（默认）走本地规则；True 且配了 Key 才真的调模型。
    两种路径返回结构一致，前端不用分支。
    """
    question = (question or "").strip()
    if not question:
        from ..core.errors import BadRequest
        raise BadRequest("question 不能为空")

    n = _answers.clamp_n(n)
    started = time.time()

    # 规则结果先算出来：模型出错 / 输出无效时直接顶上
    fallback = _answers.hypothesize(question, n)

    if not use_llm:
        log.info("predict 规则引擎 | question=%s n=%d 耗时=%.1fms",
                 question[:40], n, (time.time() - started) * 1000)
        return _finalize(fallback["answers"], question, n,
                         provider="echo", source="rule")

    rendered = templates.render("hypothesize", {"question": question, "n": n})
    prov = llm.get_provider(provider)
    # 没真正的大模型可用（provider 还是 echo，或没配 Key 的 openai 兼容）：直接走规则，
    # 不强行标 llmFallback，否则会把 echo 返回的「分析类」JSON 误判成「模型没返回答案」。
    if prov.kind != "openai" or not prov.available:
        log.info("predict 无可用大模型（provider=%s），走规则 | question=%s n=%d",
                 prov.name, question[:40], n)
        return _finalize(fallback["answers"], question, n,
                         provider="echo", source="rule")
    log.info("predict 调用模型 | provider=%s model=%s question=%s n=%d",
             prov.name, getattr(config, "LLM_MODEL", "?"), question[:40], n)
    try:
        data = llm.complete_json(rendered["system"], rendered["user"], provider=provider)
    except Exception as e:  # 超时 / 连不上 / 返回结构异常，一律降级
        log.warning("predict 模型调用失败（%s），回退本地规则 | provider=%s",
                    e, prov.name)
        return _finalize(fallback["answers"], question, n,
                         provider="echo", source="rule",
                         llm_fallback=True, reason="模型调用失败: %s" % e)

    bad = _placeholder_reason(data)
    if bad:
        log.warning("predict 模型输出无效（%s），回退本地规则 | provider=%s", bad, prov.name)
        return _finalize(fallback["answers"], question, n,
                         provider="echo", source="rule",
                         llm_fallback=True, reason=bad)

    cleaned = _clean_answers(data, fallback, n)
    log.info("predict 模型返回 | provider=%s 耗时=%.1fms 有效答案=%d",
             prov.name, (time.time() - started) * 1000, len(cleaned))
    return _finalize(cleaned, question, n, provider=prov.name, source="llm")


def _extract_list(data):
    """从模型返回的多种可能结构里抠出 answers 列表。"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("answers", "candidates", "results", "options"):
            val = data.get(key)
            if isinstance(val, list):
                return val
        # 模型直接返回 {"raw": "[...]"} 的情况
        if "raw" in data and isinstance(data["raw"], str):
            import json
            try:
                parsed = json.loads(data["raw"])
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, dict):
                    for key in ("answers", "candidates", "results"):
                        if isinstance(parsed.get(key), list):
                            return parsed[key]
            except ValueError:
                pass
    return []


def _placeholder_reason(data):
    """返回问题原因，正常返回 None。"""
    items = _extract_list(data)
    if not items:
        return "模型没有返回任何答案"

    # 占位文字检测：answer/reason 直接抄了模板说明
    for it in items:
        if not isinstance(it, dict):
            continue
        for key in ("answer", "reason"):
            val = (it.get(key) or "").strip()
            if val in _PLACEHOLDERS:
                return "%s 是占位文字「%s」" % (key, val)
    if len(items) == 0:
        return "内容基本为空"
    return None


def _clean_answers(data, fallback, n):
    """把模型给的答案洗成 {answer, probability, reason} 列表，缺概率就按排名补。

    不够 n 条时用本地规则结果补齐，保证前端永远拿得到 n 条结构一致的数据。
    """
    items = _extract_list(data)
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        answer = (it.get("answer") or it.get("text") or "").strip()
        if not answer or answer in _PLACEHOLDERS:
            continue
        probability = _answers.parse_probability(it.get("probability"))
        reason = (it.get("reason") or "").strip()[:200]
        out.append({
            "answer": answer[:200],
            "probability": probability,   # 可能是 None，后面补
            "reason": reason,
        })
        if len(out) >= n:
            break

    # 不足 n 条——用本地规则占位补齐（保持结构，但标记为规则兜底）
    if len(out) < n:
        for f in fallback["answers"]:
            if len(out) >= n:
                break
            out.append({
                "answer": f["answer"],
                "probability": None,
                "reason": f["reason"],
            })

    # 给缺失概率的答案按排名补一个递减权重（仅用于兜底，最终会被归一化）
    if out:
        # 已有时，用中位概率的衰减来填缺；全缺则用均匀 1/n
        known = [o["probability"] for o in out if o["probability"] is not None]
        if known:
            avg = sum(known) / len(known)
        else:
            avg = 1.0 / max(1, len(out))
        for idx, o in enumerate(out):
            if o["probability"] is None:
                o["probability"] = max(0.01, avg * (0.9 ** (idx + 1)))
    return out


def _finalize(answers, question, n, provider, source, llm_fallback=False, reason=None):
    """概率归一化 + 排序 + 排名，组装最终响应。"""
    n = _answers.clamp_n(n)
    items = list(answers)[:n]
    if not items:
        items = _answers.hypothesize(question, n)["answers"]

    # 归一化：先把每个 clamp 到 [0,1]，再按总和归一
    for o in items:
        p = _answers.parse_probability(o.get("probability")) or 0.0
        o["probability"] = p
    total = sum(o["probability"] for o in items)
    if total <= 0:
        # 全 0 时退化为均匀分布
        for o in items:
            o["probability"] = round(1.0 / len(items), 4)
        total = 1.0
    else:
        for o in items:
            o["probability"] = round(o["probability"] / total, 4)
    # 归一化后再跑一遍，确保展示用 total 与四舍五入后的和一致
    shown_total = round(sum(o["probability"] for o in items), 4)

    # 降序排列，给排名
    items.sort(key=lambda o: o["probability"], reverse=True)
    ranked = []
    for i, o in enumerate(items, 1):
        ranked.append({
            "rank": i,
            "answer": o.get("answer", ""),
            "probability": o["probability"],
            "reason": o.get("reason") or "",
        })

    return {
        "question": question,
        "n": len(ranked),
        "answers": ranked,
        "normalized": True,
        "totalProbability": shown_total,
        "provider": provider,
        "source": source,
        "llmFallback": bool(llm_fallback),
        "llmFallbackReason": reason,
    }
