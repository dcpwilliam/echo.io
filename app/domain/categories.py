"""领域词库：与小程序 utils/engine.js 的六大领域对齐（精简版，够服务端用）。

小程序端有 7 天计划模板等重逻辑；服务端只需要「这句话属于哪个领域」，
用于目标归拢、时间线着色与 prompt 里的上下文补充。
"""

CATEGORIES = [
    {
        "key": "fitness",
        "name": "健康塑形",
        "color": "#12B886",
        "match": [
            "减重", "减肥", "瘦身", "跑步", "跑", "健身", "马甲线", "腹肌", "体重", "斤",
            "公里", "锻炼", "运动", "拉伸", "早睡", "睡眠", "饮食", "控糖", "戒", "跳绳",
        ],
    },
    {
        "key": "study",
        "name": "学习考试",
        "color": "#4C6EF5",
        "match": [
            "学习", "读书", "看書", "复习", "备考", "考研", "背单词", "英语", "刷题", "课程",
            "论文", "考试", "证书", "技能", "学", "读完", "页", "章节",
        ],
    },
    {
        "key": "career",
        "name": "职业发展",
        "color": "#7048E8",
        "match": [
            "跳槽", "面试", "简历", "offer", "工作", "升职", "转岗", "绩效", "项目", "汇报",
            "晋升", "求职", "内推", "副业", "涨薪", "入职", "离职",
        ],
    },
    {
        "key": "money",
        "name": "财富积累",
        "color": "#F08C00",
        "match": [
            "存钱", "存款", "存了", "攒钱", "理财", "基金", "定投", "记账", "省钱", "还贷",
            "负债", "收入", "预算", "消费", "攒", "买房", "首付", "万", "元", "块",
        ],
    },
    {
        "key": "create",
        "name": "创作输出",
        "color": "#E64980",
        "match": [
            "写作", "写", "文章", "公众号", "视频", "剪辑", "播客", "画画", "设计", "作品集",
            "更新", "发布", "连载", "小红书", "博客", "专栏", "日更",
        ],
    },
    {
        "key": "social",
        "name": "关系社交",
        "color": "#1098AD",
        "match": [
            "社交", "朋友", "聚会", "约会", "相亲", "家人", "父母", "孩子", "沟通", "联系",
            "人脉", "认识", "恋爱", "婚姻", "陪",
        ],
    },
]

GENERIC = {
    "key": "generic",
    "name": "通用目标",
    "color": "#5B6CFF",
    "match": [],
}

ALL = CATEGORIES + [GENERIC]
_BY_KEY = {c["key"]: c for c in ALL}


def find(key):
    return _BY_KEY.get(key) or GENERIC


def detect(text):
    """按关键词命中数打分，选命中最多且词最长的领域；都没中则通用。"""
    raw = str(text or "")
    best, best_score = None, 0
    for cat in CATEGORIES:
        score = 0
        for word in cat["match"]:
            if word in raw:
                # 命中词越长越可信，避免"跑"这类单字抢戏
                score += len(word)
        if score > best_score:
            best, best_score = cat, score
    return best or GENERIC


def short(cat):
    """喂给 prompt 的紧凑表示"""
    return {"key": cat["key"], "name": cat["name"], "color": cat["color"]}
