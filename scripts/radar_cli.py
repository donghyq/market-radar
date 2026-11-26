#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Market Radar CLI (中国互联网真实商机挖掘与AI锐评立项评估引擎)
支持：
1. 线上免反爬真实信号采集：
   - Apple 中国区 App Store 工具榜及 1~3 星付费痛点差评 RSS
   - Bilibili 真实视频热度、收藏比（Favorites/Play）与高赞评论痛点
   - 搜狗微信公众号真实商业拆解与实战痛点文章检索
2. 本地 inbox/ CSV 报表导入（兼容蝉妈妈、闲鱼、小红书导出表）
3. 硬规则清洗去噪（剔除导流软文、低互动水贴、重复 URL）
4. “AI锐评”五维立项打分（对团队既有想法做诊断改造 + 挖掘高确定性新方向）
5. 导出双击即开的本地交互式 HTML 商机工作台与 CSV 报表
"""

import argparse
import csv
import datetime
import html
import http.cookiejar
import json
import os
import pathlib
import re
import sqlite3
import ssl
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from signal_time import epoch_time, market_today, newest_results, observed_now, source_day, source_time
from user_comments import save_comment

BASE_WORKSPACE = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = BASE_WORKSPACE / "radar.db"
INBOX_DIR = BASE_WORKSPACE / "inbox"
EXPORT_DIR = BASE_WORKSPACE / "exports"
HTML_PATH = BASE_WORKSPACE / "index.html"

SSL_CTX = ssl._create_unverified_context()
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_conn(db_path: pathlib.Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL,
            source_tier TEXT NOT NULL,
            category TEXT NOT NULL,
            query_term TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            author_or_app TEXT DEFAULT '',
            metric_primary TEXT DEFAULT '',
            metric_secondary TEXT DEFAULT '',
            rating_or_price TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            pain_tags TEXT DEFAULT '',
            is_noise INTEGER DEFAULT 0,
            noise_reason TEXT DEFAULT '',
            collected_at TEXT NOT NULL,
            published_at TEXT DEFAULT '',
            freshness_tier TEXT DEFAULT '30d_active',
            audience_tag TEXT DEFAULT '',
            persona_note TEXT DEFAULT '',
            UNIQUE(channel, title, author_or_app)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            group_type TEXT NOT NULL,
            title TEXT NOT NULL,
            status_badge TEXT NOT NULL,
            one_liner TEXT NOT NULL,
            origin_context TEXT NOT NULL,
            target_buyer TEXT NOT NULL,
            current_workaround TEXT NOT NULL,
            product_form TEXT NOT NULL,
            pricing_model TEXT NOT NULL,
            score_payment INTEGER NOT NULL,
            score_acquisition INTEGER NOT NULL,
            score_delivery INTEGER NOT NULL,
            score_competition INTEGER NOT NULL,
            score_validation INTEGER NOT NULL,
            total_score INTEGER NOT NULL,
            bear_case_risks TEXT NOT NULL,
            pivot_advice TEXT NOT NULL,
            validation_48h_plan TEXT NOT NULL,
            match_categories TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    from persona_and_freshness import ensure_columns
    from user_comments import init_comments
    init_comments(conn)
    ensure_columns(conn)


def strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", "", text)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def insert_signal(
    conn: sqlite3.Connection,
    channel: str,
    source_tier: str,
    category: str,
    query_term: str,
    title: str,
    content: str,
    author_or_app: str,
    metric_primary: str,
    metric_secondary: str,
    rating_or_price: str,
    source_url: str,
    published_at: str = "",
    collected_at: str = "",
    *,
    source_published_at: str = "",
    published_time_source: str = "",
    observed_at: Optional[str] = None,
    signal_id: Optional[int] = None,
) -> bool:
    raw_time, precision = source_time(source_published_at)
    observed_at = observed_now() if observed_at is None else observed_at
    author = author_or_app[:100]
    title = title[:200]
    cur = conn.cursor()
    # Skip known duplicates before SQLite allocates an AUTOINCREMENT value.
    cur.execute(
        """
        INSERT OR IGNORE INTO raw_signals (
            id, channel, source_tier, category, query_term, title, content,
            author_or_app, metric_primary, metric_secondary, rating_or_price,
            source_url, collected_at, published_at, source_published_at,
            published_time_source, published_time_precision, observed_at
        ) SELECT
            CASE WHEN EXISTS (SELECT 1 FROM raw_signals WHERE id = ?) THEN NULL ELSE ? END,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        WHERE NOT EXISTS (
            SELECT 1 FROM raw_signals WHERE channel=? AND title=? AND author_or_app=?
        )
        """,
        (
            signal_id, signal_id, channel,
            source_tier,
            category,
            query_term,
            title,
            content[:1000],
            author,
            metric_primary[:80],
            metric_secondary[:80],
            rating_or_price[:80],
            source_url[:500],
            collected_at or now_str(),
            (published_at or raw_time or (collected_at or now_str())[:10])[:10],
            raw_time,
            published_time_source if raw_time else "",
            precision,
            observed_at,
            channel, title, author,
        ),
    )
    added = cur.rowcount > 0
    if not added and raw_time:
        cur.execute(
            """UPDATE raw_signals SET source_published_at=?, published_time_source=?,
               published_time_precision=?, observed_at=COALESCE(NULLIF(observed_at, ''), ?)
               WHERE channel=? AND title=? AND author_or_app=?
                 AND (COALESCE(source_published_at, '')='' OR
                      (published_time_precision='date' AND ?='timestamp'))""",
            (raw_time, published_time_source, precision, observed_at, channel, title, author, precision),
        )
    return added


def appstore_review_comment(entry, app_id):
    review_id = str((entry.get("id") or {}).get("label") or "").strip()
    content = (entry.get("content") or {}).get("label") or ""
    if not review_id or not content.strip():
        return None
    title = ((entry.get("title") or {}).get("label") or "").strip()
    reviewer = (entry.get("author") or {}).get("name") or {}
    rating = (entry.get("im:rating") or {}).get("label") or ""
    return {
        "channel": "App Store",
        "comment_id": review_id,
        "parent_url": f"https://apps.apple.com/cn/app/id{app_id}",
        "content": f"{title}\n{content}" if title and title != content.strip() else content,
        "author_or_app": reviewer.get("label", ""),
        "commented_at": (entry.get("updated") or {}).get("label") or "",
        "comment_time_source": "appstore_review_updated",
        "source_metric": f"{rating} 星" if rating else "",
    }


def save_appstore_feedback(conn, app, category, term, reviews):
    if not reviews:
        return 0
    app_id = app["trackId"]
    channel = "AppStore应用(实时API)"
    parent_url = reviews[0]["parent_url"]
    existing = conn.execute(
        "SELECT id FROM raw_signals WHERE channel=? AND source_url=?", (channel, parent_url)
    ).fetchone()
    added = False
    if existing is None:
        name = app.get("trackName") or f"App Store 应用 {app_id}"
        rating_count = app.get("userRatingCount") or 0
        average = round(float(app.get("averageUserRating") or 0), 2)
        added = insert_signal(
            conn=conn, channel=channel, source_tier="实时API抓取", category=category, query_term=term,
            title=name, content=strip_html(app.get("description") or "") or f"App Store 应用：{name}",
            author_or_app=f"App Store #{app_id}", metric_primary=f"App总评 {rating_count} 条",
            metric_secondary=f"均分 {average}", rating_or_price="",
            source_url=parent_url, source_published_at=app.get("releaseDate") or "",
            published_time_source="appstore_release_date",
        )
    for comment in reviews:
        save_comment(conn, comment)
    return int(added)


def collect_appstore(conn: sqlite3.Connection, custom_queries: Optional[List[Tuple[str, str]]] = None) -> int:
    """采集中国区 App Store 工具应用及最新 1~3 星真实付费用户差评"""
    queries = custom_queries or [
        ("教培与督学工具", "错题 试卷"),
        ("教培与督学工具", "学习计划 考研 打卡"),
        ("知识视频与口播工具", "提词器 字幕 视频剪辑"),
        ("垂直B端与效率工具", "扫描 合同 报价 开单"),
    ]
    added = 0
    pain_keywords = ["扣费", "会员", "太贵", "不好用", "闪退", "客服", "导出", "限制", "套路", "收费", "垃圾", "微信", "打印"]
    for category, term in queries:
        try:
            search_url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(
                {"term": term, "country": "cn", "entity": "software", "limit": 3}
            )
            req = urllib.request.Request(search_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            for app in data.get("results", []):
                track_id = str(app.get("trackId") or "")
                rating_cnt = app.get("userRatingCount") or 0
                if not track_id.isdecimal() or rating_cnt < 100:
                    continue
                rss_url = f"https://itunes.apple.com/cn/rss/customerreviews/page=1/id={track_id}/sortby=mostrecent/json"
                rss_req = urllib.request.Request(rss_url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(rss_req, timeout=10, context=SSL_CTX) as r_resp:
                    rss_data = json.loads(r_resp.read().decode("utf-8", errors="ignore"))
                entries = rss_data.get("feed", {}).get("entry", [])
                if isinstance(entries, dict):
                    entries = [entries]
                reviews = []
                for entry in entries:
                    rating = entry.get("im:rating", {}).get("label", "")
                    if rating not in ("1", "2", "3"):
                        continue
                    pub = entry.get("updated", {}).get("label", "") or ""
                    pub_dt = source_day(pub)
                    if pub_dt and (market_today() - datetime.date.fromisoformat(pub_dt)).days > 180:
                        continue
                    r_title = strip_html(entry.get("title", {}).get("label", ""))
                    r_content = strip_html(entry.get("content", {}).get("label", ""))
                    combined = f"{r_title} {r_content}"
                    if any(k in combined for k in pain_keywords) or len(r_content) >= 12:
                        comment = appstore_review_comment(entry, track_id)
                        if comment:
                            reviews.append(comment)
                        if len(reviews) >= 3:
                            break
                added += save_appstore_feedback(conn, app, category, term, reviews)
        except Exception as exc:
            print(f"[WARN] AppStore采集异常 ({term}): {exc}")
    conn.commit()
    return added


def collect_bilibili_replies(conn, opener, aid, parent_url, *, limit=1, page_size=5):
    if not aid:
        return
    rep_url = f"https://api.bilibili.com/x/v2/reply?type=1&oid={aid}&sort=1&ps={page_size}"
    try:
        response = opener.open(rep_url, timeout=6).read().decode("utf-8", errors="ignore")
        replies = (json.loads(response).get("data") or {}).get("replies") or []
    except Exception as exc:
        print(f"[WARN] B站评论采集跳过 ({aid}): {exc}")
        return
    for reply in replies[:limit]:
        reply_id = str(reply.get("rpid_str") or reply.get("rpid") or "").strip()
        content = (reply.get("content") or {}).get("message") or ""
        if not reply_id or not content.strip():
            continue
        likes = reply.get("like")
        save_comment(conn, {
            "channel": "B站",
            "comment_id": reply_id,
            "parent_url": parent_url,
            "content": content,
            "author_or_app": (reply.get("member") or {}).get("uname", ""),
            "commented_at": epoch_time(reply.get("ctime")),
            "comment_time_source": "bilibili_reply_ctime",
            "source_metric": f"{likes} 赞" if type(likes) is int and likes >= 0 else "",
        })


def collect_bilibili(conn: sqlite3.Connection, custom_queries: Optional[List[Tuple[str, str]]] = None) -> int:
    """采集 B 站真实视频播放量、收藏率（高收藏比代表强工具/干货需求）及热门评论"""
    queries = custom_queries or [
        ("知识可视化与Vibe视频", "Claude Remotion 知识动画"),
        ("知识可视化与Vibe视频", "Manim 知识动画 教程 制作"),
        ("AI直播与整活工具", "AI 无人直播 虚拟主播 搭建 弹幕"),
        ("教培与督学工具", "考研 规划 督学 艾宾浩斯 模板"),
        ("闲鱼与虚拟变现闭环", "闲鱼 虚拟 自动发货 实操 工具"),
        ("垂直B端与效率工具", "DeepSeek 工作流 变现 实操"),
    ]
    added = 0
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=SSL_CTX),
        urllib.request.HTTPCookieProcessor(cj),
    )
    opener.addheaders = [
        ("User-Agent", USER_AGENT),
        ("Referer", "https://www.bilibili.com/"),
    ]
    try:
        opener.open("https://www.bilibili.com/", timeout=8).read()
    except Exception as exc:
        print(f"[WARN] B站预热Cookie失败: {exc}")

    for category, term in queries:
        try:
            url = "https://api.bilibili.com/x/web-interface/search/type?" + urllib.parse.urlencode(
                {"search_type": "video", "keyword": term}
            )
            raw = opener.open(url, timeout=10).read().decode("utf-8", errors="ignore")
            res = json.loads(raw)
            items = res.get("data", {}).get("result", []) or []
            candidates = ((item, epoch_time(item.get("pubdate"))) for item in items)
            for item, published in newest_results(candidates, 4):
                title = strip_html(item.get("title", ""))
                desc = strip_html(item.get("description", ""))
                play = int(item.get("play") or 0)
                fav = int(item.get("favorites") or 0)
                danmaku = int(item.get("video_review") or 0)
                author = item.get("author", "")
                pub_dt = source_day(published)
                if pub_dt and (market_today() - datetime.date.fromisoformat(pub_dt)).days > 180:
                    continue
                bvid = item.get("bvid", "")
                if not bvid:
                    continue
                aid = item.get("aid")
                fav_ratio = round((fav / play * 100), 1) if play > 0 else 0.0
                video_url = f"https://www.bilibili.com/video/{bvid}"
                ok = insert_signal(
                    conn=conn,
                    channel="B站视频与评论(实时API)",
                    source_tier="实时API抓取",
                    category=category,
                    query_term=term,
                    title=title,
                    content=f"视频简介: {desc[:160] if desc else '无'}",
                    author_or_app=f"UP主: {author}",
                    metric_primary=f"{play} 播放 / {fav} 收藏",
                    metric_secondary=f"收藏率 {fav_ratio}% / {danmaku} 弹幕",
                    rating_or_price="高收藏干货" if fav_ratio >= 5.0 else "常规视频",
                    source_url=video_url,
                    published_at=pub_dt,
                    source_published_at=published,
                    published_time_source="bilibili_video_pubdate",
                )
                if ok:
                    added += 1
                collect_bilibili_replies(conn, opener, aid, video_url)
        except Exception as exc:
            print(f"[WARN] B站采集异常 ({term}): {exc}")
    conn.commit()
    return added


def collect_wechat_sogou(conn: sqlite3.Connection, custom_queries: Optional[List[Tuple[str, str]]] = None) -> int:
    """通过搜狗微信搜索实时抓取微信公众号实战拆解与行业痛点文章"""
    queries = custom_queries or [
        ("闲鱼与虚拟变现闭环", "闲鱼 虚拟 痛点 自动发货 变现"),
        ("教培与督学工具", "教培机构 续费 招生 学情 工具 痛点"),
        ("知识可视化与Vibe视频", "知识可视化 动画 视频 变现 AI"),
        ("垂直B端与效率工具", "小红书 获客 工具 痛点 平替 变现"),
    ]
    added = 0
    for category, term in queries:
        try:
            url = "https://weixin.sogou.com/weixin?" + urllib.parse.urlencode({"type": "2", "query": term})
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
                page = resp.read().decode("utf-8", errors="ignore")
            blocks = re.findall(r'<div class="txt-box">(.*?)</div>\s*</div>', page, re.S)
            candidates = []
            for blk in blocks:
                ts_match = re.search(r"timeConvert\('(\d+)'\)", blk)
                candidates.append((blk, epoch_time(ts_match.group(1)) if ts_match else ""))
            for blk, published in newest_results(candidates, 3):
                t_match = re.search(r"<h3[^>]*>\s*<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>\s*</h3>", blk, re.S)
                p_match = re.search(r'<p class="txt-info"[^>]*>(.*?)</p>', blk, re.S)
                a_match = re.search(r'<span class="all-time-y2">(.*?)</span>', blk, re.S)
                pub_dt = source_day(published)
                if pub_dt and (market_today() - datetime.date.fromisoformat(pub_dt)).days > 180:
                    continue
                if not t_match:
                    continue
                href, raw_title = t_match.group(1), t_match.group(2)
                if href.startswith("/"):
                    href = "https://weixin.sogou.com" + href
                title = strip_html(raw_title)
                abstract = strip_html(p_match.group(1)) if p_match else ""
                wx_author = strip_html(a_match.group(1)) if a_match else "微信公众号"
                ok = insert_signal(
                    conn=conn,
                    channel="微信公众号检索(实时抓取)",
                    source_tier="实时API抓取",
                    category=category,
                    query_term=term,
                    title=title,
                    content=abstract,
                    author_or_app=wx_author,
                    metric_primary="公众号深度拆解",
                    metric_secondary=f"检索词: {term}",
                    rating_or_price="行业一线案例",
                    source_url=href,
                    published_at=pub_dt,
                    source_published_at=published,
                    published_time_source="sogou_article_time",
                )
                if ok:
                    added += 1
        except Exception as exc:
            print(f"[WARN] 微信公众号采集异常 ({term}): {exc}")
    conn.commit()
    return added


def ingest_inbox_csv(conn: sqlite3.Connection, inbox_dir: pathlib.Path = INBOX_DIR) -> int:
    """导入既有信号表和显式标记为 comment 的评论行。"""
    added = 0
    if not inbox_dir.exists():
        return 0
    for csv_file in sorted(inbox_dir.glob("*.csv")):
        try:
            with csv_file.open("r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if (row.get("record_type") or "").strip().lower() == "comment":
                        try:
                            row["comment_time_source"] = row.get("comment_time_source") or csv_file.name
                            added += save_comment(conn, row)
                        except ValueError as exc:
                            print(f"[WARN] 跳过评论 ({csv_file.name}:{reader.line_num}): {exc}")
                        continue
                    ok = insert_signal(
                        conn=conn,
                        channel=row.get("channel", "本地CSV导入"),
                        source_tier="本地导表导入",
                        category=row.get("category", "未分类"),
                        query_term=row.get("query_term", csv_file.stem),
                        title=row.get("title", ""),
                        content=row.get("content", ""),
                        author_or_app=row.get("author_or_app", ""),
                        metric_primary=row.get("metric_primary", ""),
                        metric_secondary=row.get("metric_secondary", ""),
                        rating_or_price=row.get("rating_or_price", ""),
                        source_url=row.get("source_url", ""),
                    )
                    if ok:
                        added += 1
        except Exception as exc:
            print(f"[WARN] 导入 CSV 失败 ({csv_file}): {exc}")
    conn.commit()
    return added


def clean_and_tag_signals(conn: sqlite3.Connection) -> Dict[str, int]:
    """硬规则清洗：剔除纯营销引流软文、过短无意义内容，并自动提取痛点标签"""
    cur = conn.cursor()
    rows = cur.execute("SELECT id, channel, title, content, metric_primary FROM raw_signals").fetchall()

    spam_patterns = [
        r"免费领",
        r"扣\s*111",
        r"加微",
        r"私信领",
        r"进群交流",
        r"纯福利分享",
    ]
    tag_rules = [
        ("付费意愿已验证", r"扣费|会员|月销|想要|投流|单价|付费|变现|高毛利|出单"),
        ("现有方案体验差/求平替", r"差评|垃圾|不好用|闪退|套路|太贵|平替|不能分享|模糊"),
        ("国内环境/使用门槛卡点", r"Claude|中转|封号|部署|不会配|环境|翻墙|吓哭"),
        ("Token/算力成本高", r"Token|算力|成本|烧不起|免费额度"),
        ("B端交付与续费痛点", r"教培|招生|续费|家长|周报|错题|定制"),
    ]

    total = len(rows)
    noise_cnt = 0
    valid_cnt = 0

    for row in rows:
        sid = row["id"]
        text = f"{row['title']} {row['content']}"
        is_noise = 0
        noise_reason = ""

        if len(text.strip()) < 15:
            is_noise = 1
            noise_reason = "内容过短(<15字)，缺乏具体痛点上下文"
        else:
            for pat in spam_patterns:
                if re.search(pat, text) and "差评" not in text and "想要" not in row["metric_primary"]:
                    is_noise = 1
                    noise_reason = f"命中纯引流软文特征词({pat})"
                    break

        matched_tags = []
        for tag_name, pat in tag_rules:
            if re.search(pat, text, re.I) or re.search(pat, row["metric_primary"], re.I):
                matched_tags.append(tag_name)
        if not matched_tags:
            matched_tags.append("基础赛道线索")

        if is_noise:
            noise_cnt += 1
        else:
            valid_cnt += 1

        cur.execute(
            "UPDATE raw_signals SET is_noise = ?, noise_reason = ?, pain_tags = ? WHERE id = ?",
            (is_noise, noise_reason, ",".join(matched_tags), sid),
        )
    conn.commit()
    from persona_and_freshness import enrich_all_signals
    enrich_all_signals(conn)
    return {"total": total, "valid": valid_cnt, "noise": noise_cnt}


def load_opportunities_seed() -> List[Dict[str, Any]]:
    json_path = pathlib.Path(__file__).parent / "opportunities_seed.json"
    if not json_path.exists():
        return []
    return json.loads(json_path.read_text(encoding="utf-8"))


def evaluate_opportunities(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    items = load_opportunities_seed()
    count = 0
    for it in items:
        total = (
            it["score_payment"]
            + it["score_acquisition"]
            + it["score_delivery"]
            + it["score_competition"]
            + it["score_validation"]
        )
        cur.execute(
            """
            INSERT OR REPLACE INTO opportunities (
                code, group_type, title, status_badge, one_liner, origin_context,
                target_buyer, current_workaround, product_form, pricing_model,
                score_payment, score_acquisition, score_delivery, score_competition,
                score_validation, total_score, bear_case_risks, pivot_advice,
                validation_48h_plan, match_categories, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                it["code"],
                it["group_type"],
                it["title"],
                it["status_badge"],
                it["one_liner"],
                it["origin_context"],
                it["target_buyer"],
                it["current_workaround"],
                it["product_form"],
                it["pricing_model"],
                it["score_payment"],
                it["score_acquisition"],
                it["score_delivery"],
                it["score_competition"],
                it["score_validation"],
                total,
                it["bear_case_risks"],
                it["pivot_advice"],
                it["validation_48h_plan"],
                it["match_categories"],
                now_str(),
            ),
        )
        count += 1
    conn.commit()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Market Radar CLI (多渠道采集 + AI锐评评估 + 团队人脉提报)")
    parser.add_argument("action", choices=["run-all", "collect", "import-csv", "clean", "evaluate", "export", "submit-idea"], default="run-all", nargs="?")
    parser.add_argument("--title", default="", help="人脉新方向标题")
    parser.add_argument("--proposer", default="团队成员", help="提报人姓名/人脉来源")
    parser.add_argument("--what", default="", help="一句话说明具体做什么产品")
    parser.add_argument("--buyer", default="", help="卖给谁、怎么收费")
    parser.add_argument("--evidence", default="", help="人脉或市场验证证据")
    parser.add_argument("--channel", default="人脉私域+小红书/闲鱼", help="首批客户获客渠道")
    parser.add_argument("--mvp-days", type=int, default=7, help="预计最小可用产品研发天数")
    parser.add_argument("--unpaid", action="store_true", help="若仅有口头意向尚无付费验证则加上此参数")
    parser.add_argument("--with-comments", action="store_true", help="本地导出信号、评论和标签到 .market-radar")
    args = parser.parse_args()
    if args.with_comments and args.action != "export":
        parser.error("--with-comments 仅适用于 export")

    conn = get_conn()
    init_db(conn)
    from collab_utils import sync_db_from_jsonl, dump_db_to_jsonl, submit_custom_idea
    from user_comments import archive_comments, restore_comments
    sync_db_from_jsonl(conn, BASE_WORKSPACE, insert_signal)
    restore_comments(conn, BASE_WORKSPACE)

    if args.action == "submit-idea":
        if not args.title or not args.what:
            print("[ERROR] 提报新方向需提供 --title 与 --what 参数")
            return
        out = submit_custom_idea(
            base_dir=BASE_WORKSPACE,
            title=args.title,
            proposer=args.proposer,
            what_to_do=args.what,
            buyer_and_price=args.buyer or "待定定价（建议99~299元测款）",
            evidence_desc=args.evidence or "团队内部人脉一线反馈",
            acquisition_channel=args.channel,
            mvp_days=args.mvp_days,
            has_paid_proof=not args.unpaid,
        )
        print(f"[SUBMIT-IDEA] 已完成立项评估并入库: {out}")
        from export_dashboard import export_all
        export_all(conn, BASE_WORKSPACE)
        print(f"[EXPORT] 看板已自动刷新: {HTML_PATH}")
        return

    if args.action == "import-csv":
        c_csv = ingest_inbox_csv(conn)
        archive_comments(conn, BASE_WORKSPACE)
        clean_and_tag_signals(conn)
        dump_db_to_jsonl(conn, BASE_WORKSPACE)
        print(f"[IMPORT-CSV] 新增信号与评论: {c_csv}")
        return

    if args.action in ("run-all", "collect"):
        c_csv = ingest_inbox_csv(conn)
        c_app = collect_appstore(conn)
        c_bili = collect_bilibili(conn)
        c_wx = collect_wechat_sogou(conn)
        if args.action == "collect":
            archive_comments(conn, BASE_WORKSPACE)
        print(f"[COLLECT] 本地导表={c_csv}, 新增主记录: AppStore应用={c_app}, B站视频={c_bili}, 微信公众号={c_wx}")

    if args.action in ("run-all", "clean"):
        stats = clean_and_tag_signals(conn)
        dump_db_to_jsonl(conn, BASE_WORKSPACE)
        archive_comments(conn, BASE_WORKSPACE)
        print(f"[CLEAN & ARCHIVE] 信号清洗与历史归档完成: 总计={stats['total']}, 有效={stats['valid']}, 拦截噪音={stats['noise']}")

    if args.action in ("run-all", "evaluate"):
        opp_cnt = evaluate_opportunities(conn)
        print(f"[EVALUATE] 已评估并更新立项卡: {opp_cnt} 个")

    if args.action in ("run-all", "export"):
        from export_dashboard import export_all
        page = export_all(conn, BASE_WORKSPACE, with_comments=args.with_comments)
        print(f"[EXPORT] 交互式看板已生成: {page}")
        if args.with_comments:
            print(f"[EXPORT] 本地 CSV: {page.parent / 'exports/signals_full.csv'}")


if __name__ == "__main__":
    main()
