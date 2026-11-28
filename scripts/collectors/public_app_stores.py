"""Collect catalog details and a bounded sample of reviews visible on public store pages."""

import json
import re
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

from collectors.consumer_sources import PRODUCT, read_public_page, save_catalog_item
from evidence.user_comments import PUBLIC_REVIEW_LIMIT
from radar_cli import strip_html
from signal_time import source_time


GOOGLE_PLAY = "https://play.google.com/store/apps/details"
TAPTAP = "https://www.taptap.cn"


def catalog_metadata(page, kind):
    for payload in re.findall(r'<script\b[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S):
        try:
            item = json.loads(payload)
        except ValueError:
            continue
        if isinstance(item, dict) and item.get("@type") == kind and item.get("name"):
            return item
    raise ValueError("公开商店页没有商品资料")


def review_day(label):
    match = re.search(r"(\d{4})[年/](\d{1,2})[月/](\d{1,2})", label)
    if match:
        day = "-".join(part.zfill(2) for part in match.groups())
        return source_time(day)[0]
    for date_format in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(label.strip(), date_format).date().isoformat()
        except ValueError:
            continue
    return ""


def google_play_reviews(page, url, package):
    cards = re.finditer(r'<header\b[^>]*\bdata-review-id="([a-z0-9-]+)"[^>]*>(.*?)</header>'
                       r'\s*<div class="h3YV2d"[^>]*>(.*?)</div>', page, re.S | re.I)
    for card in cards:
        review_id, header, body = card.groups()
        if not (content := strip_html(body)):
            continue
        date = re.search(r'<span class="bp9Aid"[^>]*>([^<]+)</span>', header)
        rating = re.search(r'aria-label="(?:获评|Rated)\s*([1-5])\s*(?:颗星|stars?)', header)
        yield {
            "channel": "Google Play", "comment_id": review_id, "thread_id": package,
            "parent_url": url, "source_url": url + "&reviewId=" + review_id,
            "content": content, "commented_at": review_day(date[1]) if date else "",
            "comment_time_source": "google_play_review_date",
            "source_metric": f"{rating[1]} 星" if rating else "",
        }


def taptap_reviews(page, url, app_id):
    cards = re.split(r'<div\b[^>]*class="[^"<>]*\breview-item\s+review-item--in-app-tab"[^>]*>', page)[1:]
    for card in cards:
        review = re.search(r'<a\b[^>]*href="/review/(\d+)"[^>]*>(.*?)</a>', card, re.S)
        if not review or not (content := strip_html(review[2])):
            continue
        date = re.search(r'<span\b[^>]*class="[^"]*review-item__updated-time"[^>]*title="([^"]+)"', card)
        if not date:
            date = re.search(r'<span\b[^>]*class="review-item__modified-tip"[^>]*>([^<]+)</span>', card)
        day = review_day(date[1]) if date else ""
        yield {
            "channel": "TapTap", "comment_id": review[1], "thread_id": app_id,
            "parent_url": url, "source_url": f"{TAPTAP}/review/{review[1]}",
            "content": content, "commented_at": day,
            "comment_time_source": "taptap_review_update_date", "source_updated_at": day,
        }


def save_store_app(conn, channel, category, term, url, item, reviews, *, released="", release_source=""):
    rating = item.get("aggregateRating") or {}
    count = str(rating.get("ratingCount") or "")
    offers = item.get("offers") or []
    offer = offers[0] if isinstance(offers, list) and offers else offers
    price = str(offer.get("price") or "") if isinstance(offer, dict) else ""
    currency = offer.get("priceCurrency") if isinstance(offer, dict) else ""
    purchase = f"{currency} {price}" if currency and re.fullmatch(r"(?:[1-9]\d*(?:\.\d+)?|0\.\d*[1-9]\d*)", price) else ""
    title = strip_html(item["name"])
    return save_catalog_item(
        conn, channel, f"{PRODUCT} / {category}", term, url, title,
        strip_html(item.get("description") or "") or title,
        price=purchase, reviews=reviews, released=released, release_source=release_source,
        metric=f"平台总评 {count} 条" if count.isdecimal() else "平台目录信息",
    )


def collect_google_play(conn, targets, *, fetch=read_public_page):
    for category, package in targets:
        if not re.fullmatch(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+", package):
            continue
        url = f"{GOOGLE_PLAY}?id={package}"
        chinese = url + "&hl=zh_CN&gl=US"
        try:
            page = fetch(chinese)
            item = catalog_metadata(page, "SoftwareApplication")
            published_url = urlsplit(item.get("url") or "")
            if published_url.hostname != "play.google.com" or parse_qs(published_url.query).get("id") != [package]:
                raise ValueError("公开商店页没有对应应用")
            reviews = {row["comment_id"]: row for row in google_play_reviews(page, url, package)}
            if len(reviews) < PUBLIC_REVIEW_LIMIT:
                english = url + "&hl=en_US&gl=US"
                try:
                    for row in google_play_reviews(fetch(english), url, package):
                        row["source_url"] += "&hl=en_US&gl=US"
                        reviews.setdefault(row["comment_id"], row)
                except (OSError, ValueError) as exc:
                    print(f"[WARN] Google Play 英文页未获取 ({package}): {exc}")
            yield save_store_app(conn, "Google Play", category, package, url, item, reviews.values())
        except (OSError, ValueError, TypeError) as exc:
            print(f"[WARN] Google Play 公开页未获取 ({package}): {exc}")


def collect_taptap(conn, targets, *, fetch=read_public_page):
    for category, app_id in targets:
        if not re.fullmatch(r"[1-9]\d*", app_id):
            continue
        url = f"{TAPTAP}/app/{app_id}"
        try:
            page = fetch(url + "/review")
            item = catalog_metadata(page, "VideoGame")
            if item.get("@id") != url:
                raise ValueError("公开评价页没有对应商品")
            reviews = list(taptap_reviews(page, url, app_id))
            yield save_store_app(conn, "TapTap", category, app_id, url, item, reviews,
                                 released=item.get("datePublished") or "", release_source="taptap_store_release")
        except (OSError, ValueError, TypeError) as exc:
            print(f"[WARN] TapTap 公开评价页未获取 ({app_id}): {exc}")
