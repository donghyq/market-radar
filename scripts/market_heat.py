"""Group evidence for market trends using verified source dates."""

from datetime import date
from urllib.parse import urlsplit, urlunsplit

from evidence.record_identity import appstore_id, normalized_text, signal_origin
from evidence_rules import platform_name
from rules.classification import default_classifier
from signal_time import observed_now, source_day, source_time


CATALOGS = ("Steam", "Notion 模板", "京东服务", "Google Play", "TapTap")
LEGACY_REVIEWS = ("AppStore中国区差评", "B站评论区痛点")
RELEASE_SOURCES = {
    "appstore_release_date": "产品上架",
    "steam_store_release": "产品上架",
    "taptap_store_release": "产品上架",
    "product_version_release": "版本发布",
    "service_listing_published": "服务发布",
}
METRICS = ("discussion", "demand", "production")


def is_comment(row):
    return row.get("record_type") == "comment"


def legacy_review(row):
    return row.get("channel", "").startswith(LEGACY_REVIEWS)


def catalog_record(row):
    channel = row.get("channel", "")
    return (channel in CATALOGS or channel.startswith(("AppStore应用", "App Store 应用"))
            or row.get("source_tier") in ("公开目录", "登录态目录"))


def product_key(row):
    url = row.get("parent_url" if is_comment(row) else "source_url") or ""
    if app := appstore_id(url):
        return f"appstore:{app}"
    origin = signal_origin(row.get("channel") or "", url)
    if origin.startswith("github-issue:"):
        return "github-repo:" + origin.split(":", 1)[1].rsplit("/", 1)[0]
    if origin.startswith(("steam:", "notion:", "jd:", "goofish:", "github-repo:", "google-play:", "taptap:")):
        return origin
    return ""


def post_key(row, url):
    """Use the same source identities as ingestion before comparing public URLs."""
    if app := appstore_id(url):
        return f"appstore:{app}"
    channel = platform_name(row)
    if (key := signal_origin(channel, url)) and not key.startswith("github-repo:"):
        return key
    try:
        parsed = urlsplit(url)
    except ValueError:
        return ""
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.path in ("", "/"):
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), parsed.query, ""))


def product_entries(posts):
    for row in posts:
        key = product_key(row)
        if not key:
            continue
        if key.startswith("github-repo:"):
            name = key.split(":", 1)[1].rsplit("/", 1)[1]
        elif legacy_review(row):
            name = row.get("author_or_app")
        else:
            name = row.get("title")
        yield key, name, row, not key.startswith(("jd:", "goofish:"))


def classify_market_records(records, classifier=None):
    classifier = classifier or default_classifier()
    posts = sorted((row for row in records if not is_comment(row)), key=lambda row: (legacy_review(row), row["id"]))
    index = classifier.product_index(product_entries(posts))
    parents = {}
    groups = {}
    for row in posts:
        groups[row["display_id"]] = classifier.classify(row, index, source_product=product_key(row))
        if not legacy_review(row) and (key := post_key(row, row.get("source_url") or "")):
            parents.setdefault(key, row["display_id"])

    for row in records:
        if is_comment(row):
            parent_id = parents.get(post_key(row, row.get("parent_url") or ""), "")
            groups[row["display_id"]] = classifier.classify(
                row, index, source_product=product_key(row), parent=groups.get(parent_id), parent_id=parent_id,
            )
    return groups, index.products


def metrics_for(row):
    if row.get("is_noise") or row.get("evidence_status") in ("noise", "promotional", "unverified"):
        return []
    release = row.get("published_time_source") in RELEASE_SOURCES and not is_comment(row)
    channel = row.get("channel", "")
    discussion = is_comment(row) or legacy_review(row) or not (
        release or catalog_record(row) or channel.startswith(("闲鱼", "蝉妈妈", "GitHub开源", "GitHub近期"))
    )
    demand = row.get("counts_as_demand") is True and (is_comment(row) or not catalog_record(row))
    return [name for name, active in zip(METRICS, (discussion, demand, release)) if active]


def record_identity(row, url_key):
    if is_comment(row):
        return "comment", platform_name(row), row.get("comment_id") or row["id"]
    if legacy_review(row):
        return "legacy_review", url_key, normalized_text(row.get("content") or row.get("title"))
    if row.get("published_time_source") == "product_version_release":
        return "release", url_key or row["id"], row.get("app_version") or row.get("source_published_at")
    if url_key:
        return "signal", url_key
    return "signal", row["id"]


def verified_coverage(archives, as_of, labels):
    """Only explicit full-coverage reports can establish a zero for a scope."""
    coverage = set()
    group_labels = set(labels.values())
    for archive in archives:
        for row in archive.get("market_heat_coverage", []):
            day = source_day(row.get("date") or "")
            metric = row.get("metric")
            scope = row.get("category") or ""
            category = labels.get(scope, scope)
            if category and category not in group_labels:
                continue
            if row.get("complete") is True and day and day <= as_of and metric in METRICS:
                coverage.add((day, category, row.get("product") or "", metric))
    return sorted(coverage)


def build_market_heat(records, archives=(), *, as_of: date | None = None):
    """Emit the deduplicated dated and undated evidence used by both dashboard exports."""
    as_of_time = observed_now() if as_of is None else ""
    today = as_of.isoformat() if as_of else source_day(as_of_time)
    classifier = default_classifier()
    groups, products = classify_market_records(records, classifier)

    events = []
    seen = set()
    releases = set()
    used_products = set()
    for row in records:
        metrics = metrics_for(row)
        if not metrics:
            continue
        url_key = post_key(row, row.get("parent_url" if is_comment(row) else "source_url") or "")
        identity = record_identity(row, url_key)
        if identity in seen:
            continue
        seen.add(identity)
        group = groups[row["display_id"]]
        category, product = group["category"], group["product_id"]
        source_timestamp = row.get("source_published_at") or ""
        day = source_day(source_timestamp)
        day = day if day and day <= today and row.get("published_time_source") != "legacy_archive_date" else ""
        release = RELEASE_SOURCES.get(row.get("published_time_source")) if "production" in metrics else None
        if release:
            version = (row.get("app_version") or url_key) if release == "版本发布" else ""
            release_key = (product or url_key or identity, release, day, version)
            if release_key in releases:
                metrics.remove("production")
            releases.add(release_key)
        if not metrics:
            continue
        if product:
            used_products.add(product)
        event = {"day": day, "category": category, "product": product, "id": row["display_id"], "metrics": metrics}
        timestamp, precision = source_time(source_timestamp)
        if day and precision == "timestamp":
            event["timestamp"] = timestamp
        if release:
            event["release"] = release
        events.append(event)

    coverage = verified_coverage(archives, today, classifier.labels)
    categories = {event["category"] for event in events}
    categories.update(category for _, category, _, _ in coverage if category)
    used_products.update(product for _, _, product, _ in coverage if product)
    return {
        "as_of": today,
        "as_of_time": as_of_time,
        "classification_version": classifier.version,
        "record_groups": groups,
        "categories": sorted(categories),
        "products": {key: value for key, value in products.items() if key in used_products},
        "events": events,
        "coverage": coverage,
    }
