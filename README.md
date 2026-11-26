# Market Radar — 中国互联网商机挖掘与立项投研终端

在线终端（GitHub Pages）：`https://donghyq.github.io/market-radar/`  
本地入口：克隆仓库后直接打开根目录 `index.html`（单文件自包含，内置全量证据快照，无需外部网络请求或登录）。
Roadmap 追踪（GitHub Issue #2）：`https://github.com/donghyq/market-radar/issues/2`

---

## 团队成员快速上手（3 步抓数据并合入总库，支持 macOS / Windows）

1. **拉取仓库并获得权限**：管理员在 GitHub 仓库 `Settings -> Collaborators` 中添加成员账号后，成员克隆仓库并确保已登录 `gh auth login`。
2. **零命令菜单式采集**：
   - **macOS**：直接双击根目录 `Mac一键采集向导.command`（或终端执行 `python3 run_radar.py`）
   - **Windows**：装好 Python 3 后，双击根目录 `Windows一键采集向导.bat`
   - 选 `[1]` 采集 App Store、B 站等公开渠道，再选 `[6]` 生成并打开本地工作台，在信号库点「评论（N）」。
   - 先选 `[2]` 扫码登录一次自己的闲鱼/小红书/蝉妈妈（登录态仅保存在个人电脑 `.browser_profile/`，互不干扰），再选 `[3]` 输入任意关键词即可自动抓包入库。
3. **无损合并上传**：在菜单选 `[5]`（或执行 `python3 scripts/sync_github.py`），脚本会自动拉取远端队友刚抓的数据按唯一指纹去重合并，重新编译看板并同步上线，不会互相覆盖。

---

## 一、系统架构与工程设计

本工具专为团队设计，用于从中国互联网公开及半公开交易渠道持续采集真实用户痛点，经去噪与立项评估后，生成具备商业核算（成本、利润、周期、人数、合规）的立项决策矩阵。

### 1.1 整体架构图

```
+-----------------------------------------------------------------------------------+
|                               1. 多源信号采集层                                   |
|  - 免登录 API 采集 (scripts/radar_cli.py & scripts/discovery_scanner.py)          |
|    * Apple 中国区 App Store (iTunes Search + CustomerReviews 1~3星差评 JSON 流)   |
|    * Bilibili (Web Search + Reply API，计算 Favorites/Play 收藏率与高赞痛点评论)  |
|    * 微信公众号 (搜狗微信检索解析，提取一线变现复盘与行业实测数据)                |
|    * V2EX 开发者与需求节点 (Topics API，捕获独立开发与工具求购信号)               |
|  - 登录态复用 XHR 自动抓包 (scripts/auto_browser_collector.py)                    |
|    * 基于 Playwright 持久化 Chrome Profile + page.on('response') 内存拦截 JSON    |
|    * 覆盖：蝉妈妈投流榜 / 闲鱼高想要虚拟商品 / 小红书高赞求链接帖                 |
|  - 离线 CSV 投递箱 (inbox/*.csv)                                                  |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                        2. 数据处理、清洗与无冲突持久化层                          |
|  - 格式归一化：统一映射为 15 个标准字段 (channel, category, title, content...)    |
|  - 唯一指纹去重：基于 MD5(channel|title|author) 生成 10 位 uid，增量 UPSERT       |
|  - 硬规则去噪：正则拦截纯导流软文（如“加微/进群/免费领”）与低信息量短评 (<15字)   |
|  - 多人零冲突存储 (scripts/collab_utils.py)：                                     |
|    * Git 仅追踪纯文本按行追加的 data/signals/signals_master.jsonl                 |
|    * 每个立项方向独立存储为 data/ideas/<CODE>.json，多人并行修改物理零冲突        |
|    * 本地运行时 0.1 秒派生重建 SQLite (radar.db，已列入 .gitignore)               |
|    * 每次运行自动生成按日快照 data/archives/YYYY-MM-DD.json，历史数据永久保留     |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                       3. 立项评估与主从式投研终端渲染层                           |
|  - 评分权重：付费证据(40) + 获客路径(25) + 交付周期(15) + 竞争缝隙(10) + 测款(10) |
|  - 复利与成长核算：评估项目是否具备滚雪球壁垒（组件库/行业规则库）与团队技能沉淀  |
|  - 市场部六维账本：成本预估 / 利润与来源 / 工期 / 人数 / 三阶段路径 / 合规风险    |
|  - 静态单文件构建 (scripts/export_dashboard.py)：                                 |
|    * 将 JSON 数据与 scripts/dashboard_app.js 内联编译进 scripts/template.html     |
|    * 输出根目录 index.html 与 docs/index.html (供 GitHub Pages 自动发布)          |
+-----------------------------------------------------------------------------------+
```

---

## 二、目录结构与模块职责

```text
market-radar/
├── index.html                        # 编译后的单文件投研终端（本地双击即开）
├── docs/
│   └── index.html                    # GitHub Pages 线上发布副本
├── data/
│   ├── signals/
│   │   └── signals_master.jsonl      # 全量信号唯一可信源（按行 JSONL，支持 Git 自动合并）
│   ├── ideas/
│   │   ├── AUTO-DISC-01.json         # 系统广谱扫描发现的独立立项档案
│   │   ├── AUTO-DISC-02.json
│   │   ├── AUTO-DISC-03.json
│   │   └── TEAM-FE4500.json          # 团队成员通过人脉录入的立项档案
│   └── archives/
│       └── 2026-11-18.json           # 每日例行运行生成的历史统计快照
├── inbox/
│   └── chanmama_xianyu_xhs_signals.csv # 外部平台 CSV 导表投递目录
├── exports/
│   └── signals_full.csv              # 带 UTF-8 BOM 的全量信号导出表（可直接拖入 Excel/飞书）
├── scripts/
│   ├── radar_cli.py                  # 主命令行入口（采集、清洗、人脉提报、评估、导出）
│   ├── discovery_scanner.py          # 跨赛道广谱主动痛点发现脚本（6大付费人群×痛点词矩阵）
│   ├── auto_browser_collector.py     # Playwright 真机登录态复用 + XHR JSON 自动抓包器
│   ├── collab_utils.py               # JSONL <-> SQLite 双向同步、历史归档与评分计算工具
│   ├── export_dashboard.py           # 终端页面编译器（将 JSON 与 JS 内联打包为单文件 HTML）
│   ├── template.html                 # 投研终端 HTML/CSS 骨架模板（无 Emoji 极简深色风格）
│   ├── dashboard_app.js              # 投研终端前端主从视图（Master-Detail）交互逻辑
│   ├── dashboard_config.json         # 核心立项项目与早期既有方向复盘配置
│   └── whitepaper_config.json        # 渠道原理、导表指南与 4 大战略 Roadmap 配置
└── .github/workflows/
    └── daily_radar.yml               # GitHub Actions 每日 08:30 自动增量采集与发布工作流
```

---

## 三、数据处理流水线说明（从采集到立项）

1. **历史基线恢复（`sync_db_from_jsonl`）**  
   每次执行命令时，先读取 `data/signals/signals_master.jsonl` 重建或合并至本地 `radar.db`，确保多人协作时老数据不丢失。
2. **多源增量抓取（`collect` / `discovery_scanner.py` / `auto_browser_collector.py`）**  
   依次拉取 App Store 1~3 星差评、B 站高收藏比视频与热门评论、搜狗微信实战拆解文章、V2EX 需求贴及 `inbox/*.csv`。利用 SQLite `UNIQUE(channel, title, author_or_app)` 约束自动忽略完全重复的数据。
3. **硬规则去噪与痛点打标（`clean_and_tag_signals`）**  
   - 长度 `< 15` 字符或命中营销导流正则（`免费领|扣111|加微|私信领|进群交流` 且无实质差评/销量指标）的记录标记 `is_noise = 1`，在终端中默认折叠并标注。
   - 根据正文与量化指标自动匹配标签：`付费意愿已验证`、`现有方案体验差/求平替`、`国内环境/使用门槛卡点`、`Token/算力成本高`、`B端交付与续费痛点`。
4. **JSONL 回写与按日快照（`dump_db_to_jsonl`）**  
   清洗完成后将全量记录写回 `data/signals/signals_master.jsonl`，保留每条信号的首次发现日期 `first_seen` 与最新活跃日期 `last_seen`，同时输出 `data/archives/YYYY-MM-DD.json`。
5. **立项合并与单文件终端编译（`export_dashboard.py`）**  
   自动汇总 `scripts/dashboard_config.json` 与 `data/ideas/*.json` 下的所有立项方案，按总分降序排列，内联全部证据快照生成 `index.html` 与 `docs/index.html`。

---

## 四、快速使用指南（日常操作命令）

本工具仅依赖 Python 3 标准库（仅在使用 `auto_browser_collector.py` 浏览器抓包时需本机已安装的 `playwright`），无需配置复杂虚拟环境。

### 4.1 一键日常增量更新（拉取常规渠道 + 清洗 + 重新编译看板）
```bash
python3 scripts/radar_cli.py run-all
```

### 4.2 运行跨赛道广谱主动发现（挖掘未知新方向）
```bash
python3 scripts/discovery_scanner.py
python3 scripts/export_dashboard.py
```

### 4.3 蝉妈妈 / 闲鱼 / 小红书全自动 XHR 抓包（免手动导 CSV）
```bash
# 仅首次运行：弹出 Chrome 扫码登录一次，登录态永久保存在本地 .browser_profile/
python3 scripts/auto_browser_collector.py --login

# 日常运行：自动打开对应平台并从内存截获后台 JSON 响应包直接入库
python3 scripts/auto_browser_collector.py --collect \
  --targets chanmama,xianyu,xhs \
  --keywords "知识动画代做,标书检查,报价单生成,提词器"
```

### 4.4 团队成员录入自己人脉发现的新方向（自动评分并生成独立 JSON）
除了直接在网页端 `录入新方向` 填表外，也可在终端执行：
```bash
python3 scripts/radar_cli.py submit-idea \
  --title "新项目方向名称" \
  --proposer "提报人姓名" \
  --what "输入什么 -> 系统怎么处理 -> 产出什么" \
  --buyer "目标客户与收费标准" \
  --evidence "人脉验证或已付费证据" \
  --channel "首批客户获客路径" \
  --mvp-days 5
```

### 4.5 同步最新数据与看板至 GitHub 仓库及线上 Pages

先用当前主分支的渲染代码导出页面，再使用有写入权限的 GitHub 账号同步。同步脚本只提交数据和生成后的页面；如本地渲染代码落后、页面未重新生成或远端已有新提交，同步会停止。代码改动通过 Git 提交发布。

```bash
python3 scripts/sync_github.py --check
python3 scripts/sync_github.py
```

### 4.6 本地导入评论和核对用户标签

将获准使用的评论表保存为 `inbox/comments_*.csv`（Git 忽略）。评论行包含 `record_type=comment`、`channel`、平台内唯一的 `comment_id`、`parent_url` 和 `content`。可附 `commented_at`（ISO 日期或带时区时间）、`source_url`、`author_profile_url`。已有的用户资料可填 `age`、`ip_location`（平台展示的属地）、`occupation`、`interests` 以及共同的 `profile_source`，也可为单个字段填对应的 `<字段>_source`。

运行现有 App Store 或 B 站采集流程时，应用和视频进信号库，抓到的评价和留言进本地评论库。系统用平台评论 ID 去重，以应用页或视频链接关联对应信号。App Store 评论时间采用平台返回的评价更新时间。

```bash
python scripts/radar_cli.py import-csv
python scripts/radar_cli.py export --with-comments
```

在 `.market-radar/index.html` 的信号库查看评论、标签和覆盖率，在 `.market-radar/exports/signals_full.csv` 核对标签来源。评论和这些导出都保存在 Git 忽略的本地目录，正常发布页仍走原有入口。

---

## 五、团队接力开发指南（如何扩展系统）

### 5.1 如何新增一个自动化信息采集渠道？
1. 打开 `scripts/radar_cli.py` 或 `scripts/discovery_scanner.py`。
2. 编写采集函数 `collect_your_source(conn)`，请求公开 JSON/RSS/HTML 后调用统一入库函数：
   ```python
   insert_signal(
       conn=conn,
       channel="渠道名称(如:七麦数据低分高收榜)",
       source_tier="实时API抓取",
       category="所属赛道分类",
       query_term="检索词",
       title="信号标题",
       content="完整痛点描述或用户评论原文",
       author_or_app="应用名或作者",
       metric_primary="主量化指标(如:月估收入/评论数)",
       metric_secondary="副指标(如:评分3.2)",
       rating_or_price="价格或内购属性",
       source_url="原始链接"
   )
   ```
3. 运行 `python3 scripts/radar_cli.py clean && python3 scripts/export_dashboard.py` 即可在终端中看到新增信号。

### 5.2 如何修改或新增立项深度评估档案？
- **新增独立项目**：直接在 `data/ideas/` 目录下新建一个 `.json` 文件（参考 `data/ideas/AUTO-DISC-01.json` 结构，包含 `workflow_steps`、`compounding` 复利成长评估、`biz_eval` 成本与收益核算表与 `evidence_ids` 关联证据编号数组），然后运行 `python3 scripts/export_dashboard.py`。
- **调整前端界面**：修改 `scripts/template.html`（样式与布局）或 `scripts/dashboard_app.js`（渲染逻辑），运行 `python3 scripts/export_dashboard.py` 重新编译单文件 `index.html`。
