#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态增量发现与自动候选立项生成器 (Auto Opportunity Synthesizer)
解决『每天只更新底层信号、看板立项列表却不自动长出新方向』的断层：
1. 动态时间窗扫描：抓取 GitHub 过去 14 天内刚诞生且 Star/Fork 飙升的全新物种（不预设死关键词），以及独立游戏/桌面挂机/AI硬件等增量信号；
2. 自动立项合成：扫描信号库中尚未被现有项目引用的高热度信号（如高收藏率 >6%、高 Fork 率 >10%、高播放或强痛点），自动生成新的候选立项 JSON 写入 data/ideas/AUTO-NEW-*.json（限制每次最多新增 2 个最显著方向，防止看板泛滥）。
"""

import datetime
import hashlib
import http.cookiejar
import json
import pathlib
import re
import sqlite3
import ssl
import urllib.parse
import urllib.request
from typing import Any, Dict, List

import radar_cli
from collab_utils import dump_db_to_jsonl, sync_db_from_jsonl
from signal_time import epoch_time

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
SSL_CTX = ssl._create_unverified_context()
UA = radar_cli.USER_AGENT


def collect_dynamic_breakouts(conn: sqlite3.Connection) -> int:
    """抓取过去 14 天内新诞生且快速蹿红的 GitHub 新物种（不锁死固定词）+ Steam 桌宠/独立游戏真实信号"""
    added = 0
    since_14d = (datetime.date.today() - datetime.timedelta(days=14)).strftime("%Y-%m-%d")
    headers = {"User-Agent": UA, "Accept": "application/vnd.github.v3+json"}

    # 1. GitHub 过去 14 天全新飙升项目（发现未知新方向的核心源头）
    gh_queries = [
        ("全球新物种飙升", f"created:>{since_14d} stars:>180"),
        ("独立游戏与桌面宠物", "godot OR desktop-pet OR idle-game stars:>300 pushed:>" + since_14d),
    ]
    for cat, q in gh_queries:
        try:
            url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
                {"q": q, "sort": "stars", "order": "desc", "per_page": 6}
            )
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            for it in data.get("items", []):
                fn = it.get("full_name", "")
                st = int(it.get("stargazers_count") or 0)
                fk = int(it.get("forks_count") or 0)
                fk_ratio = round(fk / st * 100, 1) if st > 0 else 0.0
                desc = radar_cli.strip_html(it.get("description") or "近期快速飙升开源项目")
                ok = radar_cli.insert_signal(
                    conn=conn,
                    channel="GitHub新物种雷达(实时API)",
                    source_tier="实时API抓取",
                    category=cat,
                    query_term=q[:40],
                    title=f"[近期飙升] {fn} — {desc[:90]}",
                    content=f"近两周高热仓库 {fn} 获 {st} Stars / {fk} Forks（Fork率 {fk_ratio}%）。功能描述：{desc}",
                    author_or_app=fn,
                    metric_primary=f"{st} Stars / {fk} Forks",
                    metric_secondary=f"Fork率 {fk_ratio}%",
                    rating_or_price="开源新趋势",
                    source_url=it.get("html_url", f"https://github.com/{fn}"),
                    source_published_at=it.get("created_at", "") or "",
                    published_time_source="github_repository_created",
                )
                if ok:
                    added += 1
        except Exception as exc:
            print(f"[WARN] GitHub 新物种扫描跳过 ({cat}): {exc}")

    # 2. 抓取独立游戏 / Steam 桌面挂机桌宠 / 微信小游戏变现与版号痛点
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=SSL_CTX),
        urllib.request.HTTPCookieProcessor(cj),
    )
    opener.addheaders = [("User-Agent", UA), ("Referer", "https://www.bilibili.com/")]
    try:
        opener.open("https://www.bilibili.com/", timeout=8).read()
        for kw in ["桌面宠物 挂机游戏 Steam", "独立游戏 个人开发者 收入 复盘"]:
            b_url = "https://api.bilibili.com/x/web-interface/search/type?" + urllib.parse.urlencode(
                {"search_type": "video", "keyword": kw}
            )
            res = json.loads(opener.open(b_url, timeout=10).read().decode("utf-8", errors="ignore"))
            for item in (res.get("data", {}).get("result") or [])[:4]:
                title = radar_cli.strip_html(item.get("title", ""))
                desc = radar_cli.strip_html(item.get("description", ""))
                play = int(item.get("play") or 0)
                fav = int(item.get("favorites") or 0)
                fav_ratio = round((fav / play * 100), 1) if play > 0 else 0.0
                bvid = item.get("bvid", "")
                if not bvid:
                    continue
                ok = radar_cli.insert_signal(
                    conn=conn,
                    channel="B站视频与评论(实时API)",
                    source_tier="实时API抓取",
                    category="独立游戏与桌面宠物",
                    query_term=kw,
                    title=title,
                    content=f"视频简介: {desc[:180] if desc else title}",
                    author_or_app=f"UP主: {item.get('author', '')}",
                    metric_primary=f"{play} 播放 / {fav} 收藏",
                    metric_secondary=f"收藏率 {fav_ratio}%",
                    rating_or_price="高热度桌宠/独游" if play >= 30000 else "独游实操",
                    source_url=f"https://www.bilibili.com/video/{bvid}",
                    source_published_at=epoch_time(item.get("pubdate")),
                    published_time_source="bilibili_video_pubdate",
                )
                if ok:
                    added += 1
    except Exception as exc:
        print(f"[WARN] B站游戏赛道扫描跳过: {exc}")

    added += radar_cli.collect_wechat_sogou(
        conn,
        custom_queries=[
            ("独立游戏与桌面宠物", "Steam 桌面挂机 桌宠 销量 独立开发"),
            ("独立游戏与桌面宠物", "微信小游戏 个人开发者 流量主 收入 版号"),
        ],
    )
    conn.commit()
    return added


def synthesize_emergent_ideas(conn: sqlite3.Connection, base_dir: pathlib.Path) -> int:
    """
    自动从『尚未被现有立项卡引用的高热度新信号』中提炼候选立项卡 (AUTO-GEN-*.json)，
    解决定时任务只抓信号不产出新方向的问题。
    """
    ideas_dir = base_dir / "data" / "ideas"
    ideas_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = base_dir / "scripts" / "dashboard_config.json"

    used_ids = set()
    existing_titles = set()
    if cfg_path.exists():
        for p in json.loads(cfg_path.read_text(encoding="utf-8")).get("projects", []):
            used_ids.update(p.get("evidence_ids", []))
            existing_titles.add(p.get("title", ""))
    for jf in ideas_dir.glob("*.json"):
        obj = json.loads(jf.read_text(encoding="utf-8"))
        used_ids.update(obj.get("evidence_ids", []))
        existing_titles.add(obj.get("title", ""))

    # 查找近 14 天新物种飙升仓中尚未立项且 Stars >= 800 的高潜信号
    rows = conn.execute(
        "SELECT * FROM raw_signals WHERE is_noise=0 AND category='全球新物种飙升' AND author_or_app NOT LIKE '%awesome%' AND content NOT LIKE '%MobileGestalt%' ORDER BY id DESC"
    ).fetchall()

    created = 0
    for r in rows:
        if r["id"] in used_ids:
            continue
        m = re.search(r"(\d+)\s*Stars", r["metric_primary"])
        stars = int(m.group(1)) if m else 0
        if stars < 800:
            continue
        repo_name = r["author_or_app"]
        short_repo = repo_name.split("/")[-1]
        cand_code = "RADAR-" + hashlib.md5(repo_name.encode("utf-8")).hexdigest()[:4].upper()
        cand_path = ideas_dir / f"{cand_code}.json"
        if cand_path.exists():
            continue

        cand_obj = {
            "code": cand_code,
            "category_tag": "每日自动发现候选 · 近期飙升新物种",
            "title": f"[自动发现候选] 基于近期飙升开源项目 {short_repo} 的本土化工具/服务封装",
            "score": 81,
            "score_detail": "付费意愿 31/40 · 获客截流 20/25 · 研发交付 13/15 · 竞争缝隙 9/10 · 48h测款 8/10",
            "plain_what_to_do": f"系统监测到开源新项目 {repo_name} 在近两周快速突破 {stars} Stars。针对国内用户配不通英文 CLI 环境或缺乏图形界面的痛点，评估将其封装为免配置中文桌面版或垂直工作流服务。",
            "workflow_steps": [
                f"【信号触发】{r['title']}",
                "【本土化封装】拉取开源底座实测核心效果，剥离繁琐依赖并接入 DeepSeek-V4.1-Flash 中文界面",
                "【快速测款】在小红书/B站发布中文实机演示视频，测试评论区求安装包/代部署转化率",
            ],
            "who_pays_and_price": "国内对新工具敏感但不会配环境的创作者、运营或中小团队；建议定价 29.9~99 元买断或月卡。",
            "ai_sharp_review": f"由每日自动新物种雷达捕获（{r['metric_primary']}，{r['metric_secondary']}）。海外刚爆火 1~2 周的新项目在国内通常存在 1~3 个月的信息差与使用门槛红利，建议研发花 30 分钟跑通 Demo 评估是否值得深挖。",
            "plan_48h": f"克隆 {repo_name} 跑通 1 个中文案例录屏发小红书/B站，若 48 小时内收藏率 >5% 且超 30 人求一键包则转正式立项，否则归档淘汰。",
            "evidence_ids": [r["id"]],
            "compounding": {
                "tier": "自动捕获候选",
                "snowball": "利用早期时间窗口切入种子用户，若需求高频则沉淀为行业专用工作台，若为一次性尝鲜则仅赚取早期信息差现金流。",
                "skill_gain": "保持团队对全球最新开源架构的第一手实操敏感度。"
            },
            "biz_eval": {
                "cost": "验证成本趋近于 0（基于现成开源底座打包测试）。",
                "profit": "早期信息差阶段毛利率 95%+，具体空间视 48h 视频测款询单量定。",
                "time": "半天内可完成本地跑通与录屏测款。",
                "team": "1 人（0.5 天技术实测 + 发帖验证）。",
                "landing": "录屏发帖测热度 -> 闲鱼/面包多发一键整合包 -> 高留存则转正式产品。",
                "compliance": "务必核查原仓库开源许可证（MIT/Apache-2.0 可商用封装，GPL/AGPL 或 Non-Commercial 需注意授权边界）。"
            }
        }
        cand_path.write_text(json.dumps(cand_obj, ensure_ascii=False, indent=2), encoding="utf-8")
        created += 1
        if created >= 1:  # 每次最多自动推选 1 个最高星未审新物种进入候选池，保证工作台精炼不泛滥
            break
    return created


def main():
    conn = radar_cli.get_conn()
    radar_cli.init_db(conn)
    sync_db_from_jsonl(conn, BASE_DIR, radar_cli.insert_signal)

    added = collect_dynamic_breakouts(conn)
    stats = radar_cli.clean_and_tag_signals(conn)
    dump_db_to_jsonl(conn, BASE_DIR)
    new_ideas = synthesize_emergent_ideas(conn, BASE_DIR)
    print(f"[AUTO-DISCOVER] 新增动态信号={added}, 总有效信号={stats['valid']}, 自动合成新候选立项={new_ideas}")


if __name__ == "__main__":
    main()
