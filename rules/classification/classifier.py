"""Classify records using source IDs, product aliases, and topic rules."""

import json
import re
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path


RULE_PATH = Path(__file__).with_name("classification_rules.json")
UNKNOWN = "unclassified"
ASCII_WORD = re.compile(r"[a-z0-9]")


def normalize(text):
    return " ".join(unicodedata.normalize("NFKC", text or "").casefold().split())


def alias_pattern(alias):
    prefix = r"(?<![a-z0-9])" if ASCII_WORD.fullmatch(alias[0]) else ""
    suffix = r"(?![a-z0-9])" if ASCII_WORD.fullmatch(alias[-1]) else ""
    return prefix + re.escape(alias) + suffix


class ProductIndex:
    def __init__(self, products, sources, aliases):
        self.products = products
        self.sources = sources
        self.aliases = aliases
        patterns = [alias_pattern(alias) for alias in sorted(aliases, key=lambda text: (-len(text), text))]
        self.pattern = re.compile("|".join(patterns)) if patterns else None

    def mentioned(self, text):
        matches = set()
        if self.pattern:
            for match in self.pattern.finditer(text):
                for key, context in self.aliases[match[0]].items():
                    if context is None or context.search(text):
                        matches.add(key)
        return matches


class MarketClassifier:
    def __init__(self, path=RULE_PATH):
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        if config["schema_version"] != 1:
            raise ValueError("Unsupported classification rule schema")
        self.version = config["rule_version"]
        self.topic_labels = {row["id"]: row["label"] for row in config["categories"]}
        groups = config.get("groups", [
            {"id": topic, "label": label, "topics": [topic]} for topic, label in self.topic_labels.items()
        ])
        self.topic_groups = {topic: group["id"] for group in groups for topic in group["topics"]}
        if (self.topic_groups.keys() != self.topic_labels.keys()
                or len(self.topic_groups) != sum(len(group["topics"]) for group in groups)):
            raise ValueError("Classification groups must contain each topic exactly once")
        self.labels = {group["id"]: group["label"] for group in groups}
        self.topic_labels[UNKNOWN] = "待分类"
        self.topic_groups[UNKNOWN] = UNKNOWN
        self.labels[UNKNOWN] = "待分类"
        self.patterns = [(row["id"], re.compile(row["pattern"], re.I)) for row in config["categories"]]
        self.contexts = {normalize(value): row["id"] for row in config["categories"]
                         for value in (*row.get("context", []), row["label"])}
        self.named_products = config["products"]
        self.generic_aliases = {normalize(text) for text in config.get("generic_aliases", [])}

    def describe_topic(self, topic):
        group = self.topic_groups[topic]
        return {"category_id": group, "category": self.labels[group],
                "topic_id": topic, "topic": self.topic_labels[topic]}

    def category(self, record, product_name=""):
        for field, text in (("product_name", product_name), ("title", record.get("title"))):
            if group := self.match_topic(text):
                return group, field
        for field in ("category", "query_term"):
            value = normalize(record.get(field))
            if group := self.contexts.get(value):
                return group, field
            if " / " in value and (group := self.contexts.get(value.rsplit(" / ", 1)[1])):
                return group, field
        if group := self.match_topic(record.get("content")):
            return group, "content"
        return UNKNOWN, ""

    def match_topic(self, text):
        value = normalize(text)
        if value:
            return next((group for group, pattern in self.patterns if pattern.search(value)), "")
        return ""

    def product_index(self, entries):
        """Use the caller's canonical source IDs and product names to build a reusable index."""
        products = {}
        sources = {}
        aliases = defaultdict(dict)
        for rule in self.named_products:
            key = "name:" + rule["id"]
            products[key] = {"name": rule["name"], **self.describe_topic(rule["category"])}
            for source in rule.get("source_ids", []):
                sources[source] = key
            constraints = {normalize(alias): re.compile(pattern, re.I)
                           for alias, pattern in rule.get("alias_context", {}).items()}
            for name in (rule["name"], *rule.get("aliases", [])):
                alias = normalize(name)
                aliases[alias][key] = constraints.get(alias)

        for source, name, record, allow_alias in entries:
            if not name:
                continue
            key = sources.setdefault(source, source)
            candidates = [name]
            if source.startswith("appstore:"):
                lead = re.split(r"[-—:：|]", name, maxsplit=1)[0].strip()
                if normalize(lead) not in self.generic_aliases and len(lead) >= 3:
                    candidates.append(lead)
            topic, _ = self.category(record, name)
            products.setdefault(key, {"name": candidates[-1], **self.describe_topic(topic)})
            if allow_alias:
                for candidate in candidates:
                    alias = normalize(candidate)
                    if len(alias) >= 3 and alias not in self.generic_aliases:
                        aliases[alias].setdefault(key, None)
        return ProductIndex(products, sources, aliases)

    def classify(self, record, index, *, source_product="", parent=None, parent_id=""):
        if parent and (parent["category_id"] != UNKNOWN or parent["product_id"]):
            return {**parent, "basis": "parent", "inherited_from": parent_id}

        product = index.sources.get(source_product, "")
        basis = "source_id" if product else ""
        if not product:
            for field in ("title", "content"):
                matches = index.mentioned(normalize(record.get(field)))
                if matches:
                    if len(matches) == 1:
                        product = next(iter(matches))
                        basis = "alias_" + field
                    break
        definition = index.products.get(product)
        if definition:
            topic = definition["topic_id"]
        else:
            topic, basis = self.category(record)
        return {**self.describe_topic(topic), "product_id": product,
                "product_name": definition["name"] if definition else "", "basis": basis or "unknown"}


@lru_cache(maxsize=1)
def default_classifier():
    return MarketClassifier()
