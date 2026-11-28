#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Market Radar 团队通用交互式采集与协同向导 (兼容 macOS / Windows / Linux)
非技术成员无需记忆命令行参数，直接运行 `python3 run_radar.py` 或双击启动脚本即可按数字菜单操作。
"""

import json
import pathlib
import subprocess
import sys
import webbrowser

ROOT = pathlib.Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
PY = sys.executable


def run_script(script_name: str, extra_args=None) -> int:
    cmd = [PY, str(SCRIPTS / script_name)] + (extra_args or [])
    print("\n>>> 执行:", " ".join(cmd))
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


def ensure_playwright():
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        print("\n[首次自动配置] 正在为您安装浏览器抓包依赖 playwright ...")
        res = subprocess.run([PY, "-m", "pip", "install", "playwright"])
        return res.returncode == 0


def open_local_workbench():
    if run_script("radar_cli.py", ["export", "--with-comments"]):
        print("本地工作台生成失败，请查看上方错误。")
        return
    html_file = ROOT / ".market-radar" / "index.html"
    if not html_file.is_file():
        print("未找到生成的本地工作台。")
        return
    webbrowser.open(html_file.as_uri())
    print("已在默认浏览器打开:", html_file)


def menu():
    while True:
        print("\n============================================================")
        print("  Market Radar · 团队市场信号采集与协同总台")
        print("============================================================")
        print("  [1] 免登录快速采集公开渠道 (AppStore差评 + B站 + 微信 + GitHub新物种)")
        print("  [2] 首次扫码保存闲鱼 / 蝉妈妈登录态（用于商品和榜单采集）")
        print("  [3] 使用本机登录态采集闲鱼价格、想要数和蝉妈妈榜单")
        print("  [4] 查看或添加团队长期监测词库 (config/watch_keywords.json)")
        print("  [5] 将我本机新抓的数据与团队 GitHub 总库安全合并并发布线上看板")
        print("  [6] 生成并打开本地最新工作台（含评论）")
        print("  [7] 免登录补采库内 V2EX / GitHub Issues 的公开评论并打开本地工作台")
        print("  [0] 退出")
        print("------------------------------------------------------------")
        choice = input("请输入功能编号 [0-7] 并回车: ").strip()

        if choice == "0":
            print("已退出。")
            break
        elif choice == "1":
            run_script("tech_radar.py")
            run_script("auto_discover_ideas.py")
            run_script("radar_cli.py", ["run-all"])
        elif choice == "2":
            if ensure_playwright():
                run_script("auto_browser_collector.py", ["--login"])
        elif choice == "3":
            if not ensure_playwright():
                continue
            kw = input("\n请输入你想抓取的关键词（多个词用逗号隔开，直接回车则使用团队默认词库）:\n> ").strip()
            tg = input("请选择采集平台 [直接回车=闲鱼和蝉妈妈 / 仅闲鱼输入 xianyu]:\n> ").strip()
            args = ["--collect"]
            if tg:
                args += ["--targets", tg]
            if kw:
                args += ["--keywords", kw]
            run_script("auto_browser_collector.py", args)
        elif choice == "4":
            cfg_p = ROOT / "config" / "watch_keywords.json"
            cfg = json.loads(cfg_p.read_text(encoding="utf-8"))
            print("\n当前团队共享抓包词库:", ", ".join(cfg.get("browser_xhr_keywords", [])))
            new_kw = input("输入要永久追加到团队词库的新词（逗号分隔，直接回车跳过）:\n> ").strip()
            if new_kw:
                for k in [x.strip() for x in new_kw.replace("，", ",").split(",") if x.strip()]:
                    if k not in cfg["browser_xhr_keywords"]:
                        cfg["browser_xhr_keywords"].append(k)
                cfg_p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
                print("已保存最新词库:", ", ".join(cfg["browser_xhr_keywords"]))
        elif choice == "5":
            print("\n正在拉取团队远端最新数据、执行无损去重合并并同步至 GitHub...")
            run_script("sync_github.py")
        elif choice in ("6", "7"):
            if choice == "7" and run_script("radar_cli.py", ["collect-comments"]):
                print("公开评论采集失败，请查看上方错误。")
                continue
            open_local_workbench()
        else:
            print("无效选项，请输入 0~7。")


if __name__ == "__main__":
    menu()
