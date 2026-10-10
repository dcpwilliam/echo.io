"""答案预测器：本地规则版兜底，对应 LLM 的 hypothesize 能力。

和 analyzer.py 一样，这里不联网、不推理，只在「没配 Key / 模型失败」时
给出一个结构一致、但明确标注「不可信」的占位结果，保证接口形状稳定。
真正的推理在 services/answer_service.py 里走 LLM。
"""
import re


# 概率上限：防止模型（或规则）给到离谱的值
_MAX_N = 10


def clamp_n(n):
    """把 n 约束到 1..10 的合法区间。"""
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 3
    return max(1, min(n, _MAX_N))


def _placeholder_answers(question, n):
    """规则引擎无法真正推理，只产出占位结构。

    每条概率按简单衰减分布给出，让前端拿到的是「形状正确、但明显是占位」的数据。
    """
    n = clamp_n(n)
    base = 1.0 / n
    answers = []
    for i in range(n):
        # 轻微递减，避免 n 条完全一样的概率
        w = base * (1 - i * 0.06)
        answers.append({
            "answer": "候选 %d（规则引擎未接入大模型，仅为占位）" % (i + 1),
            "probability": round(w, 4),
            "reason": "本地规则不具推理能力；配置 LLM_API_KEY 后可得真实最可能的答案与概率。",
        })
    return answers


def hypothesize(question, n=3):
    """规则版入口：返回 { question, n, answers, source }。

    source 永远是 "rule"，提醒上层这是占位结果。
    """
    n = clamp_n(n)
    return {
        "question": (question or "").strip(),
        "n": n,
        "answers": _placeholder_answers(question, n),
        "source": "rule",
    }


# ---------------- 概率解析 ----------------

def parse_probability(raw):
    """把模型给的概率统一成 0~1 之间的 float；解析不出返回 None。

    支持：0.62 / "0.62" / 62 / "62%" / "62%" 等写法。
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
    else:
        s = str(raw).strip().replace("%", "").replace("％", "")
        s = s.rstrip("。").strip()
        if not s:
            return None
        try:
            val = float(s)
        except ValueError:
            m = re.search(r"(\d+(?:\.\d+)?)", s)
            if not m:
                return None
            val = float(m.group(1))
    # 0~1 之外但落在 0~100：当成百分比
    if val > 1 and val <= 100:
        val = val / 100.0
    if val < 0:
        val = 0.0
    if val > 1:
        val = 1.0
    return val
