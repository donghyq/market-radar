#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单点深潜与结构性拐点挖掘引擎 (Deep-Dive & Inflection Point Scanner)
不仅抓取表面标题，还针对具备『高 Fork 复刻率 × 硬件/算力成本骤降』特征的战略级项目（如 Microduck 具身宠物），
深入抓取：
1. GitHub 主仓及国产平替复刻仓的热度、Fork 率与真实 Issues 报错卡点；
2. B 站高收藏复刻教程视频及其评论区的前排真实痛点留言；
3. 微信公众号关于具身桌面宠物、AI 陪伴硬件与创客教具的商业拆解。
"""

import http.cookiejar
import json
import pathlib
import re
import sqlite3
import ssl
import urllib.parse
import urllib.request
from typing import List, Tuple

import radar_cli
from collab_utils import dump_db_to_jsonl, sync_db_from_jsonl
from signal_time import epoch_time
from user_comments import archive_comments, restore_comments

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
SSL_CTX = ssl._create_unverified_context()
UA = radar_cli.USER_AGENT


def deep_scan_github_inflection(conn: sqlite3.Connection) -> List[int]:
    """扫描 Microduck 及开源具身宠物生态仓库与真实 Issues 卡点"""
    added_ids: List[int] = []
    headers = {"User-Agent": UA, "Accept": "application/vnd.github.v3+json"}

    # 1. 搜索核心仓库与国产复刻仓
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
        {"q": "microduck OR Open_Duck_Mini", "sort": "stars", "per_page": 6}
    )
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        for it in data.get("items", []):
            fn = it.get("full_name", "")
            st = int(it.get("stargazers_count") or 0)
            fk = int(it.get("forks_count") or 0)
            fk_ratio = round(fk / st * 100, 1) if st > 0 else 0.0
            desc = radar_cli.strip_html(it.get("description") or "")
            h_url = it.get("html_url", f"https://github.com/{fn}")
            radar_cli.insert_signal(
                conn=conn,
                channel="GitHub结构性拐点(深潜API)",
                source_tier="实时API抓取",
                category="具身智能与AI宠物硬件",
                query_term="microduck",
                title=f"[开源复刻潮] {fn} — {desc[:90]}",
                content=f"仓库 {fn} 已获 {st} Stars 与 {fk} Forks（Fork复刻率高达 {fk_ratio}%，远超普通软件项目的5%，说明大量极客与团队正在动手组装实机）。项目简介：{desc}",
                author_or_app=fn,
                metric_primary=f"{st} Stars / {fk} Forks",
                metric_secondary=f"复刻率 {fk_ratio}%",
                rating_or_price="高壁垒硬件开源拐点",
                source_url=h_url,
            )
    except Exception as exc:
        print(f"[WARN] GitHub 仓库深潜异常: {exc}")

    # 2. 抓取真实 Issues 里的组装/RL环境/舵机校准报错卡点
    for repo in ["pollen-robotics/microduck", "fanhao375/microduck-replica", "pollen-robotics/microduck_rl"]:
        try:
            i_url = f"https://api.github.com/repos/{repo}/issues?state=all&per_page=5"
            req = urllib.request.Request(i_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
                issues = json.loads(resp.read().decode("utf-8", errors="ignore"))
            for iss in issues:
                if "pull_request" in iss:
                    continue
                i_title = radar_cli.strip_html(iss.get("title", ""))
                i_body = radar_cli.strip_html(iss.get("body") or "")[:350]
                cmts = int(iss.get("comments") or 0)
                u_login = (iss.get("user") or {}).get("login", "dev")
                radar_cli.insert_signal(
                    conn=conn,
                    channel="GitHub真实Issue卡点(深潜API)",
                    source_tier="实时API抓取",
                    category="具身智能与AI宠物硬件",
                    query_term=repo,
                    title=f"[复刻卡点 Issue] {i_title}",
                    content=f"开发者 @{u_login} 在 {repo} 反馈实机/训练卡点：{i_title}。详情摘要：{i_body if i_body else '无附加正文'}",
                    author_or_app=f"{repo} #{iss.get('number')}",
                    metric_primary=f"{cmts} 条讨论",
                    metric_secondary=f"状态: {iss.get('state')}",
                    rating_or_price="真实研发痛点",
                    source_url=iss.get("html_url", f"https://github.com/{repo}/issues"),
                )
        except Exception as exc:
            print(f"[WARN] GitHub Issue 抓取跳过 ({repo}): {exc}")

    conn.commit()
    return added_ids


def deep_scan_bilibili_microduck(conn: sqlite3.Connection) -> None:
    """深潜抓取 B 站 Microduck 与桌面具身机器人复刻教程及多条高赞痛点评论"""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=SSL_CTX),
        urllib.request.HTTPCookieProcessor(cj),
    )
    opener.addheaders = [("User-Agent", UA), ("Referer", "https://www.bilibili.com/")]
    try:
        opener.open("https://www.bilibili.com/", timeout=8).read()
    except Exception:
        pass

    for kw in ["microduck", "桌面机器人 AI 宠物 开源"]:
        try:
            url = "https://api.bilibili.com/x/web-interface/search/type?" + urllib.parse.urlencode(
                {"search_type": "video", "keyword": kw}
            )
            res = json.loads(opener.open(url, timeout=10).read().decode("utf-8", errors="ignore"))
            for item in (res.get("data", {}).get("result") or [])[:5]:
                title = radar_cli.strip_html(item.get("title", ""))
                desc = radar_cli.strip_html(item.get("description", ""))
                play = int(item.get("play") or 0)
                fav = int(item.get("favorites") or 0)
                author = item.get("author", "")
                bvid = item.get("bvid", "")
                if not bvid:
                    continue
                aid = item.get("aid")
                fav_ratio = round((fav / play * 100), 1) if play > 0 else 0.0
                video_url = f"https://www.bilibili.com/video/{bvid}"
                radar_cli.insert_signal(
                    conn=conn,
                    channel="B站视频与评论(实时API)",
                    source_tier="实时API抓取",
                    category="具身智能与AI宠物硬件",
                    query_term=kw,
                    title=title,
                    content=f"视频简介: {desc[:140]}",
                    author_or_app=f"UP主: {author}",
                    metric_primary=f"{play} 播放 / {fav} 收藏",
                    metric_secondary=f"收藏率 {fav_ratio}%",
                    rating_or_price="高热度硬件复刻" if play >= 10000 else "实机演示",
                    source_url=video_url,
                    source_published_at=epoch_time(item.get("pubdate")),
                    published_time_source="bilibili_video_pubdate",
                )
                radar_cli.collect_bilibili_replies(conn, opener, aid, video_url, limit=5, page_size=8)
        except Exception as exc:
            print(f"[WARN] B站深潜跳过 ({kw}): {exc}")
    conn.commit()


def main():
    conn = radar_cli.get_conn()
    radar_cli.init_db(conn)
    sync_db_from_jsonl(conn, BASE_DIR, radar_cli.insert_signal)
    restore_comments(conn, BASE_DIR)

    deep_scan_github_inflection(conn)
    deep_scan_bilibili_microduck(conn)
    radar_cli.collect_wechat_sogou(
        conn,
        custom_queries=[
            ("具身智能与AI宠物硬件", "AI桌面宠物 机器人 陪伴 创业 融资 爆款"),
            ("具身智能与AI宠物硬件", "具身智能 教具 实训 高校 采购 痛点"),
        ],
    )
    stats = radar_cli.clean_and_tag_signals(conn)
    archive_comments(conn, BASE_DIR)
    dump_db_to_jsonl(conn, BASE_DIR)
    print(f"[DEEP-DIVE] 深潜完成！当前库内总信号={stats['total']} (有效={stats['valid']})")


if __name__ == "__main__":
    main()
