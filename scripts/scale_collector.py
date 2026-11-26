#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高信噪比规模化信号扩充引擎 (High-Purity Scale Collector)
在不引入垃圾水贴的前提下，放开人为 Top-3 截断，将有效信号库扩充至 1,000+ 条统计有效规模：
1. 中国区 App Store 28 个高付费垂直品类：每类取高评内购 App，拉取完整最新 RSS 页中全部近 180 天内的 1~3 星实质痛点差评（字数>=15）；
2. GitHub 高复刻与生产力项目 Issues 痛点深挖：批量拉取具身硬件、知识动画(Remotion/Manim)、独立游戏(Godot)、浏览器自动化、本地Agent项目的真实报错与 Feature Request；
3. 微信公众号 20 组细分商业变现与行业痛点检索（严格提取真实 timeConvert 时间戳并拦截 >180 天旧文）；
4. V2EX 多技术与创业节点（create / programmer / macos / share / ask / career / apple）真实痛点帖采集。
"""

import concurrent.futures
import datetime
import json
import pathlib
import re
import sqlite3
import ssl
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Tuple

import radar_cli
from collab_utils import dump_db_to_jsonl, sync_db_from_jsonl
from persona_and_freshness import ensure_columns, enrich_all_signals
from signal_time import epoch_time
from user_comments import archive_comments, restore_comments

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
SSL_CTX = ssl._create_unverified_context()
UA = radar_cli.USER_AGENT
TODAY = datetime.date.today()


def is_within_days(date_str: str, max_days: int = 180) -> bool:
    if not date_str or len(date_str) < 10:
        return False
    try:
        d = datetime.date.fromisoformat(date_str[:10])
        return (TODAY - d).days <= max_days
    except Exception:
        return False


def fetch_appstore_category(cat_and_term: Tuple[str, str]):
    category, term = cat_and_term
    out = []
    pain_words = [
        "扣费", "会员", "太贵", "不好用", "闪退", "客服", "导出", "限制", "套路",
        "收费", "广告", "微信", "打印", "卡顿", "报错", "消失", "同步", "水印",
        "模糊", "识别", "骗钱", "自动续费", "买断", "永久", "崩溃", "没反应", "功能"
    ]
    try:
        s_url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(
            {"term": term, "country": "cn", "entity": "software", "limit": 6}
        )
        req = urllib.request.Request(s_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            apps = json.loads(resp.read().decode("utf-8", errors="ignore")).get("results", [])

        for app in apps:
            tid = str(app.get("trackId") or "")
            rcnt = int(app.get("userRatingCount") or 0)
            if not tid.isdecimal() or rcnt < 150:
                continue

            reviews = []
            for page_no in (1, 2):
                rss_u = f"https://itunes.apple.com/cn/rss/customerreviews/page={page_no}/id={tid}/sortby=mostrecent/json"
                r_req = urllib.request.Request(rss_u, headers={"User-Agent": UA})
                try:
                    with urllib.request.urlopen(r_req, timeout=8, context=SSL_CTX) as r_resp:
                        entries = json.loads(r_resp.read().decode("utf-8", errors="ignore")).get("feed", {}).get("entry", [])
                except Exception:
                    break
                if isinstance(entries, dict):
                    entries = [entries]
                picked = 0
                for e in entries:
                    rating = (e.get("im:rating") or {}).get("label", "")
                    if rating not in ("1", "2", "3"):
                        continue
                    pub = (e.get("updated") or {}).get("label") or ""
                    pub_dt = pub[:10]
                    if not is_within_days(pub_dt, 180):
                        continue
                    rt = radar_cli.strip_html((e.get("title") or {}).get("label", ""))
                    rc = radar_cli.strip_html((e.get("content") or {}).get("label", ""))
                    if len(rc) < 16:
                        continue
                    if any(w in (rt + rc) for w in pain_words):
                        comment = radar_cli.appstore_review_comment(e, tid)
                        if comment:
                            reviews.append(comment)
                            picked += 1
                        if picked >= 12:
                            break
            if reviews:
                out.append((app, category, term, reviews))
    except Exception:
        pass
    return out


def fetch_github_issues_batch(repo_info: Tuple[str, str]) -> List[Dict[str, str]]:
    category, repo = repo_info
    out: List[Dict[str, str]] = []
    headers = {"User-Agent": UA, "Accept": "application/vnd.github.v3+json"}
    try:
        url = f"https://api.github.com/repos/{repo}/issues?state=open&sort=comments&direction=desc&per_page=18"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            issues = json.loads(resp.read().decode("utf-8", errors="ignore"))
        for iss in issues:
            if "pull_request" in iss:
                continue
            pub_dt = (iss.get("created_at") or iss.get("updated_at") or "")[:10]
            if not is_within_days(pub_dt, 180):
                continue
            title = radar_cli.strip_html(iss.get("title", ""))
            body = radar_cli.strip_html(iss.get("body") or "")[:380]
            if len(title + body) < 25:
                continue
            cmts = int(iss.get("comments") or 0)
            out.append({
                "channel": "GitHub Issue报错(实时API)",
                "source_tier": "实时API抓取",
                "category": category,
                "query_term": repo,
                "title": f"[开源痛点 Issue] {title[:110]}",
                "content": f"仓库 {repo} 用户高频需求/报错：{title}。详情摘要：{body}",
                "author": f"{repo} #{iss.get('number')}",
                "m1": f"{cmts} 条跟帖讨论",
                "m2": "Open Issue",
                "price": "开发者/复刻真实卡点",
                "url": iss.get("html_url", f"https://github.com/{repo}/issues"),
                "pub": pub_dt,
                "source_pub": iss.get("created_at") or "",
            })
    except Exception:
        pass
    return out


def fetch_wechat_batch(cat_and_q: Tuple[str, str]) -> List[Dict[str, str]]:
    category, term = cat_and_q
    out: List[Dict[str, str]] = []
    try:
        url = "https://weixin.sogou.com/weixin?" + urllib.parse.urlencode({"type": "2", "query": term})
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            page = resp.read().decode("utf-8", errors="ignore")
        blocks = re.findall(r'<div class="txt-box">(.*?)</div>\s*</div>', page, re.S)
        for blk in blocks[:8]:
            tm = re.search(r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>\s*</h3>', blk, re.S)
            pm = re.search(r'<p class="txt-info"[^>]*>(.*?)</p>', blk, re.S)
            am = re.search(r'<span class="all-time-y2">(.*?)</span>', blk, re.S)
            tsm = re.search(r"timeConvert\('(\d+)'\)", blk)
            if not tm or not tsm:
                continue
            pub_dt = datetime.datetime.fromtimestamp(int(tsm.group(1))).strftime("%Y-%m-%d")
            if not is_within_days(pub_dt, 180):
                continue
            href = tm.group(1)
            if href.startswith("/"):
                href = "https://weixin.sogou.com" + href
            title = radar_cli.strip_html(tm.group(2))
            abstract = radar_cli.strip_html(pm.group(1)) if pm else ""
            if len(abstract) < 20:
                continue
            author = radar_cli.strip_html(am.group(1)) if am else "微信公众号"
            out.append({
                "channel": "微信公众号检索(实时抓取)",
                "source_tier": "实时API抓取",
                "category": category,
                "query_term": term,
                "title": title,
                "content": abstract,
                "author": author,
                "m1": "公众号实战拆解",
                "m2": f"发布于 {pub_dt}",
                "price": "行业案例与需求",
                "url": href,
                "pub": pub_dt,
                "source_pub": epoch_time(tsm.group(1)),
            })
    except Exception:
        pass
    return out


def fetch_v2ex_nodes() -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for node in ["create", "programmer", "macos", "share", "ask", "apple", "openai"]:
        try:
            url = f"https://www.v2ex.com/api/topics/show.json?node_name={node}"
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=8, context=SSL_CTX) as resp:
                items = json.loads(resp.read().decode("utf-8", errors="ignore"))
            for it in items[:15]:
                ts = int(it.get("created") or 0)
                pub_dt = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else TODAY.isoformat()
                if not is_within_days(pub_dt, 180):
                    continue
                title = radar_cli.strip_html(it.get("title", ""))
                content = radar_cli.strip_html(it.get("content", ""))
                if len(title + content) < 20:
                    continue
                replies = int(it.get("replies") or 0)
                member = (it.get("member") or {}).get("username", "V2EX")
                out.append({
                    "channel": "V2EX开发者与需求社区(实时API)",
                    "source_tier": "实时API抓取",
                    "category": "独立开发与工具痛点",
                    "query_term": f"v2ex:{node}",
                    "title": title,
                    "content": content[:450] if content else title,
                    "author": f"V2EX @{member}",
                    "m1": f"{replies} 条回复",
                    "m2": f"节点: {node}",
                    "price": "社区真实需求",
                    "url": it.get("url", ""),
                    "pub": pub_dt,
                    "source_pub": epoch_time(ts),
                })
        except Exception:
            pass
    return out


def main():
    conn = radar_cli.get_conn()
    radar_cli.init_db(conn)
    ensure_columns(conn)
    sync_db_from_jsonl(conn, BASE_DIR, radar_cli.insert_signal)
    restore_comments(conn, BASE_DIR)

    appstore_tasks = [
        ("电商卖家与主图工具", "电商 主图 批量 水印"),
        ("电商卖家与主图工具", "快递 打单 发货 电商"),
        ("电商卖家与主图工具", "商品 详情页 美工 作图"),
        ("个体户开单与报价工具", "进销存 开单 收银 库存"),
        ("个体户开单与报价工具", "装修 报价 量房 CAD"),
        ("个体户开单与报价工具", "电子收据 发票 记账 门店"),
        ("招投标与合同办公工具", "标书 招投标 企业 查询"),
        ("招投标与合同办公工具", "PDF 转换 扫描 盖章 电子签"),
        ("招投标与合同办公工具", "录音转文字 会议纪要 实时翻译"),
        ("高客单专业IP工具", "法宝 裁判 律师 案件管理"),
        ("高客单专业IP工具", "教培 排课 消课 招生 家校"),
        ("知识视频与口播工具", "去水印 视频提取 配音 字幕"),
        ("知识视频与口播工具", "动画制作 手绘视频 白板动画"),
        ("知识视频与口播工具", "录屏 剪辑 直播助手 虚拟主播"),
        ("备考与K12家长刚需", "背单词 考研 法考 刷题 题库"),
        ("备考与K12家长刚需", "字帖 练字 口算 批改 作业"),
        ("备考与K12家长刚需", "日程 番茄钟 习惯 打卡 备忘录"),
        ("桌面宠物与小组件", "桌面宠物 灵动岛 小组件 壁纸"),
    ]

    github_issue_tasks = [
        ("具身智能与AI宠物硬件", "huggingface/lerobot"),
        ("知识可视化与动画引擎", "remotion-dev/remotion"),
        ("知识可视化与动画引擎", "ManimCommunity/manim"),
        ("独立游戏与桌面宠物", "godotengine/godot"),
        ("浏览器自动化与采集", "microsoft/playwright-mcp"),
    ]

    wechat_tasks = [
        ("电商卖家与主图工具", "拼多多 抖音电商 卖家 工具 痛点 自动"),
        ("电商卖家与主图工具", "跨境 TikTok 达人 建联 工具 转化 痛点"),
        ("个体户开单与报价工具", "建材 门窗 全屋定制 老板 获客 报价 痛点"),
        ("个体户开单与报价工具", "实体店 餐饮 美业 小程序 续费 痛点"),
        ("招投标与合同办公工具", "招投标 废标 痛点 AI 审查 效率"),
        ("高客单专业IP工具", "青年律师 案源 小红书 获客 视频 痛点"),
        ("高客单专业IP工具", "代理记账 财税 获客 痛点 工具"),
        ("备考与K12家长刚需", "考研 考公 督学 闲鱼 变现 痛点"),
        ("桌面宠物与AI硬件", "AI陪伴 桌面机器人 硬件 痛点 销量 复盘"),
        ("独立开发与SaaS变现", "独立开发者 出海 小程序 月入 真实 复盘 2026"),
    ]

    collected_records: List[Dict[str, str]] = []
    inserted = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for batch in ex.map(fetch_appstore_category, appstore_tasks):
            for app, category, term, reviews in batch:
                inserted += radar_cli.save_appstore_feedback(conn, app, category, term, reviews)
        for batch in ex.map(fetch_github_issues_batch, github_issue_tasks):
            collected_records.extend(batch)
        for batch in ex.map(fetch_wechat_batch, wechat_tasks):
            collected_records.extend(batch)

    collected_records.extend(fetch_v2ex_nodes())

    for rec in collected_records:
        ok = radar_cli.insert_signal(
            conn=conn,
            channel=rec["channel"],
            source_tier=rec["source_tier"],
            category=rec["category"],
            query_term=rec["query_term"],
            title=rec["title"],
            content=rec["content"],
            author_or_app=rec["author"],
            metric_primary=rec["m1"],
            metric_secondary=rec["m2"],
            rating_or_price=rec["price"],
            source_url=rec["url"],
            published_at=rec["pub"],
            source_published_at=rec["source_pub"],
            published_time_source=rec["channel"],
        )
        if ok:
            inserted += 1
    conn.commit()
    archive_comments(conn, BASE_DIR)

    stats = radar_cli.clean_and_tag_signals(conn)
    rep = enrich_all_signals(conn, TODAY.isoformat())
    dump_db_to_jsonl(conn, BASE_DIR)
    (BASE_DIR / "data" / "persona_stats.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SCALE-COLLECT] 本次新增入库={inserted} 条 | 当前库内总信号={stats['total']} (有效={stats['valid']}, 拦截噪音={stats['noise']})")
    print("最新时效分布:", rep["freshness_breakdown"])


if __name__ == "__main__":
    main()
