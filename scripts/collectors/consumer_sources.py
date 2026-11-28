"""Read small samples from public catalogs and their visible review pages."""

import hashlib
import json
import pathlib
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

import radar_cli
from evidence.user_comments import save_comment
from signal_time import market_today, source_time


CONFIG = pathlib.Path(__file__).resolve().parents[2] / "config" / "consumer_queries.json"
STEAM = "https://store.steampowered.com"
STEAM_COMMUNITY = "https://steamcommunity.com"
NOTION = "https://www.notion.com"
JD = "https://www.jd.com"
PRODUCT = "消费级虚拟产品"
SERVICE = "消费级虚拟服务"
UNAVAILABLE = "评论未获取"
USER_AGENT = "MarketRadar/0.2.2"
UNRELATED_LISTING = re.compile(r"无痕改字|改数字|印章|去水印|破解|激活码|刷单|论文代写")


class PageLinks(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.links = []
        self.feed(page)
        self.close()

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append(dict(attrs))


def consumer_queries():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def read_public_page(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(request, timeout=8) as response:
        requested = urllib.parse.urlsplit(url)
        final = urllib.parse.urlsplit(response.geturl())
        if final.hostname != requested.hostname or final.path.rstrip("/") != requested.path.rstrip("/"):
            raise ValueError("公开页面重定向")
        if response.headers.get_content_type() != "text/html":
            raise ValueError("公开页面没有 HTML")
        data = response.read(3_000_001)
        if len(data) > 3_000_000:
            raise ValueError("公开页面超过采样大小")
        return data.decode(response.headers.get_content_charset() or "utf-8", errors="replace")


def save_catalog_item(conn, channel, category, term, url, title, description, *, price="", reviews=None,
                      released=""):
    status = "公开评价节选" if reviews else UNAVAILABLE
    with conn:
        added = radar_cli.insert_signal(
            conn, channel, "公开目录", category, term, title, description, "",
            "平台目录信息", status, price, url,
            source_published_at=released, published_time_source="steam_store_release" if released else "",
        )
        return int(added), sum(save_comment(conn, review, refresh=True) for review in reviews or ())


def steam_items(page):
    for match in re.finditer(r'<a\b([^>]*\bsearch_result_row\b[^>]*)>(.*?)</a>', page, re.S):
        attributes, markup = match.groups()
        id_match = re.search(r'\bdata-ds-appid="([1-9]\d*)"', attributes)
        title_match = re.search(r'<span class="title">([^<]+)</span>', markup)
        if not id_match or not title_match:
            continue
        price_match = re.search(r'<div class="(?:discount_final_price|search_price[^"]*)">\s*([^<]+)', markup)
        released = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', markup)
        day = "-".join(part.zfill(2) for part in released.groups()) if released else ""
        yield id_match[1], radar_cli.strip_html(title_match[1]), radar_cli.strip_html(price_match[1]) if price_match else "", day


def steam_review_date(text):
    match = re.search(r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if not match:
        return ""
    year, month, day = match.groups()
    today = market_today()
    year = year or str(today.year - ((int(month), int(day)) > (today.month, today.day)))
    return source_time(f"{year}-{int(month):02d}-{int(day):02d}")[0]


def steam_reviews(page, app_id, parent_url):
    for card in re.split(r'(?=<div\b[^>]*class="apphub_Card )', page)[1:]:
        link = re.search(r'data-modal-content-url="(https://steamcommunity\.com/(?:id|profiles)/([^/"]+)/recommended/'
                         + re.escape(app_id) + r'/)"', card)
        body = re.search(r'class="apphub_CardTextContent">\s*<div class="date_posted">(.*?)</div>(.*?)</div>', card, re.S)
        if not link or not body or not (content := radar_cli.strip_html(body[2])):
            continue
        rating = re.search(r'<div class="title">(不推荐|推荐)</div>', card)
        yield {
            "channel": "Steam", "comment_id": f"{app_id}:{link[2].casefold()}", "parent_url": parent_url,
            "source_url": link[1], "content": content, "commented_at": steam_review_date(body[1]),
            "comment_time_source": "steam_public_review_date", "source_metric": rating[1] if rating else "",
        }


def collect_steam(conn, terms, *, fetch=read_public_page):
    seen = set()
    for term in terms:
        try:
            query = urllib.parse.urlencode({"term": term, "l": "schinese", "cc": "cn"})
            item = next((row for row in steam_items(fetch(f"{STEAM}/search/?{query}")) if row[0] not in seen), None)
            if not item:
                continue
            app_id, title, price, day = item
            seen.add(app_id)
            url = f"{STEAM}/app/{app_id}/"
            try:
                reviews_url = (f"{STEAM_COMMUNITY}/app/{app_id}/reviews/"
                               "?browsefilter=mostrecent&l=schinese&filterLanguage=schinese")
                reviews = list(steam_reviews(fetch(reviews_url), app_id, url))[:5]
            except (OSError, ValueError) as exc:
                print(f"[WARN] Steam 公开评测未获取 ({app_id}): {exc}")
                reviews = None
            yield save_catalog_item(
                conn, "Steam", PRODUCT, term, url, title, title,
                price=price, reviews=reviews, released=day,
            )
        except (OSError, ValueError) as exc:
            print(f"[WARN] Steam 目录采集跳过 ({term}): {exc}")


def notion_product(page):
    for payload in re.findall(r'<script\b[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S):
        try:
            item = json.loads(payload)
        except ValueError:
            continue
        if isinstance(item, dict) and item.get("@type") == "Product" and item.get("name"):
            return item
    raise ValueError("公开模板页没有商品数据")


def notion_reviews(item, url, slug):
    for review in item.get("review", [])[:5]:
        name = review.get("name") or ""
        body = review.get("reviewBody") or ""
        author = (review.get("author") or {}).get("name") or ""
        date = review.get("datePublished") or ""
        if not body.strip():
            continue
        identity = "\n".join((slug, date, author or name or body))
        rating = (review.get("reviewRating") or {}).get("ratingValue")
        yield {
            "channel": "Notion 模板", "comment_id": hashlib.sha256(identity.encode()).hexdigest()[:24],
            "parent_url": url, "source_url": url, "author_or_app": author,
            "content": f"{name}\n{body}" if name and name != body else body,
            "commented_at": date, "comment_time_source": "notion_marketplace_review_date",
            "source_metric": f"{rating} 星" if rating is not None else "",
        }


def collect_notion(conn, slugs, *, fetch=read_public_page):
    for slug in slugs:
        if not re.fullmatch(r"[a-z0-9-]+", slug):
            continue
        url = f"{NOTION}/templates/{slug}"
        try:
            item = notion_product(fetch(url))
            offer = item.get("offers") or {}
            value, currency = offer.get("price"), offer.get("priceCurrency")
            price = f"{currency} {value}" if isinstance(value, (int, float)) and currency else ""
            yield save_catalog_item(
                conn, "Notion 模板", PRODUCT, slug, url, item["name"], item.get("description") or item["name"],
                price=price, reviews=list(notion_reviews(item, url, slug)),
            )
        except (OSError, ValueError, TypeError) as exc:
            print(f"[WARN] Notion 模板采集跳过 ({slug}): {exc}")


def jd_items(page, pattern):
    seen = set()
    for link in PageLinks(page).links:
        if "price-href" not in (link.get("class") or "").split():
            continue
        url = re.fullmatch(r"(?:https:)?//item\.jd\.com/(\d+)\.html", link.get("href") or "")
        title = (link.get("title") or "").strip()
        if not url or url[1] in seen or UNRELATED_LISTING.search(title) or not re.search(pattern, title, re.I):
            continue
        seen.add(url[1])
        yield f"https://item.jd.com/{url[1]}.html", title


def collect_jd(conn, categories, *, fetch=read_public_page):
    for category, path, pattern in categories:
        try:
            items = list(jd_items(fetch(f"{JD}/{path}"), pattern))[:2]
            for url, title in items:
                yield save_catalog_item(conn, "京东服务", SERVICE, category, url, title, title)
        except (OSError, ValueError) as exc:
            print(f"[WARN] 京东公开服务目录采集跳过 ({category}): {exc}")
