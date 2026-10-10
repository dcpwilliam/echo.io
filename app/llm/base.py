"""LLM Provider 抽象。"""
import json
import re


class LLMProvider:
    name = "base"
    available = False

    def complete(self, system, user, expect_json=False, temperature=None, max_tokens=None):
        """返回字符串；expect_json=True 时要求是合法 JSON 文本。"""
        raise NotImplementedError

    def complete_json(self, system, user, **kw):
        text = self.complete(system, user, expect_json=True, **kw)
        obj = parse_loose(text)
        return obj if obj is not None else {"raw": text}

    def describe_image(self, image_b64, mime="image/jpeg", hint="", system=None, max_tokens=None):
        """看图说话。默认不支持，只有 OpenAI 兼容实现里有真正的能力。"""
        raise RuntimeError("当前 provider 不支持识图")


def parse_loose(text):
    """宽松 JSON 解析：能处理围栏、前后废话，以及被 max_tokens 截断的半截输出。

    截断很常见（推理型模型的 chain-of-thought 会吃掉 token 预算），
    这时把最后那个不完整的元素砍掉、补齐括号，尽量把前面的字段保下来。
    实在救不回来返回 None。
    """
    s = (text or "").strip()
    if not s:
        return None
    # ```json ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)(```|$)", s)
    if m:
        s = m.group(1).strip()
    i = s.find("{")
    if i < 0:
        return None
    j = s.rfind("}")
    frag = s[i:j + 1] if j > i else s[i:]

    try:
        obj = json.loads(frag)
        return obj if isinstance(obj, dict) else None
    except ValueError:
        pass

    # 从尾部一点点砍，砍到能解析为止。
    # 砍点选在 } ] " 这些边界上，避免砍出半截 key
    cuts = sorted([i for i, c in enumerate(frag) if c in "}\"]"], reverse=True)
    for k in cuts:
        if k <= 0:
            break
        obj = _close_and_parse(frag[:k + 1])
        if obj is not None:
            return obj
    return None


def _open_stack(text):
    """返回 (未闭合的左括号栈, 是否停在字符串内部)。"""
    stack, in_str, esc = [], False, False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()
    return stack, in_str


def _close_and_parse(frag):
    """补齐没闭合的括号再解析；解析不出来返回 None。"""
    cand = frag
    stack, in_str = _open_stack(cand)
    if in_str:
        # 字符串被截断：把那半截字符串、以及它前面那个没值的 "key": 一起扔掉
        cand = cand[:cand.rfind('"')]
        cand = re.sub(r',?\s*"[^"]*"\s*:\s*$', '', cand).rstrip().rstrip(",")
        stack, _ = _open_stack(cand)
    cand += "".join("}" if c == "{" else "]" for c in reversed(stack))
    try:
        obj = json.loads(cand)
        return obj if isinstance(obj, dict) else None
    except ValueError:
        return None
