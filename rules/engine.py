"""Versioned, offline evidence evaluation using the Python standard library."""

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path


RULE_PATH = Path(__file__).with_name("evidence_rules.json")
SCHEMA_VERSION = 1
PROFILE_FIELDS = ("age", "ip_location", "occupation", "interests")
AGE_BANDS = ((0, 17), (18, 24), (25, 34), (35, 44), (45, 54), (55, 64), (65, 120))
SOURCE_FIELDS = (
    "platform", "channel", "record_type", "title", "content", "source_url", "parent_url", "thread_id",
    "comment_id", "reply_to_id", "author_id", "author_or_app", "published_at", "commented_at",
    "source_published_at", "published_time_source", "comment_time_source", "source_updated_at", "source_metric",
    "app_version",
)
QUOTED_LINE = re.compile(r"^[ \t]*>[^\n]*", re.M)
GITHUB_ISSUE_URL = re.compile(
    r"https?://(?:www\.)?github\.com/(?P<repo>[\w.-]+/[\w.-]+)/issues/(?P<number>[1-9]\d*)/?(?:[?#].*)?$",
    re.I | re.ASCII,
)
GITHUB_EXPORT_PREFIX = re.compile(r"^(?:仓库 \S+ 用户高频需求/报错：|开发者 @\S+ 在 \S+ 反馈实机/训练卡点：).*?详情摘要：", re.S)
GITHUB_COMMENT = re.compile(r"<!--.*?(?:-->|$)", re.S)
GITHUB_CODE_BLOCK = re.compile(r"^[ \t]*(?:```|~~~)[^\n]*\n.*?(?:^[ \t]*(?:```|~~~)[^\n]*|\Z)", re.M | re.S)


def profile_evidence(record):
    """Read supplied profile facts with provenance."""
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
    interval = re.fullmatch(r"(\d{1,3})\s*[-–~至到]\s*(\d{1,3})(?:周?岁)?", value)
    if interval and 0 <= int(interval[1]) <= int(interval[2]) <= 120:
        return f"{int(interval[1])}–{int(interval[2])}岁"
    if value in ("未满18岁", "65岁以上"):
        return value
    return ""


def record_kind(record):
    return record.get("record_type") or ("comment" if record.get("comment_id") else "signal")


def platform_name(record):
    channel = record.get("platform") or record.get("channel") or ""
    if channel.startswith("V2EX"):
        return "V2EX"
    if channel.startswith(("App Store", "AppStore")):
        return "App Store"
    if channel.startswith("小众软件论坛") or channel == "Appinn Forum":
        return "小众软件论坛"
    if channel.startswith("GitHub") and ("Issue" in channel or GITHUB_ISSUE_URL.match(record.get("source_url") or "")):
        return "GitHub Issues"
    return channel


def thread_key(record):
    platform = platform_name(record)
    target = str(record.get("thread_id") or record.get("parent_url") or record.get("source_url") or "")
    if platform == "V2EX" and (match := re.search(r"/t/(\d+)(?:[?#/]|$)", target)):
        target = match[1]
    if platform == "App Store" and (match := re.search(r"/id(\d+)(?:[?#/]|$)", target)):
        target = match[1]
    if platform == "小众软件论坛" and (match := re.search(r"/t/[^/]+/(\d+)(?:[/#?]|$)", target)):
        target = match[1]
    if platform == "GitHub Issues" and (match := GITHUB_ISSUE_URL.fullmatch(target)):
        target = f"{match['repo'].lower()}/issues/{match['number']}"
    return platform, target


def text_of(record):
    content = record.get("content") or ""
    title = record.get("title") or ""
    return f"{title}\n{content}" if title else content


def github_issue_excerpt(content):
    """Keep issue prose while removing publishing wrappers and template instructions."""
    content = GITHUB_EXPORT_PREFIX.sub("", content, count=1)
    return GITHUB_CODE_BLOCK.sub("\n", GITHUB_COMMENT.sub("\n", content)).strip()


def same_thread_author(comment, post):
    if not post:
        return False
    if comment.get("author_id") and post.get("author_id"):
        return str(comment["author_id"]) == str(post["author_id"])
    if platform_name(comment) in ("V2EX", "小众软件论坛"):
        comment_author = (comment.get("author_or_app") or "").casefold()
        post_author = (post.get("author_or_app") or "").removeprefix("V2EX @").casefold()
        return bool(comment_author and comment_author == post_author)
    return False


def match_details(rule_id, match, field, source_url):
    return {"rule_id": rule_id, "field": field, "quote": match.group(0), "source_url": source_url}


class EvidenceRules:
    def __init__(self, path):
        raw_rules = Path(path).read_bytes()
        config = json.loads(raw_rules)
        if config["schema_version"] != SCHEMA_VERSION:
            raise ValueError("Unsupported evidence rule schema")
        self.version = config["rule_version"]
        self.fingerprint = hashlib.sha256(raw_rules + Path(__file__).read_bytes()).hexdigest()
        legacy = config["legacy_signal"]
        self.min_length = legacy["min_length"]
        self.noise = [(entry["id"], re.compile(entry["pattern"])) for entry in legacy["noise"]]
        self.text_exception = re.compile(legacy["noise_except"]["text"])
        self.metric_exception = re.compile(legacy["noise_except"]["metric_primary"])
        self.v2ex_discovery = config["v2ex_discovery"]
        self.tags = self.compile_labels(legacy["tags"])
        self.intents = self.compile_labels([entry for entry in config["intents"] if not entry.get("platforms")])
        self.intent_types = {entry["id"]: entry["record_types"] for entry in config["intents"]
                             if entry.get("record_types")}
        self.context_intents = {entry["id"] for entry in config["intents"] if not entry.get("counts_as_demand", True)}
        self.intent_fields = {entry["id"]: entry["field"] for entry in config["intents"] if entry.get("field")}
        self.intent_exclusions = {entry["id"]: re.compile(entry["exclude_pattern"], re.I)
                                  for entry in config["intents"] if entry.get("exclude_pattern")}
        self.intent_parents = {entry["id"]: re.compile(entry["parent_pattern"], re.I) for entry in config["intents"]
                               if entry.get("parent_pattern")}
        platform_entries = defaultdict(list)
        for entry in config["intents"]:
            for platform in entry.get("platforms", []):
                platform_entries[platform].append(entry)
        self.platform_intents = {platform: self.compile_labels(entries) for platform, entries in platform_entries.items()}
        self.comment_topics = self.compile_labels(config.get("comment_topics", []))
        market = config.get("consumer_market", {})
        self.market_segments = self.compile_labels(market.get("segments", []))
        self.market_roles = self.compile_labels(market.get("roles", []))
        self.market_facts = {name: re.compile(pattern, re.I) for name, pattern in market.get("facts", {}).items()}
        self.profiles = {field: re.compile(pattern) for field, pattern in config["profiles"].items()}
        self.negative = re.compile(config["stance"]["negative"])
        self.positive = re.compile(config["stance"]["positive"])
        promotion = config["promotion"]
        self.promotion = {
            name: (promotion[name]["id"], re.compile(promotion[name]["pattern"], re.I))
            for name in ("self", "offer", "contact")
        }
        self.launch = [(entry["id"], re.compile(entry["pattern"], re.I)) for entry in promotion.get("launch", [])]
        followup = promotion["author_followup"]
        self.followup = (followup["id"], re.compile(followup["pattern"], re.I))
        self.complaint = re.compile(promotion["complaint"], re.I)
        self.recommendation = re.compile(promotion["recommendation"], re.I)
        self.thread_request = re.compile(promotion["thread_request"], re.I)
        self.repeat_min_length = promotion["repeat_min_length"]

    @staticmethod
    def compile_labels(entries):
        return [(entry["id"], entry["label"], re.compile(entry["pattern"], re.I)) for entry in entries]

    def repeat_key(self, record):
        if record_kind(record) != "comment" or not record.get("author_id"):
            return None
        content = record.get("content") or ""
        if len(content) < self.repeat_min_length:
            return None
        return platform_name(record), str(record["author_id"]), "".join(content.casefold().split())

    def contexts(self, records):
        posts = {}
        comments = {}
        repeats = defaultdict(dict)
        for record in records:
            key = thread_key(record)
            if not key[1]:
                continue
            if record_kind(record) != "comment":
                posts.setdefault(key, record)
                continue
            if record.get("comment_id"):
                comments[key, str(record["comment_id"])] = record
            repeat = self.repeat_key(record)
            if repeat:
                url = record.get("source_url") or record.get("parent_url") or ""
                previous = repeats[repeat].get(key)
                repeats[repeat][key] = min(previous, url) if previous else url

        def linked_text(record):
            return (text_of(record), record.get("source_url") or "") if record else ("", "")

        for record in records:
            if record_kind(record) != "comment":
                yield (), (), False
                continue
            key = thread_key(record)
            parent_text = record.get("parent_text")
            post = posts.get(key)
            thread = (parent_text, record.get("parent_url") or "") if parent_text else linked_text(post)
            reply = linked_text(comments.get((key, str(record.get("reply_to_id") or ""))))
            related = repeats.get(self.repeat_key(record), {})
            other_urls = sorted({url for thread_id, url in related.items() if key != thread_id and url})[:3]
            yield (thread, reply), tuple(other_urls), same_thread_author(record, post), post

    def labels(self, record, source_url):
        text = QUOTED_LINE.sub("", record.get("content") or "")
        facts = profile_evidence(record)
        matches = []
        for field, pattern in self.profiles.items():
            match = pattern.search(text)
            if match and field not in facts:
                facts[field] = {"value": match[1], "source": "评论自述", "quote": match[0]}
                matches.append(match_details(f"profile-{field}", match, "content", source_url))
        tags = {}
        for field in PROFILE_FIELDS:
            fact = facts.get(field, {})
            value = fact.get("value", "")
            if field == "age":
                value = age_band(value)
            tags[field] = {**fact, "value": value} if value else {"value": "未知", "source": ""}

        negative = self.negative.search(text)
        positive = self.positive.search(self.negative.sub("\n", text) if negative else text)
        for rule_id, match in (("stance-negative", negative), ("stance-positive", positive)):
            if match:
                matches.append(match_details(rule_id, match, "content", source_url))
        stance = {(True, True): "褒贬并存", (True, False): "负面",
                  (False, True): "正面", (False, False): "不明确"}[bool(negative), bool(positive)]
        return {"profile_tags": tags, "stance": stance}, matches

    def promotion_status(self, text, source_url, parents, repeated_sources, author_matches_thread):
        matches = {}
        for kind, (rule_id, pattern) in self.promotion.items():
            match = pattern.search(text)
            if match:
                matches[kind] = match_details(rule_id, match, "text", source_url)
        if self.complaint.search(text):
            matches.pop("contact", None)
            matches.pop("offer", None)
        requests = []
        if matches:
            for field, (parent, parent_source) in zip(("thread", "parent_comment"), parents):
                if match := self.thread_request.search(parent):
                    requests.append(match_details("thread-request", match, field, parent_source))

        if "self" in matches or ("contact" in matches and "offer" in matches):
            return "promotional", [*matches.values(), *requests]
        launch_matches = []
        for rule_id, pattern in self.launch:
            if not (match := pattern.search(text)):
                break
            launch_matches.append(match_details(rule_id, match, "text", source_url))
        if launch_matches and len(launch_matches) == len(self.launch):
            return "promotional", [*launch_matches, *requests]
        if author_matches_thread and parents and not self.complaint.search(text):
            followup_id, followup_pattern = self.followup
            self_id, self_pattern = self.promotion["self"]
            thread, thread_url = parents[0]
            if (pitch := followup_pattern.search(text)) and (origin := self_pattern.search(thread)):
                return "promotional", [match_details(followup_id, pitch, "text", source_url),
                                       match_details(self_id, origin, "thread", thread_url)]
        if repeated_sources and (matches or self.recommendation.search(text)):
            repetition = {"rule_id": "repeated-recommendation", "field": "text", "quote": text[:120],
                          "source_url": source_url, "related_sources": list(repeated_sources)}
            return "unverified", [repetition, *matches.values(), *requests]
        if matches and (requests or "contact" in matches or self.recommendation.search(text)):
            return "unverified", [*matches.values(), *requests]
        return "", []

    def market_evidence(self, record, text, parents, source_url, post):
        if not self.market_segments:
            return {}
        matches = []
        segment = ""
        category = record.get("category") or ""
        named_app = category.startswith("消费级虚拟产品") and platform_name(record) == "App Store"
        catalog = record_kind(record) == "signal" and (record.get("source_tier") in ("公开目录", "登录态目录") or named_app)
        if catalog:
            segment = "virtual_service" if category == "消费级虚拟服务" else "virtual_product"
        for subject, url, field in ((text, source_url, "text"),
                                    *((parent, url, "thread") for parent, url in parents)):
            if segment:
                break
            for name, _, pattern in self.market_segments:
                if match := pattern.search(QUOTED_LINE.sub("", subject)):
                    segment = name
                    matches.append(match_details(f"market-{name}", match, field, url))
                    break
        if not segment and (category.startswith("消费级虚拟产品")
                            or (post or {}).get("category", "").startswith("消费级虚拟产品")):
            segment = "virtual_product"
        if not segment and platform_name(record) in ("Steam", "Notion 模板"):
            segment = "virtual_product"
        if not segment:
            return {}

        role = "listing" if catalog else ""
        for name, _, pattern in self.market_roles:
            if role:
                break
            if match := pattern.search(text):
                role = name
                matches.append(match_details(f"market-{name}", match, "text", source_url))

        facts = {}
        for name, pattern in self.market_facts.items():
            if match := pattern.search(text):
                facts[name] = match[0]
                matches.append(match_details(f"market-{name}", match, "text", source_url))
        if catalog and record.get("rating_or_price"):
            facts["asking_price"] = record["rating_or_price"]
            matches.append({"rule_id": "market-asking_price", "field": "rating_or_price",
                            "quote": record["rating_or_price"], "source_url": source_url})
        if role in ("listing", "seller"):
            for name in ("paid_price", "paid_report"):
                facts.pop(name, None)
            matches = [match for match in matches if match["rule_id"] not in ("market-paid_price", "market-paid_report")]
        elif facts.get("paid_price") or facts.get("paid_report"):
            role = "buyer_feedback"
        return {"segment": segment, "role": role, "facts": facts, "matches": matches}

    def evaluate(self, record, context=((), (), False)):
        kind = record_kind(record)
        platform = platform_name(record)
        if platform == "GitHub Issues":
            text = text_of({**record, "content": github_issue_excerpt(record.get("content") or "")})
        else:
            text = text_of(record)
        if ">" in text:
            text = QUOTED_LINE.sub("", text)
        source_url = record.get("source_url") or record.get("parent_url") or ""
        metric = record.get("metric_primary") or record.get("source_metric") or ""
        intents = []
        demand_intents = []
        matches = []
        for rule_id, label, pattern in (*self.intents, *self.platform_intents.get(platform, ())):
            if rule_id in self.intent_types and kind not in self.intent_types[rule_id]:
                continue
            field = self.intent_fields.get(rule_id, "text")
            subject = text if field == "text" else record.get(field) or ""
            if exclusion := self.intent_exclusions.get(rule_id):
                subject = exclusion.sub("\n", subject)
            if match := pattern.search(subject):
                if parent_pattern := self.intent_parents.get(rule_id):
                    context_matches = []
                    for parent_field, (parent_text, parent_source) in zip(("thread", "parent_comment"), context[0]):
                        if parent_match := parent_pattern.search(QUOTED_LINE.sub("", parent_text)):
                            context_matches.append({**match_details(rule_id, parent_match, parent_field, parent_source),
                                                    "label": label, "label_kind": "intent"})
                    if not context_matches:
                        continue
                    matches.extend(context_matches)
                if label not in intents:
                    intents.append(label)
                if rule_id not in self.context_intents and label not in demand_intents:
                    demand_intents.append(label)
                matches.append({**match_details(rule_id, match, field, source_url), "label": label, "label_kind": "intent"})

        status, promotion_matches = self.promotion_status(text, source_url, *context[:3])
        matches.extend(promotion_matches)
        market = self.market_evidence(record, text, context[0], source_url, context[3] if len(context) > 3 else None)
        consumer = market.get("segment") in ("virtual_product", "virtual_service")
        facts = market.get("facts", {})
        reported_payment = bool(facts.get("paid_price") or facts.get("paid_report"))
        if consumer:
            role = market["role"]
            if role in ("seller", "listing") or metric == "公众号深度拆解":
                demand_intents.clear()
            elif (label := "已付费" if reported_payment else "买家需求" if role == "buyer_request" else ""):
                if label not in intents:
                    intents.append(label)
                if label not in demand_intents:
                    demand_intents.append(label)
        reason = ""
        tags = []
        if kind == "signal":
            if len(text.strip()) < self.min_length and not intents and not status:
                status = "noise"
                reason = f"内容过短(<{self.min_length}字)，缺乏具体痛点上下文"
            if not status and not self.text_exception.search(text) and not self.metric_exception.search(metric) and not self.complaint.search(text):
                for rule_id, pattern in self.noise:
                    if match := pattern.search(text):
                        matches.append(match_details(rule_id, match, "text", source_url))
                        status = "promotional"
                        break
            for rule_id, label, pattern in self.tags:
                match = pattern.search(text)
                field = "text"
                if not match:
                    match = pattern.search(metric)
                    field = "metric_primary"
                if match:
                    tags.append(label)
                    matches.append(match_details(rule_id, match, field, source_url))
        tags.extend(demand_intents)
        status = status or ("eligible" if demand_intents else "context")
        if market:
            independent = status == "eligible" and market["role"] not in ("listing", "seller")
            paid = independent and consumer and reported_payment
            turnaround = facts.get("turnaround", "")
            duration = re.search(r"(\d+(?:\.\d+)?)\s*(分钟|小时|天)", turnaround)
            hours = {"分钟": 1 / 60, "小时": 1, "天": 24}
            quick = (float(duration[1]) * hours[duration[2]] <= 48 if duration
                     else bool(turnaround))
            market["paid_evidence"] = paid
            market["priority"] = (1 + int(bool(facts.get("delivery")))
                                  + int(quick)) if paid else 0
        if status == "promotional":
            reason = "明确推广线索"
        elif status == "unverified":
            reason = "推广线索待核实"
        fields = {field: record[field] for field in SOURCE_FIELDS if record.get(field) not in (None, "")}
        fields.setdefault("platform", platform_name(record))
        fields.setdefault("record_type", kind)
        labels, label_matches = self.labels(record, source_url) if kind == "comment" else ({}, [])
        if kind == "comment":
            topics = []
            for rule_id, label, pattern in self.comment_topics:
                if match := pattern.search(text):
                    if label not in topics:
                        topics.append(label)
                    matches.append({**match_details(rule_id, match, "text", source_url), "label": label, "label_kind": "topic"})
            labels["topic_tags"] = topics
        return {
            "schema_version": SCHEMA_VERSION, "rule_version": self.version,
            "id": record.get("id", record.get("comment_id")), "fields": fields,
            "evidence_status": status, "counts_as_demand": status == "eligible",
            "is_noise": int(status in ("noise", "promotional")), "noise_reason": reason,
            "intents": intents, "pain_tags": tags or ["基础赛道线索"], "matches": [*matches, *label_matches],
            "market": market,
            **labels,
        }

    def evaluate_batch(self, records):
        for record, context in zip(records, self.contexts(records)):
            yield self.evaluate(record, context)


@lru_cache(maxsize=1)
def default_rules():
    return EvidenceRules(RULE_PATH)


def main():
    parser = argparse.ArgumentParser(description="Evaluate a UTF-8 JSONL batch with offline evidence rules.")
    parser.add_argument("input", help="JSONL file or - for stdin")
    parser.add_argument("--rules", type=Path, default=RULE_PATH)
    parser.add_argument("--output", type=Path, help="Write UTF-8 JSONL to this file")
    args = parser.parse_args()
    try:
        content = sys.stdin.buffer.read().decode("utf-8-sig") if args.input == "-" else Path(args.input).read_text(encoding="utf-8-sig")
        records = [json.loads(line) for line in content.splitlines() if line.strip()]
        if any(not isinstance(record, dict) for record in records):
            raise ValueError("Each input line must be a JSON object")
        rules = EvidenceRules(args.rules)
        result = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rules.evaluate_batch(records))
        if args.output:
            args.output.write_text(result, encoding="utf-8", newline="\n")
        else:
            sys.stdout.buffer.write(result.encode("utf-8"))
    except (OSError, TypeError, ValueError, KeyError, re.error) as exc:
        parser.exit(2, f"evidence_rules: {exc}\n")


if __name__ == "__main__":
    main()
