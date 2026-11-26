#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主动广谱商机发现引擎 (Autonomous Pain-Point & Monetization Scanner)
解决『只会围绕用户已有想法打转、缺乏自主发掘新赛道能力』的核心问题：
1. 不预设具体产品方向，而是按『高付费意愿人群 × 交易/抱怨动词』构建广谱探针矩阵；
2. 跨 6 大完全独立于既有想法的商业赛道主动扫描：
   - 赛道 A：拼多多/抖音小店/跨境卖家高频工具痛点（批量主图/详情页/违禁词/客服催拍/打单）
   - 赛道 B：个体户/装修/餐饮/家政/房产中介获客与报价开单工具（报价表/效果图/朋友圈海报/收据）
   - 赛道 C：财务/法务/HR/招投标文书高频痛点（发票核对/标书检查/排班考勤/合同比对）
   - 赛道 D：自媒体与短剧/小说推文二创生产力工具（去重/混剪/字幕/配音/漫画分镜）
   - 赛道 E：家长/备考/留学/求职刚需付费服务（简历精修/面试模拟/字帖生成/背诵打卡）
   - 赛道 F：V2EX / 独立开发者社区与淘宝闲鱼高频求助信号
"""

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
from signal_time import epoch_time, newest_results
from user_comments import archive_comments, restore_comments

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
SSL_CTX = ssl._create_unverified_context()
UA = radar_cli.USER_AGENT


def scan_broad_appstore(conn: sqlite3.Connection) -> int:
    """广谱扫描中国区 App Store 6 大全新高付费赛道的 1~3 星真实差评"""
    broad_queries: List[Tuple[str, str]] = [
        ("电商卖家与主图工具", "电商 主图 抠图 批量"),
        ("个体户开单与报价工具", "报价单 开单 收据 记账"),
        ("招投标与合同办公工具", "合同 扫描 发票 识别"),
        ("短剧与视频二创工具", "视频去重 混剪 提取文案"),
        ("求职简历与面试工具", "简历 制作 面试 题库"),
        ("生活刚需与垂直小工具", "证件照 电子章 排版 打印"),
    ]
    return radar_cli.collect_appstore(conn, custom_queries=broad_queries)


def scan_broad_bilibili(conn: sqlite3.Connection) -> int:
    """广谱扫描 B 站全新赛道的高收藏率教程/工具求购视频与热评"""
    broad_queries: List[Tuple[str, str]] = [
        ("电商卖家与主图工具", "拼多多 抖音小店 自动 批量 工具 痛点"),
        ("招投标与合同办公工具", "标书 自动 检查 废标 AI 工具"),
        ("个体户开单与报价工具", "装修 门窗 定制 报价单 自动生成"),
        ("短剧与视频二创工具", "小说推文 漫画解说 批量 生成 工具"),
        ("闲鱼与虚拟变现闭环", "淘宝 闲鱼 虚拟 蓝海 冷门 暴利 项目"),
    ]
    return radar_cli.collect_bilibili(conn, custom_queries=broad_queries)


def scan_broad_wechat_and_web(conn: sqlite3.Connection) -> int:
    """广谱扫描搜狗微信与公开网页的蝉妈妈/闲鱼/小红书真实交易痛点"""
    broad_queries: List[Tuple[str, str]] = [
        ("电商卖家与主图工具", "蝉妈妈 低粉 爆单 工具 小程序 拆解"),
        ("闲鱼与虚拟变现闭环", "闲鱼 月销 虚拟 代做 痛点 需求 2026"),
        ("小红书高赞求购信号", "小红书 评论区 求链接 平替 刚需 工具"),
        ("招投标与合同办公工具", "企业 标书 废标 检查 痛点 收费 工具"),
        ("个体户开单与报价工具", "个体户 装修 报价 小程序 付费 痛点"),
    ]
    return radar_cli.collect_wechat_sogou(conn, custom_queries=broad_queries)


def scan_v2ex_pain_points(conn: sqlite3.Connection) -> int:
    """扫描 V2EX 公开热门/创造者节点中的真实独立开发与工具痛点"""
    added = 0
    for node in ["create", "programmer", "ideas"]:
        try:
            url = f"https://www.v2ex.com/api/topics/show.json?node_name={node}"
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=8, context=SSL_CTX) as resp:
                items = json.loads(resp.read().decode("utf-8", errors="ignore"))
            candidates = ((item, epoch_time(item.get("created"))) for item in items)
            for it, published in newest_results(candidates, 6):
                title = radar_cli.strip_html(it.get("title", ""))
                content = radar_cli.strip_html(it.get("content", ""))
                replies = int(it.get("replies") or 0)
                t_url = it.get("url", "")
                member = (it.get("member") or {}).get("username", "V2EX用户")
                if len(title) >= 6 and (replies >= 5 or any(k in title + content for k in ["痛点", "工具", "付费", "开源", "小程序", "插件", "需求", "变现"])):
                    ok = radar_cli.insert_signal(
                        conn=conn,
                        channel="V2EX开发者与需求社区(实时API)",
                        source_tier="实时API抓取",
                        category="独立开发与新工具发现",
                        query_term=f"v2ex:{node}",
                        title=title,
                        content=content[:500] if content else title,
                        author_or_app=f"V2EX @{member}",
                        metric_primary=f"{replies} 条真实回复",
                        metric_secondary=f"节点: {node}",
                        rating_or_price="真实社区痛点",
                        source_url=t_url,
                        source_published_at=published,
                        published_time_source="v2ex_topic_created",
                    )
                    if ok:
                        added += 1
        except Exception as exc:
            print(f"[WARN] V2EX 采集跳过 ({node}): {exc}")
    conn.commit()
    return added


def main():
    conn = radar_cli.get_conn()
    radar_cli.init_db(conn)
    sync_db_from_jsonl(conn, BASE_DIR, radar_cli.insert_signal)
    restore_comments(conn, BASE_DIR)

    a1 = scan_broad_appstore(conn)
    a2 = scan_broad_bilibili(conn)
    a3 = scan_broad_wechat_and_web(conn)
    a4 = scan_v2ex_pain_points(conn)
    archive_comments(conn, BASE_DIR)
    stats = radar_cli.clean_and_tag_signals(conn)
    dump_db_to_jsonl(conn, BASE_DIR)
    print(f"[DISCOVERY] 广谱主动扫描完成！新增 AppStore={a1}, B站={a2}, 微信/网页={a3}, V2EX={a4} | 当前库内总信号={stats['total']} (有效={stats['valid']})")


if __name__ == "__main__":
    main()
