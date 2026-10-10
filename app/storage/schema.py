"""数据结构定义与规范化。

与小程序 Storage 里的三个 key 一一对应：
    tl_goals_v1   -> state["goals"]
    tl_records_v1 -> state["records"]
    tl_msgs_v1    -> state["messages"]
"""
import time

from ..domain import dates, new_id

MAX_MENTIONS = 20
MAX_MESSAGES = 60

# 任务难度档位（与服务端 / 小程序共用同一套取值与配色）
DIFFICULTY_LEVELS = {
    "easy": {"key": "easy", "label": "轻松", "color": "#12b886"},
    "medium": {"key": "medium", "label": "适中", "color": "#5B6CFF"},
    "hard": {"key": "hard", "label": "挑战", "color": "#E8590C"},
}
DEFAULT_DIFFICULTY = "medium"
MAX_STEPS = 5
MAX_STEP_LEN = 40

# 模型可能用中文/近义词描述难度，统一归到 easy/medium/hard
DIFFICULTY_ALIAS = {
    "easy": "easy", "简单": "easy", "容易": "easy", "轻松": "easy", "低": "easy", "随手": "easy",
    "medium": "medium", "适中": "medium", "中等": "medium", "一般": "medium", "中": "medium",
    "hard": "hard", "难": "hard", "困难": "hard", "挑战": "hard", "高": "hard", "费劲": "hard",
}


def difficulty_meta(key):
    """返回 {key,label,color}，非法值回落默认档。"""
    return DIFFICULTY_LEVELS.get(DIFFICULTY_ALIAS.get(str(key).strip().lower(), DEFAULT_DIFFICULTY)) \
        or DIFFICULTY_LEVELS[DEFAULT_DIFFICULTY]


def now_ms():
    return int(time.time() * 1000)


# ---------------- 用户 ----------------

def make_user(user_id=None, name="", email="", **extra):
    now = now_ms()
    return {
        "id": user_id or new_id("u_"),
        "name": name or ("用户" + (user_id or new_id(""))[:4]),
        "email": email,
        "sub": extra.get("sub") or "",
        "createdAt": now,
        "updatedAt": now,
        "level": extra.get("level", 1),
        "coins": extra.get("coins", 0),
        "settings": {
            "window": extra.get("window", 7),
            "llmProvider": extra.get("llmProvider", "echo"),
        },
        **{k: v for k, v in extra.items() if k not in ("sub", "window", "llmProvider", "level", "coins")},
    }


def normalize_user(data):
    if not isinstance(data, dict):
        return None
    for key in ("name", "email", "sub"):
        data.setdefault(key, "")
    data.setdefault("level", 1)
    data.setdefault("coins", 0)
    data.setdefault("settings", {})
    data.setdefault("createdAt", now_ms())
    data["updatedAt"] = now_ms()
    return data


# ---------------- 目标 ----------------

def normalize_goal(data):
    """补齐字段，避免前端少传一个字段就炸。"""
    if not isinstance(data, dict):
        return None
    now = now_ms()
    data.setdefault("id", new_id("g_"))
    data.setdefault("title", "未命名目标")
    data.setdefault("criterion", "")
    data.setdefault("categoryKey", "generic")
    data.setdefault("categoryName", "通用目标")
    data.setdefault("color", "#5B6CFF")
    data.setdefault("target", None)
    data["current"] = float(data.get("current") or 0)
    data.setdefault("status", "active")
    data.setdefault("progress", 0)
    data.setdefault("stalledDays", 0)
    data.setdefault("momentum", 0)
    data.setdefault("advice", "")
    data.setdefault("createdAt", now)
    data.setdefault("updatedAt", now)
    data.setdefault("lastMentionAt", data["createdAt"])
    data.setdefault("horizonDays", 0)
    data.setdefault("horizonLabel", "未设时限")
    mentions = data.get("mentions") or []
    data["mentions"] = [m for m in mentions if isinstance(m, dict)][:MAX_MENTIONS]
    return data


# ---------------- 任务 / 记录 ----------------

def normalize_task(task, index=0, start=None):
    if not isinstance(task, dict):
        return None
    task.setdefault("id", new_id("t_"))
    task.setdefault("index", index)
    task.setdefault("date", dates.add_days(start or dates.today(), index))
    task.setdefault("phase", "行动")
    task.setdefault("title", "")
    task.setdefault("tip", "")
    task["minutes"] = int(task.get("minutes") or 15)
    task["done"] = bool(task.get("done"))
    task.setdefault("doneAt", now_ms() if task["done"] else 0)

    # ---- 任务卡片规范字段 ----
    # 1) 关联目标：任务一定挂在某个目标下，缺省留空，由 buildActionRecord / appendTaskToGoal 回填
    task.setdefault("goalId", "")
    task.setdefault("goal", "")
    # 2) 难度：只能是 easy / medium / hard（中文/近义词自动归并）
    task["difficulty"] = difficulty_meta(task.get("difficulty"))["key"]
    # 3) 详细内容
    if not isinstance(task.get("detail"), str):
        task["detail"] = str(task.get("detail") or "")
    # 4) 实现步骤（建议）：字符串数组，最多 MAX_STEPS 条，每条截断
    steps = task.get("steps")
    if not isinstance(steps, list):
        steps = []
    task["steps"] = [str(s).strip()[:MAX_STEP_LEN] for s in steps if str(s).strip()][:MAX_STEPS]

    # 5) 对目标的贡献点数（非负整数，缺省 0）
    try:
        task["points"] = max(0, int(task.get("points") or 0))
    except (TypeError, ValueError):
        task["points"] = 0
    # 6) 截止时间：毫秒时间戳，缺省 0（前端默认当天 20:00）
    try:
        task["dueAt"] = int(task.get("dueAt") or 0)
    except (TypeError, ValueError):
        task["dueAt"] = 0
    if not isinstance(task.get("dueLabel"), str):
        task["dueLabel"] = str(task.get("dueLabel") or "")
    return task


def normalize_record(data):
    if not isinstance(data, dict):
        return None
    now = now_ms()
    data.setdefault("id", new_id("r_"))
    data.setdefault("kind", "action")
    data.setdefault("need", data.get("goal") or "")
    data.setdefault("goal", data.get("need") or "")
    data.setdefault("goalId", "")
    data.setdefault("categoryKey", "generic")
    data.setdefault("categoryName", "通用目标")
    data.setdefault("categoryColor", "#5B6CFF")
    data.setdefault("horizonLabel", "未设时限")
    data.setdefault("createdAt", now)
    # 说明：原来的「三条路径」已移除，记录一律是目标下的行动，
    # 这里只保留一个「即时行动」的展示壳，不再有达成概率。
    data.setdefault("option", {
        "id": "action", "tag": "即时", "name": "即时行动", "emoji": "⚡",
        "way": "", "cost": "", "risk": "",
    })
    tasks = [normalize_task(t, i, data.get("start")) for i, t in enumerate(data.get("tasks") or [])]
    data["tasks"] = [t for t in tasks if t]
    data["start"] = data.get("start") or (data["tasks"][0]["date"] if data["tasks"] else dates.today())
    data["end"] = data.get("end") or (data["tasks"][-1]["date"] if data["tasks"] else data["start"])
    return data


# ---------------- 会话 ----------------

def normalize_message(data):
    if not isinstance(data, dict):
        return None
    data.setdefault("id", new_id("m_"))
    data.setdefault("ts", now_ms())
    data.setdefault("text", "")
    data.setdefault("intent", "")
    data.setdefault("goalId", "")
    return data


def normalize_vote(data):
    """投票记录：question 投了哪个 choice，可选 detail / weight。"""
    if not isinstance(data, dict):
        return None
    data.setdefault("id", new_id("v_"))
    data.setdefault("ts", now_ms())
    data.setdefault("question", "")
    data.setdefault("choice", "")
    data.setdefault("detail", "")
    try:
        data["weight"] = max(0, int(data.get("weight") or 1))
    except (TypeError, ValueError):
        data["weight"] = 1
    return data


# ---------------- 整体 ----------------

def empty_state(user_id):
    return {
        "user": make_user(user_id),
        "goals": [],
        "records": [],
        "messages": [],
        "votes": [],
        "updatedAt": now_ms(),
    }


def normalize_state(data, user_id=None):
    if not isinstance(data, dict):
        data = {}
    state = {
        "user": normalize_user(data.get("user")) or make_user(user_id),
        "goals": [g for g in (normalize_goal(x) for x in (data.get("goals") or [])) if g],
        "records": [r for r in (normalize_record(x) for x in (data.get("records") or [])) if r],
        "messages": [m for m in (normalize_message(x) for x in (data.get("messages") or [])) if m][:MAX_MESSAGES],
        "votes": [v for v in (normalize_vote(x) for x in (data.get("votes") or [])) if v],
        "updatedAt": now_ms(),
    }
    if user_id and not state["user"].get("id"):
        state["user"]["id"] = user_id
    return state
