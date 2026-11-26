"""Read explicit profile facts from permitted, already acquired inputs."""

import re


PROFILE_FIELDS = ("age", "ip_location", "occupation", "interests")
AGE_BANDS = ((0, 17), (18, 24), (25, 34), (35, 44), (45, 54), (55, 64), (65, 120))
COMMENT_SELF_REPORTS = {
    "age": r"(?:我(?:今年|现在)?|本人(?:今年|现在)?)[：:\s]*(\d{1,3})(?:周)?岁",
    "occupation": (
        r"(?:我是(?:一名|一个|个)?|本人是|我(?:从事|做))\s*"
        r"(小学老师|中学老师|大学老师|老师|教师|学生|家长|医生|护士|律师|程序员|设计师|"
        r"摄影师|剪辑师|个体户|商家|跨境电商|电商运营|内容创作者)"
        r"(?=[\s，。！？、；,.!?;的从做在学用]|$)"
    ),
    "interests": r"(?:我|本人)(?:平时|一直|很)?喜欢\s*([^，。！？、；,.!?;\r\n]{1,24})(?=[，。！？、；,.!?;\r\n]|$)",
}
NEGATIVE = re.compile(
    r"不(?:太)?(?:好用|推荐|喜欢|满意)|差评|闪退|太贵|太短|太慢|太吵|用不了|不方便|失望"
)
POSITIVE = re.compile(r"好用|不错|推荐|满意|喜欢|方便|很稳|清晰")
INTENT_RULES = (
    ("询价", r"多少钱|什么价|价格多少|求报价"),
    ("购买咨询", r"哪里买|在哪买|怎么买|求链接|想买"),
    ("使用反馈", r"我用过|我试过|我买了|用了一|用起来|闪退|报错"),
    ("了解功能", r"支持吗|支持.+吗|能不能|有没有.+功能"),
)


def profile_evidence(record):
    """Return only facts that carry a source. This never visits a profile."""
    saved = record.get("profile_evidence")
    if not isinstance(saved, dict):
        saved = {}
    common_source = record.get("profile_source") or ""
    facts = {}
    for field in PROFILE_FIELDS:
        item = saved.get(field, {})
        if not isinstance(item, dict):
            item = {}
        value = str(item.get("value") or record.get(field) or "").strip()
        source = str(item.get("source") or record.get(f"{field}_source") or common_source).strip()
        if field == "ip_location":
            value = re.sub(r"^IP\s*属地\s*[：:]?\s*", "", value, flags=re.IGNORECASE)
            if any(char.isdigit() for char in value) or ":" in value:
                value = ""
        if value and value not in ("未知", "未填写") and source:
            facts[field] = {"value": value, "source": source}
    return facts


def age_band(value):
    exact = re.fullmatch(r"(\d{1,3})(?:周?岁)?", value)
    if exact:
        age = int(exact[1])
        for low, high in AGE_BANDS:
            if low <= age <= high:
                return "未满18岁" if low == 0 else "65岁以上" if low == 65 else f"{low}–{high}岁"
        return ""
    interval = re.fullmatch(r"(\d{1,3})\s*[-–~至到]\s*(\d{1,3})\s*岁?", value)
    if interval and 0 <= int(interval[1]) <= int(interval[2]) <= 120:
        return f"{int(interval[1])}–{int(interval[2])}岁"
    if value in ("未满18岁", "65岁以上"):
        return value
    return ""


def label_comment(comment):
    text = comment["content"]
    facts = profile_evidence(comment)
    for field, pattern in COMMENT_SELF_REPORTS.items():
        match = re.search(pattern, text)
        if match and field not in facts:
            facts[field] = {"value": match[1], "source": "评论自述", "quote": match[0]}

    tags = {}
    for field in PROFILE_FIELDS:
        fact = facts.get(field, {})
        value = fact.get("value", "")
        if field == "age":
            value = age_band(value)
        tags[field] = {**fact, "value": value} if value else {"value": "未知", "source": ""}

    negative = bool(NEGATIVE.search(text))
    positive = bool(POSITIVE.search(NEGATIVE.sub("", text)))
    stance = {(True, True): "褒贬并存", (True, False): "正面",
              (False, True): "负面", (False, False): "不明确"}[positive, negative]
    intents = [label for label, pattern in INTENT_RULES if re.search(pattern, text)]
    return {"profile_tags": tags, "stance": stance, "intents": intents}
