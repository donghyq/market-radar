#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Discover consumer digital products and services in public sources."""

import json
import pathlib
import sqlite3
import ssl
import urllib.parse
import urllib.request

import radar_cli
from collectors.appinn_collector import collect_appinn
from collectors.consumer_sources import PRODUCT, collect_jd, collect_notion, collect_steam, consumer_queries
from collectors.v2ex_comments import CHANNEL as V2EX_CHANNEL, collect_replies
from collab_utils import dump_db_to_jsonl, sync_db_from_jsonl
from evidence.user_comments import archive_comments, restore_comments
from evidence_rules import default_rules
from signal_time import epoch_time, newest_results

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
SSL_CTX = ssl._create_unverified_context()
UA = radar_cli.USER_AGENT


def scan_broad_appstore(conn: sqlite3.Connection) -> int:
    broad_queries = [(f"{PRODUCT} / {category}", term) for category, term in consumer_queries()["appstore"]]
    return radar_cli.collect_appstore(conn, custom_queries=broad_queries)


def scan_broad_wechat_and_web(conn: sqlite3.Connection) -> int:
    """Search broad buyer language for leads to inspect on the original sites."""
    return radar_cli.collect_wechat_sogou(conn, custom_queries=consumer_queries()["wechat"])


def scan_v2ex_pain_points(conn: sqlite3.Connection, *, per_node=6) -> int:
    """扫描 V2EX 公开热门/创造者节点中的真实独立开发与工具痛点"""
    added = 0
    seen_replies = set()
    rules = default_rules()
    discovery = rules.v2ex_discovery
    for node in ["create", "programmer", "ideas"]:
        try:
            url = f"https://www.v2ex.com/api/topics/show.json?node_name={node}"
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=8, context=SSL_CTX) as resp:
                items = json.loads(resp.read().decode("utf-8", errors="ignore"))
            candidates = ((item, epoch_time(item.get("created"))) for item in items)
            for it, published in newest_results(candidates, per_node):
                title = radar_cli.strip_html(it.get("title", ""))
                content = radar_cli.strip_html(it.get("content", ""))
                replies = int(it.get("replies") or 0)
                t_url = it.get("url", "")
                member = (it.get("member") or {}).get("username", "V2EX用户")
                legacy_match = len(title) >= discovery["min_title_length"] and (replies >= discovery["min_replies"]
                    or any(word in title + content for word in discovery["keywords"]))
                if legacy_match or rules.evaluate({"channel": "V2EX", "title": title, "content": content})["counts_as_demand"]:
                    ok = radar_cli.insert_signal(
                        conn=conn,
                        channel=V2EX_CHANNEL,
                        source_tier="实时API抓取",
                        category="独立开发与新工具发现",
                        query_term=f"v2ex:{node}",
                        title=title,
                        content=content[:500] if content else title,
                        author_or_app=f"V2EX @{member}",
                        metric_primary=f"{replies} 条回复",
                        metric_secondary=f"节点: {node}",
                        rating_or_price="",
                        source_url=t_url,
                        source_published_at=published,
                        published_time_source="v2ex_topic_created",
                    )
                    if ok:
                        added += 1
                    topic_id = it.get("id")
                    if replies and topic_id and topic_id not in seen_replies:
                        seen_replies.add(topic_id)
                        collect_replies(conn, topic_id, t_url, user_agent=UA)
        except Exception as exc:
            print(f"[WARN] V2EX 采集跳过 ({node}): {exc}")
    conn.commit()
    return added


def collect_discovery(conn):
    config = consumer_queries()
    added = {
        "App Store": scan_broad_appstore(conn),
        "微信公众号检索": scan_broad_wechat_and_web(conn),
    }
    for label, results in (
        ("Steam", collect_steam(conn, config["steam"])),
        ("Notion 模板", collect_notion(conn, config["notion"])),
        ("京东服务", collect_jd(conn, config["jd"])),
    ):
        captured = list(results)
        added[label] = sum(signals for signals, _ in captured)
        print(f"[DISCOVERY] {label}: 新增信号={added[label]}，新增评价={sum(reviews for _, reviews in captured)}")
    added["小众软件论坛"], replies = collect_appinn(conn)
    print(f"[DISCOVERY] 小众软件论坛: 新增主帖={added['小众软件论坛']}，新增回帖={replies}")
    added["V2EX"] = scan_v2ex_pain_points(conn, per_node=1)
    return added


def main():
    conn = radar_cli.get_conn()
    radar_cli.init_db(conn)
    sync_db_from_jsonl(conn, BASE_DIR, radar_cli.insert_signal)
    restore_comments(conn, BASE_DIR)

    added = collect_discovery(conn)
    archive_comments(conn, BASE_DIR)
    stats = radar_cli.clean_and_tag_signals(conn)
    dump_db_to_jsonl(conn, BASE_DIR)
    print(f"[DISCOVERY] {added} | 当前库内总信号={stats['total']} (有效={stats['valid']})")


if __name__ == "__main__":
    main()
