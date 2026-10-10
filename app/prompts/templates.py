"""Prompt 模板库。

模板用 Python str.format 风格占位符，变量缺失时用默认值补齐，不会抛异常。
服务端只管拼装与变量校验，真正的补全交给 llm/ 里的 provider。
"""

TEMPLATES = {
    "analyze": {
        "desc": "分析一句话：判定意图与领域，给出理解和下一步建议",
        # 注意：不要把「字段说明」写成可照抄的示例值，小模型会原样复制。
        # 说明里只给字段名和取值约束，具体内容让模型自己生成。
        "system": (
            "你是一个目标管理助手。用户说的每一句话都是「当下」的状态描述，不是让你预测未来。\n"
            "先判断它属于哪一种意图：\n"
            "- progress：在汇报已经做了什么 / 有进展\n"
            "- setback：遇到阻力、拖延、没做到\n"
            "- ask：想知道办法、在提问\n"
            "- new：冒出一个新的想法或目标\n"
            "只输出一个 JSON 对象：不要解释，不要代码块，不要复述字段说明，不要输出示例文字。"
        ),
        "user": (
            "用户说：{text}\n\n"
            "已知目标：\n{goals}\n\n"
            "输出一个 JSON 对象，包含这些字段：\n"
            "1. intent：字符串，只能是 progress / setback / ask / new 之一\n"
            "2. intentLabel：字符串，2 到 4 个汉字的中文意图标签\n"
            "3. category：字符串，只能是 fitness / study / career / money / create / social / generic 之一\n"
            "4. summary：字符串，用一句话复述你对上面那句话的理解，不超过 60 字\n"
            "5. goalTitle：字符串，这句话应该归入、或应该新建的目标标题，8 到 16 字\n"
            "6. criterion：字符串，一句话说明怎样才算达成，必须带上具体数字或期限\n"
            "7. suggestions：数组，1 到 3 个对象，每个对象含这些字段：\n"
            "   - title：字符串，下一步具体动作，6 到 12 字\n"
            "   - detail：字符串，这一步具体要做什么、做到什么程度，30 到 80 字\n"
            "   - difficulty：字符串，只能是 easy / medium / hard 之一"
            "（easy=随手就能做，medium=需要一点专注，hard=要专门腾出整块时间）\n"
            "   - steps：字符串数组，1 到 4 条可立即照做的实现步骤，每条 8 到 20 字\n"
            "   - minutes：整数，这一步预计要花多少分钟\n"
            "   - tip：字符串，一句话说明为什么这么做\n\n"
            "硬性要求：summary、goalTitle、criterion、suggestions 的内容必须针对用户说的那句话来写，"
            "不许写「下一步」「为什么」「怎么算达成」「随手就能做」这类占位文字；"
            "detail 和 steps 要有可操作性，不能是空话。"
        ),
        "defaults": {"text": "", "goals": "（暂无）"},
        "json": True,
    },
    "hypothesize": {
        "desc": "给定一个问题/事件，列出最可能的 n 个答案，并给出每个成立的概率",
        "system": (
            "你是一个严谨的推理助手。给定一个开放问题或未来事件，你要列出最可能成立的 n 个答案/结果，"
            "并为每个给出它成立的概率。概率必须是 0 到 1 之间的小数，代表「这个答案是正确的 / 这个结果发生的可能性」。\n"
            "只输出一个 JSON 对象，不要解释，不要代码块，不要复述字段说明，不要输出示例文字。"
        ),
        "user": (
            "问题：{question}\n"
            "需要数量：{n}\n\n"
            "输出一个 JSON 对象，结构如下（注意是合法 JSON，键名用双引号）：\n"
            "{\"answers\": [{\"answer\": \"最可能的答案或结果描述，要具体、可执行、不空洞\", "
            "\"probability\": 0到1之间的小数，表示它成立的可能性，不要自己归一化, "
            "\"reason\": \"一句话说明为什么它成立的可能性高或低\"}]}\n\n"
            "硬性要求：\n"
            "1. answers 长度必须正好是 {n}；\n"
            "2. 所有 answer 必须彼此不同、且紧扣这个问题，不许写占位文字；\n"
            "3. probability 是 0 到 1 之间的小数，多个答案的概率不必加起来等于 1，服务端会归一化；\n"
            "4. reason 要有实质信息，不能写「因为可能性高」这种废话。"
        ),
        "defaults": {"question": "", "n": 3},
        "json": True,
    },
    "suggest": {
        "desc": "围绕一个目标给出可立即执行的下一步",
        "system": "你是一个擅长把大目标拆成小行动的助手。只输出 JSON。",
        "user": (
            "目标：{goal}\n"
            "当前进度：{progress}%\n"
            "停滞天数：{stalledDays}\n"
            "最近提到的：{mentions}\n\n"
            '输出 {{"advice":"一句建议","actions":[{{"title":"...","tip":"...","minutes":15}}]}}，最多 3 条行动。'
        ),
        "defaults": {"goal": "", "progress": 0, "stalledDays": 0, "mentions": "（无）"},
        "json": True,
    },
    "review": {
        "desc": "复盘一段时间线，给出观察与调整建议",
        "system": "你是一个温和但不敷衍的复盘教练。只输出 JSON。",
        "user": (
            "这段时间线：\n{timeline}\n\n"
            '输出 {{"observation":"你看到了什么","risk":"最大的风险","next":"下周最重要的一件事"}}'
        ),
        "defaults": {"timeline": "（空）"},
        "json": True,
    },
    "reframe": {
        "desc": "把一句模糊的抱怨重构成可执行的目标",
        "system": "你擅长把情绪化的表达翻译成可执行的语言。只输出纯文本，不要 JSON。",
        "user": "原话：{text}\n\n把它重构成一句「有数字、有截止日、有验收方式」的目标，然后给出今天能做的最小一步。",
        "defaults": {"text": ""},
        "json": False,
    },
}


def names():
    return [{"name": k, "desc": v["desc"], "json": v["json"],
             "variables": sorted((v.get("defaults") or {}).keys())} for k, v in TEMPLATES.items()]


def get(name):
    tpl = TEMPLATES.get(name)
    if not tpl:
        from ..core.errors import NotFound
        raise NotFound("没有这个模板: %s" % name)
    return tpl


def render(name, variables=None):
    """渲染出 system / user 两段文本，缺失变量用默认值。"""
    tpl = get(name)
    values = dict(tpl.get("defaults") or {})
    values.update({k: v for k, v in (variables or {}).items() if v is not None})

    def fill(text):
        for key, val in values.items():
            text = text.replace("{%s}" % key, str(val))
        return text

    return {
        "name": name,
        "system": fill(tpl["system"]),
        "user": fill(tpl["user"]),
        "expectJson": tpl["json"],
        "variables": values,
    }
