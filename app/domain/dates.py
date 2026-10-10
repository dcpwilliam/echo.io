"""日期工具，与小程序 utils/date.js 保持一一对应（'YYYY-MM-DD' 字符串为准）。"""
from datetime import datetime, timedelta

WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 任务默认截止时间：当天晚上 8 点
DUE_HOUR = 20


def pad(n):
    return ("0%d" % n) if n < 10 else str(n)


def fmt(d):
    """datetime -> 'YYYY-MM-DD'"""
    return "%d-%s-%s" % (d.year, pad(d.month), pad(d.day))


def parse(s):
    """'YYYY-MM-DD' -> datetime（本地零点）"""
    y, m, d = (int(x) for x in str(s).split("-"))
    return datetime(y, m, d)


def today():
    return fmt(datetime.now())


def add_days(s, n):
    return fmt(parse(s) + timedelta(days=n))


def diff_days(a, b):
    """相隔天数 b - a"""
    return (parse(b) - parse(a)).days


def weekday(s):
    """周一…周日"""
    return WEEK[parse(s).weekday()]


def md(s):
    """'10月3日 周六'"""
    d = parse(s)
    return "%d月%d日 %s" % (d.month, d.day, weekday(s))


def relative(s):
    """今天 / 明天 / 后天 / 昨天 / 前天 / 周一…"""
    n = diff_days(today(), s)
    if n == 0:
        return "今天"
    if n == 1:
        return "明天"
    if n == 2:
        return "后天"
    if n == -1:
        return "昨天"
    if n == -2:
        return "前天"
    return weekday(s)


def date_range(start, length):
    """以 start 开头、共 length 天的日期数组"""
    return [add_days(start, i) for i in range(length)]


def friendly_time(ts):
    """毫秒时间戳 -> 人类可读"""
    d = datetime.fromtimestamp(ts / 1000.0)
    n = diff_days(fmt(d), today())
    hm = "%s:%s" % (pad(d.hour), pad(d.minute))
    if n == 0:
        return "今天 " + hm
    if n == 1:
        return "昨天 " + hm
    if 0 < n < 7:
        return "%d天前" % n
    return "%d月%d日" % (d.month, d.day)


def now_ms():
    return int(datetime.now().timestamp() * 1000)


# ---------------- 截止时间 ----------------

def at_today(hour=None, minute=0):
    """当天某个时刻的毫秒时间戳，默认晚上 8 点（任务截止）。"""
    now = datetime.now()
    when = now.replace(hour=DUE_HOUR if hour is None else hour,
                       minute=minute or 0, second=0, microsecond=0)
    return int(when.timestamp() * 1000)


def hm(ts):
    """毫秒时间戳 -> '20:00'"""
    d = datetime.fromtimestamp(ts / 1000.0)
    return "%s:%s" % (pad(d.hour), pad(d.minute))


def due_label(ts):
    """截止时间的人类读法：今晚 20:00 / 明天 20:00 / 昨天 20:00 / 10月8日 20:00"""
    if not ts:
        return ""
    d = datetime.fromtimestamp(ts / 1000.0)
    n = diff_days(today(), fmt(d))
    clock = hm(ts)
    if n == 0:
        return "今晚 " + clock
    if n == 1:
        return "明天 " + clock
    if n == -1:
        return "昨天 " + clock
    return "%d月%d日 %s" % (d.month, d.day, clock)
