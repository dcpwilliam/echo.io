"""目标维护：归拢、累计、重算。与小程序 utils/goals.js 的算法保持一致。"""
import time
import uuid
from datetime import datetime

from . import categories, dates

WEEK_MS = 7 * 86400000
CURRENCY = {"万": 10000, "千": 1000, "元": 1, "块": 1}

# 难度 -> 对目标的贡献点数（与小程序 engine.POINTS_BY_DIFFICULTY 一致）
POINTS_BY_DIFFICULTY = {"easy": 10, "medium": 20, "hard": 30}
DEFAULT_POINTS = 20
# 任务卡片规范：步骤最多 5 条
MAX_STEPS = 5


def uid():
    return "%s%s" % (int(time.time() * 1000), str(int(time.time() * 1e6) % 100000))


def new_id(prefix=""):
    return (prefix or "") + uuid.uuid4().hex[:12]


def round1(n):
    return round(n * 10) / 10


def points_of(difficulty):
    """难度 -> 贡献点数（没显式指定时按难度折算）。"""
    return POINTS_BY_DIFFICULTY.get(difficulty, DEFAULT_POINTS)


def normalize_difficulty(key):
    from ..storage.schema import difficulty_meta
    return difficulty_meta(key)["key"]


def normalize_steps(steps):
    """步骤：字符串数组，最多 MAX_STEPS 条，去空白。"""
    if not isinstance(steps, list):
        return []
    out = []
    for s in steps:
        text = str(s or "").strip()
        if text:
            out.append(text)
    return out[:MAX_STEPS]


# ---------------- 相似度 ----------------

def _grams(s):
    import re
    t = re.sub(r"[^一-龥a-zA-Z0-9]", "", str(s or ""))
    if len(t) < 2:
        return {t} if t else set()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def similarity(a, b):
    """2-gram Jaccard"""
    A, B = _grams(a), _grams(b)
    if not A or not B:
        return 0.0
    inter = len(A & B)
    return inter / (len(A) + len(B) - inter)


def match_goal(text, category_key, goals, threshold=0.42):
    """这句话该归到哪个目标？同领域 + 字面重合即命中。"""
    now = time.time() * 1000
    best, best_score = None, 0.0
    for g in goals:
        score = 0.55 * similarity(text, g.get("title", ""))
        if g.get("categoryKey") == category_key:
            score += 0.45
        if g.get("status") == "done":
            score -= 0.2
        last = g.get("lastMentionAt") or 0
        if last and (now - last) / 86400000 <= 3:
            score += 0.05
        if score > best_score:
            best, best_score = g, score
    if best is not None and best_score >= threshold:
        return {"goal": best, "score": round(best_score, 3)}
    return None


def recent_active_goal(goals, days=7):
    """「最近在忙的那个目标」——抱怨或提问往往说的是它。"""
    limit = time.time() * 1000 - days * 86400000
    best = None
    for g in goals:
        if g.get("status") == "done":
            continue
        if (g.get("lastMentionAt") or g.get("createdAt") or 0) < limit:
            continue
        if best is None or (g.get("lastMentionAt") or 0) > (best.get("lastMentionAt") or 0):
            best = g
    return best


# ---------------- 创建 ----------------

def create_goal(analysis):
    cat = categories.find(analysis["category"]["key"])
    qty = analysis.get("quantity")
    is_target = analysis.get("metricKind") == "target"
    now = int(time.time() * 1000)
    return {
        "id": new_id("g_"),
        "title": analysis.get("suggestedTitle") or analysis.get("goalTitle"),
        "criterion": analysis.get("criterion", ""),
        "categoryKey": cat["key"],
        "categoryName": cat["name"],
        "color": cat["color"],
        "target": {"value": qty["value"], "unit": qty["unit"]} if (is_target and qty) else None,
        "current": 0,
        "currentUnit": None,
        "horizonDays": analysis.get("horizon", {}).get("days", 0),
        "horizonLabel": analysis.get("horizon", {}).get("label", "未设时限"),
        "status": "active",
        "createdAt": now,
        "updatedAt": now,
        "lastMentionAt": now,
        "mentions": [{"text": analysis.get("text", ""), "ts": now, "intent": analysis.get("intent")}],
        "progress": 0,
        # 贡献点数（已完成任务累计 / 全部任务合计）
        "points": 0,
        "pointsTotal": 0,
        "momentum": 0,
        "stalledDays": 0,
        "advice": "",
        "taskDone": 0,
        "taskTotal": 0,
    }


# ---------------- 累计 ----------------

def apply_metric(goal, analysis):
    """汇报了数字 -> 累计到目标进度（单位不一致时按货币表换算）。"""
    qty = analysis.get("quantity")
    if not qty:
        return goal
    if analysis.get("metricKind") != "done":
        if not goal.get("target"):
            goal["target"] = {"value": qty["value"], "unit": qty["unit"]}
        return goal
    target = goal.get("target")
    if not target:
        goal["current"] = round1(goal.get("current", 0) + qty["value"])
        goal["currentUnit"] = qty["unit"]
        return goal
    if target.get("unit") == qty["unit"]:
        goal["current"] = round1(goal.get("current", 0) + qty["value"])
        return goal
    src, dst = CURRENCY.get(qty["unit"]), CURRENCY.get(target.get("unit"))
    if src and dst:
        goal["current"] = round1(goal.get("current", 0) + qty["value"] * src / dst)
    return goal


def mention(goal, analysis, keep=20):
    now = int(time.time() * 1000)
    goal.setdefault("mentions", []).insert(0, {
        "text": analysis.get("text", ""),
        "ts": now,
        "intent": analysis.get("intent"),
    })
    goal["mentions"] = goal["mentions"][:keep]
    goal["lastMentionAt"] = now
    goal["updatedAt"] = now
    return goal


# ---------------- 重算 ----------------

def compose_advice(progress, done, total, recent, stalled_days):
    if progress >= 100:
        return "目标已经达成了。可以说一句复盘，或者直接立个新的。"
    if total == 0:
        return "还没有落地的行动，从下面的建议里挑一条放进时间线。"
    if stalled_days >= 5:
        return "已经 %d 天没有动静了，今天做一件 10 分钟能完成的事，把惯性接回来。" % stalled_days
    if stalled_days >= 2:
        return "有 %d 天没推进，先别追求质量，做最小的一步。" % stalled_days
    if recent >= 4:
        return "近七天完成了 %d 项，节奏很稳，可以考虑加一档强度。" % recent
    if progress >= 50:
        return "已经过半，后半程通常比前半程快，保持现在的节奏。"
    return "保持每天一个小动作，先把连续记录攒起来。"


def sync_goal(goal, records):
    """用时间线上的真实完成情况重算目标状态。手动标记达成后锁定，不再被覆盖。"""
    if goal.get("status") == "done":
        goal["progress"] = 100
        goal["advice"] = "这个目标已经完成了，剩下的就是别让它反弹。"
        return goal

    now = time.time() * 1000
    total = done = recent = 0
    points = points_total = 0
    last_done_at = 0
    for r in records:
        if r.get("goalId") != goal["id"]:
            continue
        for t in r.get("tasks", []):
            total += 1
            p = int(t.get("points") or 0)
            points_total += p
            if t.get("done"):
                done += 1
                points += p
                if t.get("doneAt") and now - t.get("doneAt", 0) < WEEK_MS:
                    recent += 1
                last_done_at = max(last_done_at, t.get("doneAt") or 0)

    target = goal.get("target")
    if target and target.get("value"):
        by_number = min(100, round((goal.get("current", 0) / target["value"]) * 100))
        progress = round(by_number * 0.5 + (done / total) * 100 * 0.5) if total else by_number
    elif total:
        progress = round(done / total * 100)
    else:
        progress = 0

    last_active = max(goal.get("lastMentionAt") or 0, last_done_at) or goal.get("createdAt", now)
    last_active_day = dates.fmt(datetime.fromtimestamp(last_active / 1000.0))
    stalled = max(0, dates.diff_days(last_active_day, dates.today()))

    goal["progress"] = progress
    goal["taskTotal"] = total
    goal["taskDone"] = done
    # 贡献点数：已完成任务的点数 / 全部任务的点数
    goal["points"] = points
    goal["pointsTotal"] = points_total
    goal["momentum"] = recent
    goal["stalledDays"] = stalled
    goal["status"] = "done" if progress >= 100 else "active"
    goal["advice"] = compose_advice(progress, done, total, recent, stalled)
    return goal


def sync_all(goals, records):
    for g in goals:
        sync_goal(g, records)
    return goals


# ---------------- 行动记录 ----------------

def make_task(action, day=None, index=0, ts=None):
    """一个可执行的最小任务（不是一排定期安排，每次只加一条）。

    卡片规范字段：关联目标 / 难度 / 详细内容 / 实现步骤；
    另附贡献点数与截止时间（默认当天晚上 8 点）。
    """
    action = action or {}
    difficulty = normalize_difficulty(action.get("difficulty"))
    points = int(action.get("points") or 0) or points_of(difficulty)
    due_at = int(action.get("dueAt") or 0) or dates.at_today()
    now = int(time.time() * 1000)
    return {
        "id": new_id("t_"),
        "index": index or 0,
        "date": day or dates.today(),
        "phase": "行动",
        "title": action.get("title", ""),
        "tip": action.get("tip", ""),
        "minutes": int(action.get("minutes") or 15),
        "image": action.get("image", ""),
        # ---- 任务卡片规范字段 ----
        "goalId": action.get("goalId", ""),
        "goal": action.get("goal", ""),
        "difficulty": difficulty,
        "detail": action.get("detail") or action.get("guide") or "",
        "steps": normalize_steps(action.get("steps")),
        # ---- 贡献点数 & 截止 ----
        "points": points,
        "dueAt": due_at,
        "dueLabel": dates.due_label(due_at),
        "done": False,
        "doneAt": 0,
        "createdAt": ts or now,
    }


def build_action_record(goal, actions, start_date=None):
    """目标 + 若干条即时行动 -> 一条时间线记录（同一天，不摊到多天）"""
    start = start_date or dates.today()
    now = int(time.time() * 1000)
    tasks = []
    for i, a in enumerate(actions or []):
        t = make_task(a, start, i, now + i)
        t["goalId"] = goal["id"]
        t["goal"] = goal.get("title", "")
        tasks.append(t)

    return {
        "id": new_id("r_"),
        "kind": "action",
        "goalId": goal["id"],
        "need": goal.get("title", ""),
        "goal": goal.get("title", ""),
        "categoryKey": goal.get("categoryKey"),
        "categoryName": goal.get("categoryName"),
        "categoryColor": goal.get("color"),
        "option": {
            "id": "action",
            "tag": "即时",
            "name": "即时行动",
            "emoji": "⚡",
            "way": "从你当下这句话里拆出来的下一步",
            "cost": "%d 条" % len(tasks),
            "risk": "",
        },
        "horizonLabel": goal.get("horizonLabel", "未设时限"),
        "createdAt": now,
        "updatedAt": now,
        "start": tasks[0]["date"] if tasks else start,
        "end": tasks[-1]["date"] if tasks else start,
        "tasks": tasks,
    }


def find_action_record(records, goal_id):
    """目标在时间线上已有的那条行动记录（一个目标只占一条连续的记录）。"""
    for r in records or []:
        if r.get("goalId") == goal_id and r.get("kind") == "action":
            return r
    return None


def append_task_to_goal(records, goal, action, day=None):
    """给目标追加一个任务：复用已有记录，没有才新建。

    这样挑一个任务就记一条，时间线不会冒出一堆重复的计划。
    @returns {"record", "task", "created"}
    """
    day_str = day or dates.today()
    rec = find_action_record(records, goal["id"])
    created = False

    if rec is None:
        rec = build_action_record(goal, [], day_str)
        records.insert(0, rec)
        created = True

    task = make_task(action, day_str, len(rec.get("tasks", [])))
    task["goalId"] = goal["id"]
    task["goal"] = goal.get("title", "")
    rec.setdefault("tasks", []).append(task)

    # 始终按「日期 + 加入顺序」排好，时间线读出来天然是时间顺序
    rec["tasks"] = sorted(rec["tasks"], key=lambda t: (t.get("date", ""), t.get("createdAt") or 0))

    if day_str < rec.get("start", day_str):
        rec["start"] = day_str
    if day_str > rec.get("end", day_str):
        rec["end"] = day_str
    rec["updatedAt"] = int(time.time() * 1000)

    return {"record": rec, "task": task, "created": created}


def progress_of(record):
    tasks = record.get("tasks", [])
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("done"))
    return {"done": done, "total": total, "percent": round(done / total * 100) if total else 0}
