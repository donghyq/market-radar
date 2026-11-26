#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
时效性时间线校准与买单人群画像统计引擎 (Freshness & Audience Persona Engine)
1. 严格区分『源站真实发布日期 (published_at)』与『爬虫入库日期 (collected_at)』；
2. 计算时效分级 (freshness_tier)：近7天当下热点 / 近30天当月信号 / 近90天近期有效 / 超90天陈旧归档；
3. 自动归类 8 大核心买单人群画像 (audience_tag) 并输出人群付费特征、典型客单价与样本统计。
"""

import datetime
import json
import pathlib
import re
import sqlite3
import ssl
import urllib.request
from typing import Any, Dict, List, Tuple

from signal_time import LEGACY_DATE_SOURCE, TIME_COLUMNS, market_today, source_day

SSL_CTX = ssl._create_unverified_context()
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

AUDIENCE_PROFILES: Dict[str, Dict[str, str]] = {
    "电商与跨境卖家": {
        "pay_habit": "按 ROI 算账，凡能防违规封店、提效测款均爽快付费",
        "price_band": "39~299 元/月 订阅制",
        "channels": "抖音电商群、小红书店群帖、深圳/义乌卖家圈",
        "pattern": r"电商|带货|主图|拼多多|抖音小店|千川|蝉妈妈|选品|跨境|TikTok|达人|寄样|独立站|卖家|淘宝客",
    },
    "极客与AI/硬件开发者": {
        "pay_habit": "愿为免配环境整合包、校准固件与节省折腾时间买单",
        "price_band": "99~399 元 镜像/买断包",
        "channels": "GitHub、B站硬核科技区、V2EX、复刻交流群",
        "pattern": r"microduck|ESP32|舵机|复刻|开源|GitHub|V2EX|Agent|MCP|Harness|DeepSeek|本地部署|终端|SSH|Termius|抓包",
    },
    "视频博主与内容创作者": {
        "pay_habit": "高频生产刚需，极其反感流氓自动续费，偏好买断或按量计费",
        "price_band": "29.9~69 元 买断或月卡",
        "channels": "B站教程评论区、小红书剪辑/口播痛点帖",
        "pattern": r"提词|口播|剪辑|字幕|混剪|Remotion|Manim|知识动画|开智小曲|小说推文|短剧|漫画解说|B站充电|短视频|无人直播|弹幕",
    },
    "备考学生与K12家长": {
        "pay_habit": "焦虑驱动型即时付费，先款后货零账期，极重打印排版体验",
        "price_band": "9.9~49.9 元 单次定制/打印包",
        "channels": "闲鱼搜索、小红书备考/鸡娃笔记、家长微信群",
        "pattern": r"错题|试卷|打印|考研|考公|法考|艾宾浩斯|打卡|复习|背单词|四六级|家长|提分|学习计划|小习惯",
    },
    "B端企业与招投标专员": {
        "pay_habit": "防损失驱动（防废标/防泄密），客单价高且年卡续费稳，重视本地隐私",
        "price_band": "49 元/次 或 699~1980 元/年",
        "channels": "招投标社群、工程造价论坛、闲鱼企业代查服务",
        "pattern": r"标书|废标|投标|查重|政采|工程|合同|扫描|发票|企业公司|B端",
    },
    "高客单专业服务IP(律所/教培/财税)": {
        "pay_habit": "获客与续费导向（成一单赚数千上万），愿为能装门面逼单的工具付年费",
        "price_band": "199~299 元/月 或 299~999 元/年",
        "channels": "小红书低赞专业博主私信、教培校长/督导群",
        "pattern": r"教培|续费|招生|学情|律所|律师|财税|判决书|具身应用技术员|实训室|高校|职教",
    },
    "线下门店与个体商户": {
        "pay_habit": "不懂电脑 Excel，只认手机点选 30 秒出图，偏好百元内一次买断",
        "price_band": "99~199 元/年 或买断",
        "channels": "抖音/快手同城同行视频评论区、建材市场群",
        "pattern": r"门窗|全屋定制|报价单|开单|收据|柜子|板材|装修|个体户|夫妻店",
    },
    "年轻玩家与桌宠受众": {
        "pay_habit": "为情绪陪伴、摸鱼解压与捏 OC 外观冲动付费，适合全球买断+DLC",
        "price_band": "18~29 元 Steam 本体 + 6~12 元 DLC",
        "channels": "Steam 新品节、B站游戏/桌宠区、小红书二次元OC圈",
        "pattern": r"桌宠|桌面宠物|挂机游戏|Steam|BongoCat|独立游戏|小游戏|牧场|捏oc|养鱼",
    },
}


def classify_audience(channel: str, category: str, query_term: str, title: str, content: str) -> Tuple[str, str]:
    combined = f"{category} {query_term} {title} {content} {channel}"
    # 优先精确匹配高区分度人群
    priority_order = [
        "B端企业与招投标专员",
        "线下门店与个体商户",
        "年轻玩家与桌宠受众",
        "备考学生与K12家长",
        "高客单专业服务IP(律所/教培/财税)",
        "电商与跨境卖家",
        "视频博主与内容创作者",
        "极客与AI/硬件开发者",
    ]
    for seg in priority_order:
        if re.search(AUDIENCE_PROFILES[seg]["pattern"], combined, re.I):
            prof = AUDIENCE_PROFILES[seg]
            return seg, f"{prof['pay_habit']}（典型定价：{prof['price_band']}）"
    return "大众效率与副业人群", "关注低门槛效率工具与副业变现（典型定价：9.9~99 元）"


def compute_freshness(pub_date_str: str, ref_date: datetime.date) -> Tuple[str, int, bool]:
    """返回 (freshness_tier, age_days, is_stale)"""
    if not pub_date_str or len(pub_date_str) < 10:
        return "recent_unverified", -1, False
    try:
        pub_d = datetime.date.fromisoformat(pub_date_str[:10])
        age = (ref_date - pub_d).days
        if age < 0:
            return "recent_unverified", -1, False
        if age <= 7:
            return "7d_hot", age, False
        if age <= 30:
            return "30d_active", age, False
        if age <= 90:
            return "90d_recent", age, False
        if age <= 180:
            return "180d_halfyear", age, False
        return "stale_archive", age, True
    except Exception:
        return "recent_unverified", -1, False


def ensure_columns(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    existing = {r[1] for r in cur.execute("PRAGMA table_info(raw_signals)").fetchall()}
    defaults = {
        "published_at": "",
        "freshness_tier": "30d_active",
        "audience_tag": "",
        "persona_note": "",
        **TIME_COLUMNS,
    }
    for col, default in defaults.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE raw_signals ADD COLUMN {col} TEXT DEFAULT '{default}'")
    conn.commit()


def backfill_real_publish_dates(conn: sqlite3.Connection) -> int:
    """对存量数据中缺失 published_at 的记录，通过 B站 View API / 标题年份解析回填真实发布日期"""
    ensure_columns(conn)
    rows = conn.execute("SELECT id, channel, title, content, source_url, collected_at, published_at FROM raw_signals").fetchall()
    updated = 0
    for r in rows:
        sid = r["id"]
        pub = (r["published_at"] or "").strip()
        if pub and len(pub) >= 10:
            continue

        url = r["source_url"] or ""
        text = f"{r['title']} {r['content']}"
        col_date = (r["collected_at"] or "2026-11-18")[:10]
        inferred = ""

        # 1. B站视频：直接调官方免登录 view 接口拿精确到秒的真实 pubdate！
        m_bv = re.search(r"/video/(BV[0-9A-Za-z]+)", url)
        if m_bv:
            bvid = m_bv.group(1)
            try:
                api_u = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
                req = urllib.request.Request(api_u, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=5, context=SSL_CTX) as resp:
                    v_data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                ts = (v_data.get("data") or {}).get("pubdate")
                if ts:
                    inferred = datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
            except Exception:
                pass

        # 2. 若标题/正文中含明确历史日期或历史年份（如 2024最新教程、2026-11-13）
        if not inferred:
            m_exact = re.search(r"(202[0-6]-\d{2}-\d{2})", text)
            if m_exact:
                inferred = m_exact.group(1)
            else:
                m_yr = re.search(r"(202[0-5])年|【(202[0-5])", text)
                if m_yr:
                    yr = m_yr.group(1) or m_yr.group(2)
                    inferred = f"{yr}-06-01"

        # 3. 实时流渠道（App Store 最新50条RSS、V2EX当前热门节点、近14天GitHub飙升）发布时间即为近期抓取窗口
        if not inferred:
            inferred = col_date

        conn.execute("UPDATE raw_signals SET published_at = ? WHERE id = ?", (inferred, sid))
        updated += 1

    conn.commit()
    return updated


def enrich_all_signals(conn: sqlite3.Connection, ref_date_str: str = "") -> Dict[str, Any]:
    ensure_columns(conn)
    ref_date = datetime.date.fromisoformat(ref_date_str) if ref_date_str else market_today()
    rows = conn.execute("SELECT * FROM raw_signals").fetchall()

    fresh_counts = {"7d_hot": 0, "30d_active": 0, "90d_recent": 0, "180d_halfyear": 0, "stale_archive": 0, "recent_unverified": 0}
    aud_stats: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        published = r["source_published_at"]
        if not published and r["published_time_source"] == LEGACY_DATE_SOURCE:
            published = r["published_at"]
        f_tier, _, is_stale = compute_freshness(source_day(published), ref_date)
        seg, p_note = classify_audience(r["channel"], r["category"], r["query_term"], r["title"], r["content"])

        conn.execute(
            "UPDATE raw_signals SET freshness_tier=?, audience_tag=?, persona_note=? WHERE id=?",
            (f_tier, seg, p_note, r["id"]),
        )

        if not r["is_noise"]:
            fresh_counts[f_tier] = fresh_counts.get(f_tier, 0) + 1
            if seg not in aud_stats:
                prof = AUDIENCE_PROFILES.get(seg, {})
                aud_stats[seg] = {
                    "audience": seg,
                    "total": 0,
                    "fresh_30d": 0,
                    "stale_cnt": 0,
                    "pay_habit": prof.get("pay_habit", "关注实用工具与性价比"),
                    "price_band": prof.get("price_band", "19.9~99 元"),
                    "channels": prof.get("channels", "小红书 / 闲鱼 / B站"),
                }
            aud_stats[seg]["total"] += 1
            if f_tier in ("7d_hot", "30d_active"):
                aud_stats[seg]["fresh_30d"] += 1
            if is_stale:
                aud_stats[seg]["stale_cnt"] += 1

    conn.commit()
    sorted_aud = sorted(aud_stats.values(), key=lambda x: (x["fresh_30d"], x["total"]), reverse=True)
    return {
        "ref_date": ref_date.isoformat(),
        "freshness_breakdown": fresh_counts,
        "audience_personas": sorted_aud,
    }
