#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蝉妈妈 / 闲鱼 / 小红书 全自动真机 XHR 精确采集器
利用本地 .browser_profile 登录态 + 反 webdriver 检测，直接拦截并精确解析：
1. 闲鱼 (mtop.taobao.idlemtopsearch.pc.search/1.0)：提取真实商品描述、价格、想要人数、好评标签、地区与单品直达链接；
2. 小红书 (so.xiaohongshu.com/api/sns/web/v2/search/notes)：提取真实痛点笔记标题、点赞数、作者、发布日期与 xsec_token 链接；
3. 蝉妈妈 (/douyin/ 搜索与热榜 API)：提取抖音带货选品、低粉爆款视频与实时商业热词。
"""

import argparse
import datetime
import json
import pathlib
import random
import re
import sys
import urllib.parse
from typing import Any, Dict, List

from signal_time import MARKET_TIMEZONE, market_today, source_time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE_DIR / ".browser_profile"
import os
import platform

def find_system_browser() -> str:
    """跨平台自动探测本机已安装的 Chrome 或 Edge 浏览器路径（兼容 macOS / Windows / Linux）"""
    env_p = os.environ.get("MR_BROWSER_PATH", "").strip()
    if env_p and pathlib.Path(env_p).exists():
        return env_p
    sys_name = platform.system()
    candidates = []
    if sys_name == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            str(pathlib.Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    elif sys_name == "Windows":
        for root in [os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", ""), os.environ.get("LOCALAPPDATA", "")]:
            if root:
                candidates.append(str(pathlib.Path(root) / "Google/Chrome/Application/chrome.exe"))
                candidates.append(str(pathlib.Path(root) / "Microsoft/Edge/Application/msedge.exe"))
    else:
        candidates = ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/microsoft-edge"]
    for c in candidates:
        if pathlib.Path(c).exists():
            return c
    return ""

def load_default_keywords() -> str:
    cfg = BASE_DIR / "config" / "watch_keywords.json"
    if cfg.exists():
        try:
            kws = json.loads(cfg.read_text(encoding="utf-8")).get("browser_xhr_keywords", [])
            if kws:
                return ",".join(kws)
        except Exception:
            pass
    return "microduck,桌面机器人,知识动画代做,标书检查,考研学习规划表"

CHROME_PATH = find_system_browser()
TODAY = market_today()


def parse_xhs_date(tag_text: str) -> str:
    t = tag_text.strip()
    now = datetime.datetime.now(MARKET_TIMEZONE)
    if t in ("今天", "刚刚"):
        return now.date().isoformat()
    if t == "昨天":
        return (now.date() - datetime.timedelta(days=1)).isoformat()
    ago = re.fullmatch(r"(\d+)\s*(天|小时|分钟)前", t)
    if ago:
        units = {"天": 1440, "小时": 60, "分钟": 1}
        minutes = int(ago[1]) * units[ago[2]]
        try:
            return (now - datetime.timedelta(minutes=minutes)).date().isoformat()
        except OverflowError:
            return ""
    return source_time(t)[0]


def parse_xianyu_response(data: Dict[str, Any], kw: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    rlist = (data.get("data") or {}).get("resultList") or []
    for entry in rlist:
        try:
            main = ((entry.get("data") or {}).get("item") or {}).get("main") or {}
            ex = main.get("exContent") or {}
            args = ((main.get("clickParam") or {}).get("args") or {})
            title = str(ex.get("title") or "").strip()
            if len(title) < 8:
                continue
            item_id = ex.get("itemId") or args.get("id") or ""
            nick = ex.get("userNickName") or "闲鱼卖家"
            area = ex.get("area") or ""
            price_val = args.get("price") or ""
            if not price_val and isinstance(ex.get("price"), list):
                price_val = "".join(str(p.get("text", "")) for p in ex["price"] if isinstance(p, dict))
            want_num = int(args.get("wantNum") or 0)

            tags_txt = []
            ftags = ex.get("fishTags") or {}
            for r_key in ("r2", "r3", "r4"):
                for tg in ((ftags.get(r_key) or {}).get("tagList") or []):
                    c = ((tg.get("data") or {}).get("content") or "")
                    if c and "Icon" not in c:
                        tags_txt.append(str(c))
            tag_summary = " · ".join(tags_txt) if tags_txt else f"{want_num}人想要"

            out.append({
                "channel": "闲鱼真实交易(自动抓包)",
                "source_tier": "真机XHR实时抓包",
                "category": f"闲鱼交易验证:{kw}",
                "query_term": kw,
                "title": f"[闲鱼在售 ¥{price_val}] {title[:85]}",
                "content": f"闲鱼真实商品详情：{title}（卖家：{nick}，地区：{area}，交易热度标签：{tag_summary}）",
                "author": f"闲鱼 @{nick}" + (f" ({area})" if area else ""),
                "m1": f"{want_num} 人想要" if want_num > 0 else (tags_txt[0] if tags_txt else "在售服务"),
                "m2": tag_summary[:60],
                "price": f"¥{price_val}" if price_val else "定制报价",
                "url": f"https://www.goofish.com/item?id={item_id}" if item_id else f"https://www.goofish.com/search?q={urllib.parse.quote(kw)}",
                "pub": TODAY.isoformat(),
            })
        except Exception:
            continue
    return out


def parse_xhs_response(data: Dict[str, Any], kw: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    items = (data.get("data") or {}).get("items") or []
    for it in items:
        try:
            if it.get("model_type") != "note":
                continue
            nc = it.get("note_card") or {}
            nid = it.get("id") or ""
            xsec = it.get("xsec_token") or ""
            title = str(nc.get("display_title") or "").strip()
            if len(title) < 4:
                continue
            user = (nc.get("user") or {}).get("nickname") or "小红书博主"
            liked = str((nc.get("interact_info") or {}).get("liked_count") or "0")
            pub_raw = ""
            for tg in (nc.get("corner_tag_info") or []):
                if tg.get("type") == "publish_time":
                    pub_raw = tg.get("text") or ""
            pub_dt = parse_xhs_date(pub_raw)
            # 拦截超 180 天的陈旧小红书笔记
            if pub_dt and (TODAY - datetime.date.fromisoformat(pub_dt[:10])).days > 180:
                continue

            url = f"https://www.xiaohongshu.com/explore/{nid}" + (f"?xsec_token={xsec}&xsec_source=pc_search" if xsec else "")
            out.append({
                "channel": "小红书真实笔记(自动抓包)",
                "source_tier": "真机XHR实时抓包",
                "category": f"小红书需求验证:{kw}",
                "query_term": kw,
                "title": f"[小红书笔记] {title[:95]}",
                "content": f"小红书一线需求/实测笔记：《{title}》 — 作者：{user}，当前获赞：{liked}，发布时间标签：{pub_raw or '未知'}",
                "author": f"小红书 @{user}",
                "m1": f"{liked} 点赞",
                "m2": f"发布: {pub_raw or pub_dt or '未知'}",
                "price": "高互动种草/求助",
                "url": url,
                "pub": pub_dt,
                "source_pub": pub_dt,
            })
        except Exception:
            continue
    return out


def parse_chanmama_response(url: str, data: Dict[str, Any], kw: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    d_node = data.get("data")
    rows = []
    if isinstance(d_node, dict):
        rows = d_node.get("list") or d_node.get("rows") or []
    elif isinstance(d_node, list):
        rows = d_node
    if not isinstance(rows, list):
        return out

    for r in rows[:15]:
        if not isinstance(r, dict):
            continue
        title = str(r.get("title") or r.get("product_title") or r.get("aweme_title") or "").strip()
        if len(title) < 5:
            continue
        # 过滤掉纯聊天推荐问题
        if "object_type" in r and "message" in r:
            continue
        sales = r.get("volume_text") or r.get("day30_volume_text") or r.get("sales") or r.get("digg_count") or r.get("hot_score") or ""
        price = r.get("price_text") or r.get("price") or ""
        author = r.get("author_name") or r.get("nickname") or r.get("brand_name") or "抖音/蝉妈妈数据"
        out.append({
            "channel": "蝉妈妈抖音数据(自动抓包)",
            "source_tier": "真机XHR实时抓包",
            "category": f"蝉妈妈商业监测:{kw}",
            "query_term": kw,
            "title": f"[蝉妈妈榜单/选品] {title[:95]}",
            "content": f"蝉妈妈实时监测条目：{title}（关联达人/品牌：{author}，销量/热度指标：{sales}，价格：{price}）",
            "author": str(author)[:60],
            "m1": f"热度/销量 {sales}" if sales else "蝉妈妈收录",
            "m2": f"检索词: {kw}",
            "price": f"¥{price}" if price else "抖音商业数据",
            "url": "https://www.chanmama.com/douyin/",
            "pub": TODAY.isoformat(),
        })
    return out


def run_browser_collector(mode: str, targets: List[str], keywords: List[str]) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("未检测到 playwright 库，请先在终端执行一次: pip3 install playwright")
    import radar_cli
    from collab_utils import dump_db_to_jsonl, sync_db_from_jsonl
    from persona_and_freshness import ensure_columns, enrich_all_signals

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    conn = radar_cli.get_conn()
    radar_cli.init_db(conn)
    ensure_columns(conn)
    sync_db_from_jsonl(conn, BASE_DIR, radar_cli.insert_signal)

    captured: List[Dict[str, str]] = []
    cur_kw = {"kw": ""}

    with sync_playwright() as p:
        # 注意：闲鱼 baxia 风控会拦截 headless=True，使用非无头真机窗口 + 屏蔽 webdriver 可 100% 稳定通过
        launch_kwargs: Dict[str, Any] = {
            "user_data_dir": str(PROFILE_DIR),
            "headless": False,
            "viewport": {"width": 1360, "height": 860},
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if CHROME_PATH and pathlib.Path(CHROME_PATH).exists():
            launch_kwargs["executable_path"] = CHROME_PATH

        context = p.chromium.launch_persistent_context(**launch_kwargs)
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = context.pages[0] if context.pages else context.new_page()

        if mode == "login":
            page.goto("https://www.chanmama.com/", wait_until="domcontentloaded")
            p2 = context.new_page(); p2.goto("https://www.goofish.com/", wait_until="domcontentloaded")
            # 安全熔断：小红书对 CDP/AI 浏览器自动化检测极严，禁止绑定个人主号跑自动浏览
            try:
                page.wait_for_event("close", timeout=300000)
            except Exception:
                pass
            context.close()
            return 0

        def on_response(resp):
            u = resp.url
            if resp.status != 200:
                return
            try:
                if "mtop.taobao.idlemtopsearch.pc.search/1.0" in u:
                    captured.extend(parse_xianyu_response(resp.json(), cur_kw["kw"]))
                elif "/api/sns/web/v2/search/notes" in u or "/api/sns/web/v1/search/notes" in u:
                    captured.extend(parse_xhs_response(resp.json(), cur_kw["kw"]))
                elif "api-service.chanmama.com" in u and "json" in resp.headers.get("content-type", ""):
                    if not any(skip in u for skip in ["/config/", "/user/", "aiQuestion"]):
                        captured.extend(parse_chanmama_response(u, resp.json(), cur_kw["kw"]))
            except Exception:
                pass

        page.on("response", on_response)

        if "xianyu" in targets:
            for kw in keywords[:4]:
                cur_kw["kw"] = kw
                u = "https://www.goofish.com/search?q=" + urllib.parse.quote(kw)
                print(f"[闲鱼抓包] 正在检索: {kw}")
                try:
                    page.goto(u, wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(random.randint(6500, 11500))
                except Exception as exc:
                    print(f"  [WARN] 闲鱼跳过 ({kw}): {exc}")

        if "xhs" in targets:
            print("[安全拦截] 小红书反 AI 自动化浏览风控极严，为保护团队成员账号安全，已默认熔断小红书登录态自动抓取！请改用免登录公开检索或人工录入高赞神帖。")
        if False and "xhs" in targets:
            for kw in keywords:
                cur_kw["kw"] = kw
                u = f"https://www.xiaohongshu.com/search_result?keyword={urllib.parse.quote(kw)}&source=web_search_result_notes"
                print(f"[小红书抓包] 正在检索: {kw}")
                try:
                    page.goto(u, wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(random.randint(6500, 11500))
                except Exception as exc:
                    print(f"  [WARN] 小红书跳过 ({kw}): {exc}")

        if "chanmama" in targets:
            cm_pages = [
                ("抖音带货销量商品榜", "https://www.chanmama.com/promotionRank/tikGoodsSale/"),
                ("抖音带货爆款视频榜", "https://www.chanmama.com/awemeRank/promotionAweme/"),
            ]
            for label, cm_url in cm_pages:
                cur_kw["kw"] = label
                print(f"[蝉妈妈抓包] 正在读取: {label}")
                try:
                    page.goto(cm_url, wait_until="domcontentloaded", timeout=18000)
                    page.wait_for_timeout(4000)
                    for kw in ["错题", "桌面宠物", "软件", "课程"]:
                        inps = page.locator("input:visible:not([readonly])[placeholder*='商品'], input:visible:not([readonly])[placeholder*='视频'], input:visible:not([readonly])[placeholder*='关键'], input:visible:not([readonly])[placeholder*='搜索']")
                        if inps.count() > 0:
                            cur_kw["kw"] = kw
                            inps.first.fill(kw)
                            inps.first.press("Enter")
                            page.wait_for_timeout(3500)
                except Exception as exc:
                    print(f"  [WARN] 蝉妈妈跳过 ({label}): {exc}")

        context.close()

    added = 0
    for rec in captured:
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
            source_published_at=rec.get("source_pub", ""),
            published_time_source="xiaohongshu_publish_label",
        )
        if ok:
            added += 1
    conn.commit()

    stats = radar_cli.clean_and_tag_signals(conn)
    rep = enrich_all_signals(conn, TODAY.isoformat())
    dump_db_to_jsonl(conn, BASE_DIR)
    (BASE_DIR / "data" / "persona_stats.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    from export_dashboard import export_all
    export_all(conn, BASE_DIR)
    print(f"[AUTO-BROWSER] 采集完毕：截获候选={len(captured)} 条，去重后新增入库={added} 条 | 当前库内总信号={stats['total']} (有效={stats['valid']})")
    return added


def main():
    parser = argparse.ArgumentParser(description="蝉妈妈/闲鱼/小红书真机 XHR 精确抓包器")
    parser.add_argument("--login", action="store_true", help="打开 Chrome 扫码登录一次并保存 Cookie")
    parser.add_argument("--collect", action="store_true", help="全自动拦截 XHR 数据包入库")
    parser.add_argument("--targets", default="xianyu,chanmama", help="安全目标平台: xianyu,chanmama（小红书已默认熔断防封号）")
    parser.add_argument("--force-unsafe-xhs", action="store_true", help="不推荐：强制使用测试小号抓小红书")
    parser.add_argument(
        "--keywords",
        default=load_default_keywords(),
        help="逗号分隔的搜索词",
    )
    args = parser.parse_args()
    mode = "login" if args.login else "collect"
    targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    run_browser_collector(mode=mode, targets=targets, keywords=keywords)


if __name__ == "__main__":
    main()
