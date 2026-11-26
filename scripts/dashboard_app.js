
function buildCollectCmd() {
  const kws = (document.getElementById("cgKw")?.value || "microduck,桌面宠物,标书检查").trim();
  const tgs = [];
  if (document.getElementById("cgXy")?.checked) tgs.push("xianyu");
  if (document.getElementById("cgCm")?.checked) tgs.push("chanmama");
  const tgStr = tgs.length ? tgs.join(",") : "xianyu";
  const out = document.getElementById("cgOut");
  if (out) {
    out.textContent = `python3 scripts/auto_browser_collector.py --collect --targets ${tgStr} --keywords "${kws}" && python3 scripts/sync_github.py`;
  }
}


const SIGNAL_DAY_MS = 86400000;
const MARKET_OFFSET_MS = 8 * 3600000;

function signalTiming(s, now = Date.now()) {
  const legacyDate = !s.source_published_at && s.published_time_source === 'legacy_archive_date';
  const raw = legacyDate ? s.published_at : s.source_published_at;
  const precision = legacyDate ? 'date' : s.published_time_precision;
  const unknown = {tier: 'recent_unverified', hour24: false, order: -Infinity};
  if (!raw || !['date', 'timestamp'].includes(precision)) return unknown;

  const dayOnly = precision === 'date';
  const stamp = Date.parse(dayOnly ? raw + 'T00:00:00Z' : raw);
  const today = Math.floor((now + MARKET_OFFSET_MS) / SIGNAL_DAY_MS);
  const day = Math.floor((stamp + (dayOnly ? 0 : MARKET_OFFSET_MS)) / SIGNAL_DAY_MS);
  const age = today - day;
  if (!Number.isFinite(stamp) || age < 0 || (!dayOnly && stamp > now)) return unknown;

  const tier = age <= 7 ? '7d_hot' : age <= 30 ? '30d_active' :
    age <= 90 ? '90d_recent' : age <= 180 ? '180d_halfyear' : 'stale_archive';
  return {tier, hour24: !dayOnly && now - stamp <= SIGNAL_DAY_MS,
    order: dayOnly ? stamp - MARKET_OFFSET_MS : stamp};
}

function signalPublishedText(s) {
  if (signalTiming(s).tier !== 'recent_unverified') {
    return s.source_published_at || s.published_at + '（归档标记）';
  }
  return s.published_at ? '待核实（旧记录 ' + s.published_at + '）' : '待核实';
}

function freshBadge(tier, pubDate, hour24) {
  const dt = esc(pubDate || "未知");
  if (hour24) return `<span class="fresh-badge fresh-7d">近 24 小时 · ${dt}</span>`;
  if (tier === "7d_hot") return `<span class="fresh-badge fresh-7d">近7天 · ${dt}</span>`;
  if (tier === "30d_active") return `<span class="fresh-badge fresh-30d">近30天 · ${dt}</span>`;
  if (tier === "90d_recent" || tier === "180d_halfyear") return `<span class="fresh-badge fresh-90d">近期 · ${dt}</span>`;
  if (tier === "stale_archive") return `<span class="fresh-badge fresh-stale">历史旧帖 · ${dt}</span>`;
  return `<span class="fresh-badge fresh-90d">${dt}</span>`;
}

function jumpToAudienceSignals(audName) {
  const btns = document.querySelectorAll(".nav-btn");
  let sigBtn = null;
  btns.forEach(b => { if (b.textContent.includes("信号库")) sigBtn = b; });
  if (sigBtn) switchTab("tab-signals", sigBtn);
  const audSel = document.getElementById("audSelect");
  const timeSel = document.getElementById("timeSelect");
  SIG_PAGE = 1;
  if (audSel) audSel.value = audName;
  if (timeSel) timeSel.value = "active180";
  filterRows();
}

function renderPersonaAndFreshness() {
  const ps = DATA.persona_stats || {};
  const personas = ps.audience_personas || [];
  const maxTotal = Math.max(1, ...personas.map(p => p.total || 1));
  const showComments = Boolean(DATA.comment_coverage);
  const windows = [
    ['24h', '近 24 小时'],
    ['7d_hot', '近 7 天（其余）'],
    ['30d_active', '8–30 天'],
    ['90d_recent', '31–90 天'],
    ['180d_halfyear', '91–180 天'],
    ['stale_archive', '超过 180 天'],
    ['recent_unverified', '时间待核实'],
  ];
  const distribution = new Map(windows.map(([key]) => [key, {signals: 0, comments: 0}]));
  const now = Date.now();
  for (const record of DATA.signals || []) {
    if (record.is_noise) continue;
    const {hour24, tier} = signalTiming(record, now);
    const counts = distribution.get(hour24 ? '24h' : tier);
    counts[record.record_type === 'comment' ? 'comments' : 'signals']++;
  }
  const layers = [['signals', '信号']];
  if (showComments) layers.push(['comments', '已导入评论']);
  const timeCards = layers.map(([kind, title]) => `
    <section class="timeline-layer" aria-labelledby="timeline-${kind}">
      <h3 id="timeline-${kind}">${title}</h3>
      <div class="timeline-grid">
        ${windows.map(([key, label]) => `
          <div class="card-cell" data-window="${key}">
            <span class="cell-k">${label}</span>
            <div class="timeline-count">${distribution.get(key)[kind]} <small>条</small></div>
          </div>
        `).join('')}
      </div>
    </section>
  `).join('');

  const pRows = personas.map((p, idx) => {
    const freshPct = Math.round(((p.fresh_30d || 0) / maxTotal) * 100);
    const oldPct = Math.round((((p.total || 0) - (p.fresh_30d || 0)) / maxTotal) * 100);
    const freshRatio = p.total ? Math.round((p.fresh_30d / p.total) * 100) : 0;
    return `
      <tr>
        <td width="48" class="mono" style="color:var(--text-muted);">${String(idx+1).padStart(2,"0")}</td>
        <td width="220">
          <strong style="color:var(--text);font-size:13.5px;">${esc(p.audience)}</strong>
          <div class="persona-bar-bg">
            <div class="persona-bar-fresh" style="width:${freshPct}%" title="近30天当下信号"></div>
            <div class="persona-bar-old" style="width:${oldPct}%" title="早于30天信号"></div>
          </div>
        </td>
        <td width="165" class="mono">
          <strong style="color:var(--accent);font-size:14px;">${p.fresh_30d} 条近30天</strong>
          <div style="font-size:11.5px;color:var(--text-muted);">总计 ${p.total} 条 · 当下占比 ${freshRatio}%${p.stale_cnt ? ` · 含旧帖 ${p.stale_cnt}` : ""}</div>
        </td>
        <td style="color:var(--text-secondary);">${esc(p.pay_habit)}</td>
        <td width="175" style="color:var(--text);font-weight:500;">${esc(p.price_band)}</td>
        <td width="190" style="color:var(--text-secondary);font-size:12.5px;">${esc(p.channels)}</td>
        <td width="105"><button class="btn" onclick="jumpToAudienceSignals('${esc(p.audience)}')">查看信号 →</button></td>
      </tr>
    `;
  }).join("");

  const el = document.getElementById("tab-persona");
  if (!el) return;
  el.innerHTML = `
    <div class="inspector" style="margin-bottom:18px;">
      <div class="ins-head" style="margin-bottom:16px;padding-bottom:12px;">
        <div>
          <span class="sec-label">01 / 按发布时间统计有效记录</span>
          <h2 class="ins-title">时效性分布</h2>
        </div>
      </div>
      <div id="freshnessDistribution">${timeCards}</div>
    </div>

    <div class="inspector">
      <div class="ins-head" style="margin-bottom:14px;padding-bottom:12px;">
        <div>
          <span class="sec-label">02 / 买单人群标签与付费画像统计（按近 30 天当下信号热度排序）</span>
          <h2 class="ins-title">目标客群盘子对比：谁在当下最活跃、怎么付钱、去哪获客截流</h2>
        </div>
      </div>
      <div class="table-wrap" style="margin-bottom:0;">
        <table>
          <thead>
            <tr>
              <th>序号</th>
              <th>买单人群画像标签</th>
              <th>当下活跃度 (近30天 / 总量)</th>
              <th>典型付费心理与决策特征</th>
              <th>主力接受定价区间</th>
              <th>核心获客与截流阵地</th>
              <th>下钻明细</th>
            </tr>
          </thead>
          <tbody>${pRows}</tbody>
        </table>
      </div>
    </div>
  `;
}

const SIG_MAP = Object.create(null);
(DATA.signals || []).forEach(s => { SIG_MAP[s.id] = s; });
const {commentsByPost, postByComment} = indexSignalComments(DATA.signals || []);


function cleanText(s) {
  if (!s) return '';
  // Strip decorative emojis for a clean, institutional terminal look
  return String(s).replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/gu, '').replace(/\s+/g, ' ').trim();
}

function esc(s) {
  return cleanText(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function getAllProjects() {
  let local = [];
  try { local = JSON.parse(localStorage.getItem('mr_custom_ideas') || '[]'); } catch(e) {}
  const merged = new Map((DATA.projects || []).map(p => [p.code, p]));
  if (Array.isArray(local)) local.forEach(p => { if (p?.code && !merged.has(p.code)) merged.set(p.code, p); });
  const all = [...merged.values()];
  all.sort((a,b) => (b.score || 0) - (a.score || 0));
  return all;
}

function renderDetailCard(p, idx) {
  const steps = (p.workflow_steps || []).map((st, i) =>
    `<div class="step-row"><span class="step-no">0${i+1}</span><div>${esc(st)}</div></div>`
  ).join('');

  const comp = p.compounding || {
    tier: "可持续积累 · 标准化产品资产",
    snowball: "初期通过轻量服务验证需求，中期沉淀行业模板与自动化流水线转为订阅制SaaS。",
    skill_gain: "沉淀领域工作流编排与高转化产品工程能力。"
  };

  const b = p.biz_eval || {
    cost: "初期成本 <100元", profit: "毛利率 90%+", time: "MVP 5~7天",
    team: "1~2人", landing: "48h测款 -> 自动化交付 -> 订阅SaaS", compliance: "遵守平台与数据脱敏规范"
  };

  const chips = (p.evidence_ids || []).map(eid => {
    const s = SIG_MAP[eid];
    if (!s) return '';
    return `<button class="btn" onclick="openSnap(${eid})">证据 #${eid} · ${esc(cleanText(s.author_or_app).slice(0,14))} (${esc(s.metric_primary)})</button>`;
  }).join(' ');

  return `
    <div class="inspector">
      <div class="ins-head">
        <div>
          <div style="display:flex;gap:8px;align-items:center;">
            <span class="pill pill-s">RANK ${String(idx + 1).padStart(2, '0')} · ${esc(comp.tier)}</span>
            <span class="pill">${esc(sourceLabel(p))}</span>
          </div>
          <h2 class="ins-title">${esc(p.title)}</h2>
        </div>
        <div class="ins-score-box">
          <div class="ins-score-big">${scoreText(p)}<span style="font-size:13px;color:var(--text-muted);font-weight:400;"> / 100</span></div>
          <div class="ins-score-sub">${esc(p.score_detail)}</div>
        </div>
      </div>

      <span class="sec-label">01 / 产品定位与一句话定义</span>
      <div class="summary-lead">${esc(p.plain_what_to_do)}</div>

      <div class="grid-2">
        <div class="card-cell">
          <span class="cell-k">运转流程（输入 → 处理 → 产出）</span>
          <div class="cell-v">${steps}</div>
        </div>
        <div class="card-cell">
          <span class="cell-k">目标客群、定价策略与 AI 锐评依据</span>
          <div class="cell-v" style="margin-bottom:10px;"><strong style="color:var(--text);">定价与客群：</strong>${esc(p.who_pays_and_price)}</div>
          <div class="cell-v"><strong style="color:var(--text);">AI 锐评依据：</strong>${esc(p.ai_sharp_review)}</div>
        </div>
      </div>

      <span class="sec-label">02 / 长期复利壁垒与团队技术沉淀</span>
      <div class="grid-2">
        <div class="card-cell" style="border-left:2px solid var(--accent);">
          <span class="cell-k" style="color:var(--text);">长期复利与数据壁垒</span>
          <div class="cell-v">${esc(comp.snowball)}</div>
        </div>
        <div class="card-cell" style="border-left:2px solid var(--pos);">
          <span class="cell-k" style="color:var(--text);">对团队成员的技术与业务成长价值</span>
          <div class="cell-v">${esc(comp.skill_gain)}</div>
        </div>
      </div>

      <span class="sec-label">03 / 成本、收益、工期、人数与合规核算</span>
      <div class="grid-3">
        <div class="card-cell"><span class="cell-k">1. 初步资金成本预估</span><div class="cell-v">${esc(b.cost)}</div></div>
        <div class="card-cell"><span class="cell-k">2. 利润预估与多元收入来源</span><div class="cell-v">${esc(b.profit)}</div></div>
        <div class="card-cell"><span class="cell-k">3. 时间成本（研发与回本周期）</span><div class="cell-v">${esc(b.time)}</div></div>
        <div class="card-cell"><span class="cell-k">4. 需要人数与角色配置</span><div class="cell-v">${esc(b.team)}</div></div>
        <div class="card-cell"><span class="cell-k">5. 三阶段落地推进路径</span><div class="cell-v">${esc(b.landing)}</div></div>
        <div class="card-cell"><span class="cell-k">6. 国内法律与平台合规边界</span><div class="cell-v">${esc(b.compliance)}</div></div>
      </div>

      <span class="sec-label">04 / 48 小时测款方案与关联证据</span>
      <div class="card-cell" style="margin-bottom:12px;">
        <span class="cell-k" style="color:var(--text);">48 小时测款动作</span>
        <div class="cell-v">${esc(p.plan_48h)}</div>
      </div>
      ${chips ? `<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;"><span style="font-size:12px;color:var(--text-muted);">点击查看本地免登录证据快照：</span>${chips}</div>` : ''}
    </div>
  `;
}

let SIG_PAGE = 1;
const SIG_PAGE_SIZE = 50;
let FILTERED_SIGS = [];

function renderSignals() {
  const sigs = DATA.signals || [];
  const now = Date.now();
  document.getElementById('lblSigCnt').innerText = sigs.filter(s => !s.is_noise && signalTiming(s, now).tier === '7d_hot').length;
  const allAuds = [...new Set(sigs.map(s => cleanText(s.audience_tag)).filter(Boolean))];
  const allChs = [...new Set(sigs.map(s => cleanText(s.channel)).filter(Boolean))];
  const coverage = DATA.comment_coverage;

  document.getElementById('tab-signals').innerHTML = `
    <div class="signal-controls" style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px;">
      <input id="qInput" style="max-width:260px;" aria-label="搜索信号" placeholder="搜索编号(#12)、标题、原文或人群..." oninput="SIG_PAGE=1;filterRows()">
      <select id="timeSelect" style="max-width:205px;" aria-label="按发布时效筛选" onchange="SIG_PAGE=1;filterRows()">
        <option value="24h">近 24 小时</option>
        <option value="7d" selected>近 7 天</option>
        <option value="30d">近 30 天</option>
        <option value="active180">近 180 天</option>
        <option value="stale_only">超过 180 天</option>
        <option value="unknown">时间待核实</option>
        <option value="all_time">全部时间</option>
      </select>
      ${coverage ? `<select id="sortSelect" aria-label="排序方式" onchange="SIG_PAGE=1;filterRows()">
        <option value="post">发帖时间优先</option>
        <option value="comment" selected>新评时间优先</option>
      </select>` : ''}
      <select id="audSelect" style="max-width:215px;" aria-label="按买单人群筛选" onchange="SIG_PAGE=1;filterRows()">
        <option value="">全部买单人群 (${allAuds.length}类)</option>
        ${allAuds.map(a => `<option value="${esc(a)}">${esc(a)}</option>`).join('')}
      </select>
      <select id="chSelect" style="max-width:190px;" aria-label="按渠道筛选" onchange="SIG_PAGE=1;filterRows()">
        <option value="">全部渠道 (${allChs.length}个)</option>
        ${allChs.map(ch => `<option value="${esc(ch)}">${esc(ch)}</option>`).join('')}
      </select>
      <select id="noiseSelect" style="max-width:120px;" aria-label="按有效性筛选" onchange="SIG_PAGE=1;filterRows()">
        <option value="valid">有效信号</option>
        <option value="all">含噪音</option>
      </select>
      ${coverage ? `<select id="recordSelect" aria-label="按记录类型筛选" onchange="SIG_PAGE=1;filterRows()">
        <option value="">全部记录</option><option value="comment">仅看评论</option>
        <option value="signal">仅看信号</option>
      </select>` : ''}
      <output id="signalCount" aria-live="polite" style="font-size:12.5px;color:var(--text-muted);"></output>
    </div>
    ${coverage?.total ? `<p id="commentCoverage" style="color:var(--text-muted);font-size:12px;">
      标签覆盖（${coverage.total} 条评论）${Object.entries(COMMENT_LABEL_NAMES).map(([key, name]) => {
        const n = coverage.counts[key];
        return `${name} ${n}/${coverage.total}（${(100*n/coverage.total).toFixed(1)}%）`;
      }).join(' · ')}
    </p>` : ''}
    <div class="table-wrap" role="region" aria-label="信号明细" tabindex="0">
      <table>
        <thead><tr><th class="signal-time">编号 / 源站发布日</th><th width="185">渠道 / 买单人群画像</th><th width="160">来源对象</th><th>标题与本地保存的正文摘要</th><th width="155">量化指标</th><th width="95">操作</th></tr></thead>
        <tbody id="sigTbody"></tbody>
      </table>
    </div>
    <div id="sigPager" style="display:flex;justify-content:space-between;align-items:center;margin-top:12px;"></div>
  `;
  filterRows();
}

function changeSigPage(delta) {
  const totalPages = Math.max(1, Math.ceil(FILTERED_SIGS.length / SIG_PAGE_SIZE));
  SIG_PAGE = Math.max(1, Math.min(totalPages, SIG_PAGE + delta));
  renderSigPage();
  document.getElementById('tab-signals')?.scrollIntoView({block:'start'});
}

function signalExcerpt(value, limit) {
  const text = cleanText(value);
  const characters = [...text];
  return characters.length > limit ? characters.slice(0, limit).join('') + '...' : text;
}

function renderSigPage() {
  const total = FILTERED_SIGS.length;
  const totalPages = Math.max(1, Math.ceil(total / SIG_PAGE_SIZE));
  if (SIG_PAGE > totalPages) SIG_PAGE = totalPages;
  const start = (SIG_PAGE - 1) * SIG_PAGE_SIZE;
  const slice = FILTERED_SIGS.slice(start, start + SIG_PAGE_SIZE);

  const now = Date.now();
  const rowsHtml = slice.map(({signal: s, matchedComment}) => {
    const source = sourceLink(s.source_url);
    const timing = signalTiming(s, now);
    const comments = commentsByPost.get(s.id) || [];
    let commentTime = '';
    if (matchedComment) {
      const activity = signalTiming(matchedComment, now);
      if (activity.tier !== 'recent_unverified') {
        const label = activity.hour24 ? '近 24 小时有新评论' : '评论时间';
        commentTime = `<small>${label} · ${esc(matchedComment.source_published_at)}</small><br>`;
      }
    }
    const colDate = s.observed_at || s.collected_at || '未知';
    const aud = s.audience_tag || '未分类人群';
    const title = signalExcerpt(s.title, 30);
    const summary = signalExcerpt(s.content, 200);
    return `
      <tr class="sig-row">
        <td class="signal-time">
          <b>#${s.id}</b><br>
          ${freshBadge(timing.tier, signalPublishedText(s), timing.hour24)}<br>
          ${commentTime}
          <small>入库 ${esc(colDate)}</small>
        </td>
        <td>
          <span class="pill">${esc(s.channel)}</span><br>
          <span class="aud-pill">${s.record_type === 'comment' ? '用户评论' : esc(aud)}</span>
        </td>
        <td><strong style="color:var(--text);font-weight:500;">${esc(s.author_or_app)}</strong><br><small style="color:var(--text-muted)">${esc(s.rating_or_price)}</small></td>
        <td>${s.is_noise ? '<span class="pill" style="color:#f87171;">已过滤噪音</span> ' : ''}<strong style="color:var(--text);font-weight:500;">${esc(title)}</strong><br><span style="color:var(--text-secondary)">${esc(summary)}</span></td>
        <td style="color:var(--text-secondary);">${s.record_type === 'comment'
          ? [s.metric_primary, ...commentTagLines(s)].filter(Boolean).map(esc).join('<br>')
          : esc(s.metric_primary) + '<br><small style="color:var(--text-muted)">' + esc(s.metric_secondary) + '</small>'}</td>
        <td>
          <button class="btn" onclick="openSnap(${s.id})">${comments.length ? `评论（${comments.length}）` : '本地快照'}</button><br>
          ${source ? `<a class="source-link" href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${source.label} ↗</a>` : ''}
        </td>
      </tr>
    `;
  }).join('');

  const tbody = document.getElementById('sigTbody');
  if (tbody) tbody.innerHTML = rowsHtml || '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:24px;">无匹配信号记录</td></tr>';
  const out = document.getElementById('signalCount');
  if (out) out.textContent = `匹配 ${total} 条 · 第 ${SIG_PAGE}/${totalPages} 页`;
  const pager = document.getElementById('sigPager');
  if (pager) {
    pager.innerHTML = `
      <span style="font-size:12px;color:var(--text-muted);">每页显示 ${SIG_PAGE_SIZE} 条（当前显示第 ${total ? start+1 : 0} ~ ${Math.min(start+SIG_PAGE_SIZE, total)} 条，共 ${total} 条）</span>
      <div style="display:flex;gap:8px;">
        <button class="btn" ${SIG_PAGE<=1 ? 'disabled' : ''} onclick="changeSigPage(-1)">← 上一页</button>
        <button class="btn" ${SIG_PAGE>=totalPages ? 'disabled' : ''} onclick="changeSigPage(1)">下一页 →</button>
      </div>
    `;
  }
}

function renderSubmitTab() {
  document.getElementById('tab-submit').innerHTML = `
    <div class="inspector">
      <div class="ins-head">
        <div>
          <span class="sec-label">内部人脉与新商机提报通道</span>
          <h2 class="ins-title">录入新方向并生成初步评估</h2>
        </div>
      </div>
      <div class="grid-2">
        <div><label class="field-lbl">1. 新项目方向名称 *</label><input id="fTitle" placeholder="例如：跨境独立站 TikTok 达人寄样自动催片工具"></div>
        <div><label class="field-lbl">2. 提报人 / 人脉来源 *</label><input id="fProposer" placeholder="例如：王总（深圳跨境卖家圈人脉）"></div>
        <div style="grid-column:span 2;"><label class="field-lbl">3. 产品一句话定义（输入什么 → 处理什么 → 产出什么）*</label><input id="fWhat" placeholder="例如：输入达人寄样单号，签收满3天自动发多语种消息催达人交挂车视频"></div>
        <div><label class="field-lbl">4. 目标客户与收费模式 *</label><input id="fBuyer" placeholder="例如：日寄样20+单的TK中小卖家，199元/月"></div>
        <div><label class="field-lbl">5. 首批客户获客渠道 *</label><input id="fChannel" placeholder="例如：深圳卖家微信群 + 小红书评论区截流"></div>
        <div><label class="field-lbl">6. 真实痛点与付费证据 *</label><input id="fEvidence" placeholder="例如：3家熟人卖家每月被白嫖样品亏上万，愿预付定金"></div>
        <div style="display:flex;gap:10px;">
          <div style="flex:1;"><label class="field-lbl">预计 MVP 工期</label><select id="fDays"><option value="5">3~7 天内</option><option value="12">1~2 周</option><option value="25">2 周以上</option></select></div>
          <div style="flex:1;"><label class="field-lbl">付费确定性</label><select id="fPaid"><option value="0">尚未确认付费</option><option value="1">已确认愿付定金或已付费</option></select></div>
        </div>
      </div>
      <div style="display:flex;gap:12px;align-items:center;">
        <button class="btn btn-primary" onclick="submitNewIdea()">计算评分并加入立项矩阵</button>
        <span id="submitMsg" style="color:var(--pos);font-size:13px;"></span>
      </div>
      <div id="cliBox" style="display:none;margin-top:16px;" class="card-cell">
        <span class="cell-k">永久同步至团队 GitHub 仓库的终端命令：</span>
        <code id="cliCmd" style="display:block;padding:10px;white-space:pre-wrap;word-break:break-all;"></code>
      </div>
    </div>
  `;
}

function submitNewIdea() {
  const title = document.getElementById('fTitle').value.trim();
  const proposer = document.getElementById('fProposer').value.trim() || '团队成员';
  const what = document.getElementById('fWhat').value.trim();
  const buyer = document.getElementById('fBuyer').value.trim() || '待定定价';
  const channel = document.getElementById('fChannel').value.trim() || '人脉私域';
  const evidence = document.getElementById('fEvidence').value.trim() || '人脉一线反馈';
  const days = parseInt(document.getElementById('fDays').value, 10);
  const paid = document.getElementById('fPaid').value === '1';
  if (!title || !what) { alert('请填写方向名称与产品定义'); return; }

  const sPay = paid ? 36 : 24;
  const sAcq = /(群|人脉|老客|小红书|闲鱼|评论)/.test(channel) ? 22 : 16;
  const sDel = days <= 7 ? 14 : (days <= 14 ? 11 : 7);
  const sComp = 8;
  const sVal = paid ? 9 : 6;
  const total = sPay + sAcq + sDel + sComp + sVal;

  const newObj = {
    code: 'TEAM-' + Date.now().toString().slice(-4),
    category_tag: `团队人脉提报 · ${proposer}`,
    title: `【人脉提报】${title}`,
    score: total,
    score_detail: `付费意愿 ${sPay}/40 · 获客截流 ${sAcq}/25 · 研发交付 ${sDel}/15 · 竞争缝隙 ${sComp}/10 · 48h测款 ${sVal}/10`,
    plain_what_to_do: what,
    workflow_steps: [`输入与痛点：${evidence}`, `处理逻辑：${days}天内基于现有脚本搭建最小闭环`, `交付变现：通过 ${channel} 按 ${buyer} 收款`],
    who_pays_and_price: buyer,
    ai_sharp_review: paid ? '人脉痛点明确且有付费意愿，重点验证能否从单点熟人复制至公域标准品。' : '当前仅口头意向，必须先收定金验证真伪。',
    plan_48h: `48小时内由 ${proposer} 向客户发去半自动样品 Demo 并收取 99~299 元测试定金。`,
    compounding: { tier: "垂直工具沉淀", snowball: "从熟人定制切入，提炼通用行业规则后转为按月订阅制工具。", skill_gain: "沉淀垂直行业工作流与自动化交付能力。" },
    biz_eval: { cost: "初期成本 <100元", profit: `按 ${buyer} 测算，毛利率 90%+`, time: `MVP ${days} 天`, team: "1.5人", landing: "熟人首单验证 -> 半自动脚本 -> 标准化SaaS", compliance: "注意数据脱敏与平台合规" },
    evidence_ids: []
  };

  let local = [];
  try { local = JSON.parse(localStorage.getItem('mr_custom_ideas') || '[]'); } catch(e) {}
  if (!Array.isArray(local)) local = [];
  local.unshift(newObj);
  try {
    localStorage.setItem('mr_custom_ideas', JSON.stringify(local));
  } catch {
    document.getElementById('submitMsg').textContent = '当前浏览器无法保存，请保留填写内容。';
    return;
  }
  selectedCode = newObj.code;
  workMode = 'focus';
  renderProjects();
  renderPersonaAndFreshness();
  document.getElementById('submitMsg').innerText = `已生成规则评分（${total}/100），方向已加到本机工作台。`;
  document.getElementById('cliBox').style.display = 'block';
  document.getElementById('cliCmd').innerText =
    `python3 scripts/radar_cli.py submit-idea --title "${title}" --proposer "${proposer}" --what "${what}" --buyer "${buyer}" --evidence "${evidence}" --channel "${channel}" --mvp-days ${days}` + (paid ? '' : ' --unpaid') + ` && python3 scripts/sync_github.py`;
}

function renderWhitepaper() {
  const wp = DATA.whitepaper || {};
  const chHtml = (wp.channels || []).map(c => `
    <div class="card-cell" style="margin-bottom:12px;">
      <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
        <strong style="color:var(--text);">${esc(c.name)}</strong>
        <span class="pill">${esc(c.type)}</span>
      </div>
      <div class="cell-v" style="margin-bottom:4px;"><strong style="color:var(--text-secondary);">采集量：</strong>${esc(c.count_info)}</div>
      <div class="cell-v" style="margin-bottom:4px;"><strong style="color:var(--text-secondary);">实现机制：</strong>${esc(c.how_it_works)}</div>
      <div class="cell-v" style="margin-bottom:4px;"><strong style="color:var(--text-secondary);">边界限制：</strong>${esc(c.limitations)}</div>
      <div class="cell-v"><strong style="color:var(--text-secondary);">扩展方式：</strong><code>${esc(c.how_to_extend)}</code></div>
    </div>
  `).join('');

  const guideHtml = (wp.csv_guides || []).map(g => `
    <div class="card-cell" style="margin-bottom:12px;">
      <span class="cell-k" style="color:var(--text);">${esc(g.platform)}</span>
      ${(g.steps || []).map(st => `<div class="cell-v" style="margin-bottom:4px;">${esc(st)}</div>`).join('')}
    </div>
  `).join('');

  document.getElementById('tab-whitepaper').innerHTML = `
    <div class="inspector" style="margin-bottom:18px;">
      <div class="ins-head" style="margin-bottom:14px;padding-bottom:12px;">
        <div>
          <span class="sec-label">团队成员通用采集入口（兼容 macOS / Windows / Linux）</span>
          <h2 class="ins-title">其他成员如何在自己电脑上抓数据并安全合入团队总库</h2>
        </div>
        <span class="pill pill-s">自动去重合并 · 互不覆盖</span>
      </div>
      <div class="grid-3" style="margin-bottom:16px;">
        <div class="card-cell">
          <span class="cell-k">方式一：零命令双击启动（推荐运营/市场同事）</span>
          <div class="cell-v">克隆仓库后，Mac 用户直接双击根目录 <code>Mac一键采集向导.command</code>，Windows 用户双击 <code>Windows一键采集向导.bat</code>，按数字菜单 [1]~[5] 输入关键词即可完成扫码、抓包与合并上传。</div>
        </div>
        <div class="card-cell">
          <span class="cell-k">方式二：修改共享词库 (config/watch_keywords.json)</span>
          <div class="cell-v">无需改 Python 代码，任何成员直接在 <code>config/watch_keywords.json</code> 中添加要长期监控的赛道词，所有采集脚本自动读取。</div>
        </div>
        <div class="card-cell">
          <span class="cell-k">多人数据防覆盖保障</span>
          <div class="cell-v">各自扫码的 Cookie 仅保存在本机 <code>.browser_profile/</code>（不上传 Git）。执行 <code>sync_github.py</code> 时会先自动拉取远端最新信号做无损并集合并，不会冲掉队友抓的数据。</div>
        </div>
      </div>
      <div class="card-cell">
        <span class="cell-k" style="color:var(--text);">交互式采集命令生成器（勾选平台并输入你想调研的词，复制到仓库终端运行即可抓取并同步全队）</span>
        <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:10px 0;">
          <input id="cgKw" style="max-width:380px;" value="microduck,桌面宠物,装修报价单审核" oninput="buildCollectCmd()" placeholder="多个关键词用逗号隔开">
          <label style="display:inline-flex;align-items:center;gap:5px;font-size:12.5px;width:auto;"><input type="checkbox" id="cgXy" checked onchange="buildCollectCmd()" style="width:auto;"> 闲鱼在售价格与想要数</label>
          <span style="font-size:11.5px;color:#fca5a5;">(注：小红书反AI浏览风控极严，已默认熔断登录态自动抓取以保护个人账号)</span>
          <label style="display:inline-flex;align-items:center;gap:5px;font-size:12.5px;width:auto;"><input type="checkbox" id="cgCm" onchange="buildCollectCmd()" style="width:auto;"> 蝉妈妈抖音榜</label>
        </div>
        <div style="font-size:11.5px;color:var(--text-muted);margin-bottom:6px;">首次运行前先执行一次 <code>python3 scripts/auto_browser_collector.py --login</code> 扫码保存你自己的登录态：</div>
        <code id="cgOut" style="display:block;padding:10px;white-space:pre-wrap;word-break:break-all;">python3 scripts/auto_browser_collector.py --collect --targets xianyu --keywords "microduck,桌面宠物,装修报价单审核" && python3 scripts/sync_github.py</code>
      </div>
    </div>
    <div class="inspector">
      <span class="sec-label">数据采集透明说明</span>
      ${chHtml}
      <span class="sec-label" style="margin-top:24px;">外部平台自动化抓包与导表操作指南</span>
      ${guideHtml}
    </div>
  `;
}

function renderRoadmapAndArchive() {
  const wp = DATA.whitepaper || {};
  const archives = DATA.archives || [];
  const archiveRows = archives.map(a => `
    <tr><td class="mono">${esc(a.date)}</td><td class="mono">${esc(String(a.total_signals ?? '—'))}</td><td class="mono">${esc(String(a.valid_signals ?? '—'))}</td><td class="mono">${esc(String(a.noise_signals ?? '—'))}</td></tr>
  `).join('');
  const rmHtml = (wp.roadmap || []).map(r => `
    <div class="card-cell" style="margin-bottom:12px;">
      <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
        <strong style="color:var(--text);">${esc(r.phase)} — ${esc(r.title)}</strong>
        <span class="pill">${esc(r.owner)}</span>
      </div>
      <div class="cell-v" style="white-space:pre-line;">${esc(r.details)}</div>
    </div>
  `).join('');

  const oldHtml = (DATA.existing_ideas || []).map(o => `
    <div class="card-cell" style="margin-bottom:12px;">
      <strong style="color:var(--text);display:block;margin-bottom:6px;">${esc(o.name)}</strong>
      <div class="cell-v" style="margin-bottom:4px;"><strong>原设想：</strong>${esc(o.original_plan)}</div>
      <div class="cell-v" style="margin-bottom:4px;"><strong>受阻原因：</strong>${esc(o.blocker)}</div>
      <div class="cell-v" style="margin-bottom:4px;"><strong>AI 锐评：</strong>${esc(o.ai_review)}</div>
      <div class="cell-v"><strong>改造方向：</strong>${esc(o.pivot_to)}</div>
    </div>
  `).join('');


  const strategyBlueprint = `
    <div class="blueprint-hero">
      <div class="research-kicker"><span></span> 团队战略共识 · 基于 1,300+ 条真实市场交易与痛点信号</div>
      <h2>轻资产跑通自动化现金流，集中技术火力打穿「AI 灵魂宠物」软硬一体主线</h2>
      <p>没有外部资金与资源背书的技术团队，最忌讳走两个极端：一是长期接零散低价定制沦为外包作坊，没有复用资产；二是一上来重投入开模或做超长周期大项目，未见营收先耗尽心气。我们的路径非常清晰——<strong>短期用 1~2 周能闭环的自动化工具跑通正向现金流，覆盖算力与硬件研发开销；中长期将团队最擅长的 AI Agent、强化学习与多模态能力沉淀进同一套「灵魂大脑」，从 Steam 桌面陪伴游戏一路打通到具身桌面机器人。</strong></p>
    </div>

    <div class="inspector" style="margin-bottom:18px;">
      <span class="sec-label">第一条线 · 短期现金流抓手（第 1 ~ 4 周：先收款、自动化交付、零账期）</span>
      <div class="summary-lead" style="margin-bottom:14px;">
        目标：不做需要求着客户付尾款的重度定制，从已验证有高频付费意愿的切口里选 1~2 把快刀，两周内跑通首笔公域陌生人订单，建立稳定的日常现金流。
      </div>
      <div class="grid-3" style="margin-bottom:0;">
        <div class="card-cell">
          <span class="cell-k" style="color:var(--text);">候选抓手 A · 免 Claude 知识动画生成工坊</span>
          <div class="cell-v">B 站相关教程近万收藏（收藏率超 11%），大量老师与创作者卡在海外账号封禁与环境报错。用预置 Remotion 组件模板 + DeepSeek-V4.1-Flash（单条成本不到 1 分钱），从闲鱼 49 元代做平滑演进至 69 元/月在线工具。</div>
        </div>
        <div class="card-cell">
          <span class="cell-k" style="color:var(--text);">候选抓手 B · 2 张图带货裂变与违禁词清洗台</span>
          <div class="cell-v">切入抖音/小红书图文带货日销破十万但美工软件频繁扣费报错、达人极怕违禁词封号的刚需。导入 1 张原图 10 秒生成 20 套过审痛点主图，按 39.9 元/月或 168 元/年订阅变现。</div>
        </div>
        <div class="card-cell">
          <span class="cell-k" style="color:var(--text);">候选抓手 C · 现有代码直接变现（LawFlow / 规划表）</span>
          <div class="cell-v">将现有 LawFlow 接上动态人物关系图，向急需案源的青年律师提供判决书转 60 秒图解获客视频（99元体验/299元包月）；将教材规划代码转为闲鱼 19.9 元考研精确到页打卡 PDF 自动发货（闲鱼同类链接超 700~5000 人想要）。</div>
        </div>
      </div>
    </div>

    <div class="inspector" style="margin-bottom:18px;">
      <span class="sec-label">第二条线 · 长期高壁垒主线（「AI 灵魂宠物」软硬一体三阶跃迁）</span>
      <div class="summary-lead" style="margin-bottom:14px;">
        为什么这是能做出长期复利与高天花板的主战场？数据同时指明了两个信号：软件侧，Steam 桌面底部挂机桌宠免国内版号、全球美金结算，同类桌宠插件近 30 天下载达 47 万次；硬件侧，开源双足小鸭子 Microduck 闲鱼代购标价 ¥2,888 且缺货仍有 576 人想要，国内 DIY 成本虽降至 1,500 元内，但全网复刻者普遍卡在「仿真迁真机步态崩坏（486赞痛点）+ 没有交互灵魂」。<strong>纯游戏小团队造不出强化学习双足真机，华强北硬件厂写不出有记忆温度的 AI 灵魂大脑——把这两端打通，就是别人抄不走的壁垒。</strong>
      </div>
      <div class="stage-track">
        <div class="stage-card blue">
          <span class="stage-kicker">STAGE 01 · 第 1 ~ 2 个月（纯软破局与攒粉）</span>
          <h4>Steam 桌面挂机游戏《AI 灵魂桌宠》</h4>
          <p>零硬件库存起步。复用大肥鱼设定与 DeepSeek-V4.1-Flash 状态机，用 Godot 做驻留屏幕底部的透明陪伴小鸭子（感知工作窗口吐槽陪伴、换装养成）。交 100 美元押金免版号上架 Steam 全球收买断美金（$3.99 + 外观 DLC），快速跑通收入并沉淀数万名喜欢这只小鸭子的核心玩家社群。</p>
        </div>
        <div class="stage-card">
          <span class="stage-kicker">STAGE 02 · 第 2 ~ 5 个月（高毛利固件与高校采购）</span>
          <h4>Microduck「灵魂大脑」固件与高校实训箱</h4>
          <p>不开重资产模具，采购 1,500 元散件攻克「廉价舵机 Sim2Real 一键校准 + 多模态语音情绪动作联动」。向全网上万名手搓复刻玩家售卖 199~399 元免配置烧录镜像与中控台；同时对接全国高职与高校新建具身智能实训室需求，售卖 3,980~6,800 元/套的图形化 RL 训练与交互教学箱。</p>
        </div>
        <div class="stage-card gold">
          <span class="stage-kicker">STAGE 03 · 半年以上（软硬记忆互通与系统授权）</span>
          <h4>屏幕宠物一键同步实体躯壳 · 具身伴侣 OS</h4>
          <p>打通杀手级体验：玩家在电脑 Steam 桌面上养熟、拥有专属记忆和口头禅的那只电子小鸭子，可一键导出记忆档案灌入桌上的实体双足小鸭子中走到现实陪伴。最终沉淀跨构型的《桌面具身伴侣 SDK》，向 AI 玩具与硬件厂商按台收取软件 License 授权费或开启融资。</p>
        </div>
      </div>

      <span class="sec-label">团队协同与执行原则</span>
      <div class="grid-3" style="margin-bottom:0;">
        <div class="card-cell"><span class="cell-k">1. 工具链拉齐（10倍研发效率）</span><div class="cell-v">全员统一使用 <code>Codex CLI + DeepSeek Harness</code>（主力模型 <code>DeepSeek-V4.1-Flash</code>），共享仓库 Skill 与规则模板，把精力聚焦在核心体验而非重复脚手架上。</div></div>
        <div class="card-cell"><span class="cell-k">2. 真实信号与 48h 付款验证</span><div class="cell-v">拒绝闭门争论。新想法先通过 Market Radar 核查真实差评与闲鱼想要数，再用 48 小时样片/商品卡测试陌生买家是否真掏定金，成则扩投，不成则果断止损。</div></div>
        <div class="card-cell"><span class="cell-k">3. 代码与数据资产处处复用</span><div class="cell-v">无论是知识动画的分镜引擎，还是桌面挂机游戏与实体机器人的宠物性格记忆引擎，每一行代码都围绕长期可复用的核心资产构建，让团队成员与产品壁垒同步成长。</div></div>
      </div>
    </div>
  `;

  document.getElementById('tab-roadmap').innerHTML = strategyBlueprint + `
    <section class="desk-panel matrix-panel archive-panel">
      <div class="panel-head"><h3>数据批次归档</h3><span class="panel-count">${archives.length} 期</span></div>
      ${archives.length ? `<div class="table-wrap" role="region" aria-label="历史批次明细" tabindex="0">
        <table><thead><tr><th>日期</th><th>采集总数</th><th>有效信号</th><th>已过滤</th></tr></thead><tbody>${archiveRows}</tbody></table>
      </div>` : '<p class="panel-empty">暂无采集批次归档。</p>'}
    </section>
    <div class="inspector">
      <div class="roadmap-title"><span class="sec-label">团队发展规划与迭代 Roadmap</span><a href="https://github.com/donghyq/market-radar/issues/2" target="_blank" rel="noopener noreferrer" class="btn">查看 GitHub Issue #2 ↗</a></div>
      ${rmHtml}
      <span class="sec-label" style="margin-top:24px;">团队早期 4 个既有想法的复盘归档</span>
      ${oldHtml}
    </div>
  `;
}

function sourceLink(value) {
  try {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol)) return null;
    const home = url.pathname === '/' && !url.search && !url.hash;
    const listing = url.hostname === 'apps.apple.com';
    return {url: url.href, label: home ? '平台首页' : listing ? '应用商店页面' : '来源链接',
      hint: ''};
  } catch { return null; }
}

function postKey(value) {
  const source = sourceLink(value);
  if (!source) return '';
  const url = new URL(source.url);
  if (/^(?:(?:www|m)\.)?bilibili\.com$/.test(url.hostname)) {
    const video = url.pathname.match(/^\/video\/(BV[A-Za-z0-9]+|av\d+)\/?$/);
    if (video) return 'bilibili:' + video[1];
  }
  if (/^(?:www\.)?xiaohongshu\.com$/.test(url.hostname)) {
    const note = url.pathname.match(/^\/(?:explore|discovery\/item)\/([\da-f]{24})\/?$/i);
    if (note) return 'xiaohongshu:' + note[1].toLowerCase();
  }
  if (url.hostname === 'apps.apple.com') {
    const app = url.pathname.match(/\/id(\d+)\/?$/);
    if (app) return 'appstore:' + app[1];
  }
  return url.pathname === '/' ? '' : url.href;
}

function indexSignalComments(signals) {
  const posts = new Map();
  const commentsByPost = new Map();
  const postByComment = new Map();
  for (const post of signals) {
    if (post.record_type === 'comment' || /^(?:B站评论区痛点|AppStore中国区差评)/.test(post.channel)) continue;
    const key = postKey(post.source_url);
    if (!key) continue;
    const previous = posts.get(key);
    if (previous && key.startsWith('bilibili:')) {
      if (post.id < previous.id) posts.set(key, post);
    } else {
      posts.set(key, posts.has(key) ? null : post);
    }
  }
  for (const comment of signals) {
    if (comment.record_type !== 'comment') continue;
    const post = posts.get(postKey(comment.parent_url));
    if (!post) continue;
    postByComment.set(comment.id, post);
    if (!commentsByPost.has(post.id)) commentsByPost.set(post.id, []);
    commentsByPost.get(post.id).push(comment);
  }
  return {commentsByPost, postByComment};
}

function evidenceLink(source, caption) {
  const link = document.createElement('a');
  link.href = source.url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.textContent = caption + ' ↗';
  return link;
}

const COMMENT_LABEL_NAMES = {age: '年龄段', ip_location: 'IP 属地', occupation: '职业', interests: '喜好'};

function commentTagLines(s, includeSource = false) {
  return Object.entries(COMMENT_LABEL_NAMES).map(([key, name]) => {
    const tag = s.profile_tags[key];
    const evidence = includeSource && tag.source ? `（${tag.source}${tag.quote ? ' · ' + tag.quote : ''}）` : '';
    return `${name}：${tag.value}${evidence}`;
  });
}

function appendSnapshotComments(body, comments) {
  if (!comments?.length) return;
  const section = document.createElement('section');
  const heading = document.createElement('h3');
  heading.textContent = `评论（${comments.length}）`;
  section.append(heading);
  const now = Date.now();
  const ordered = comments.map(comment => ({comment, order: signalTiming(comment, now).order}));
  ordered.sort((a, b) => b.order - a.order || b.comment.id - a.comment.id);
  for (const {comment} of ordered) {
    const article = document.createElement('article');
    const meta = document.createElement('strong');
    meta.textContent = [signalPublishedText(comment), comment.author_or_app, comment.metric_primary].filter(Boolean).join(' · ');
    const content = document.createElement('div');
    content.textContent = [comment.content, `态度：${comment.stance}`, ...commentTagLines(comment, true)].join('\n');
    article.append(document.createElement('hr'), meta, content);
    const source = sourceLink(comment.source_url);
    if (source && source.url !== sourceLink(comment.parent_url)?.url) {
      article.append(evidenceLink(source, '查看原评论'));
    }
    const profile = sourceLink(comment.author_profile_url);
    if (profile) {
      if (article.lastElementChild?.tagName === 'A') article.append(' · ');
      article.append(evidenceLink(profile, '用户主页'));
    }
    section.append(article);
  }
  body.append(section);
}

function openSnap(id) {
  const s = SIG_MAP[id];
  if (!s) return;
  document.getElementById('mTitle').textContent = `证据 #${s.id} — ${cleanText(s.title)}`;
  const isComment = s.record_type === 'comment';
  const timeLabel = isComment ? '评论时间' : s.published_time_source === 'legacy_archive_date' ? '发帖日期' : '源站时间';
  const audience = isComment ? '' : ` | 人群画像：${cleanText(s.audience_tag || '通用')}`;
  document.getElementById('mMeta').textContent = `${timeLabel}：${signalPublishedText(s)} | 采集入库：${s.observed_at || cleanText(s.collected_at)}${audience} | 渠道：${cleanText(s.channel)}`;
  const body = document.getElementById('mBody');
  body.textContent = [
    s.is_noise ? `已过滤：${cleanText(s.noise_reason) || '未记录原因'}` : '',
    '[采集时保存的内容]',
    String(s.content || '').trim(),
    '',
    isComment ? '[用户标签]' : '[指标与分类]',
    [s.metric_primary, s.metric_secondary, s.rating_or_price].filter(Boolean).map(cleanText).join(' · '),
    [s.category, s.audience_tag, s.persona_note].filter(Boolean).map(cleanText).join(' · '),
    ...(isComment ? [...commentTagLines(s, true), `态度：${s.stance}`, `意图：${s.intents.join('、') || '不明确'}`] : []),
  ].filter((line, i) => i !== 0 || line).join('\n');
  appendSnapshotComments(body, commentsByPost.get(s.id));
  body.scrollTop = 0;
  const source = sourceLink(s.source_url);
  const parent = isComment ? sourceLink(s.parent_url) : null;
  const link = document.getElementById('mLink');
  link.hidden = !source;
  if (source) {
    link.href = source.url;
    link.textContent = (isComment ? (parent?.url === source.url ? '原帖' : '查看原评论') : source.label) + ' ↗';
  } else link.removeAttribute('href');
  const hint = document.getElementById('mHint');
  hint.replaceChildren();
  if (parent && parent.url !== source?.url) {
    hint.append(evidenceLink(parent, '原帖'));
  }
  const profile = isComment && sourceLink(s.author_profile_url);
  if (profile) {
    if (hint.hasChildNodes()) hint.append(' · ');
    hint.append(evidenceLink(profile, '用户主页'));
  }
  document.getElementById('snapModal').showModal();
}

function renderTechRadar() {
  const items = DATA.tech_radar || [];
  const cntEl = document.getElementById("lblTechCnt");
  if (cntEl) cntEl.innerText = items.length;
  const rows = items.map((it, i) => `
    <tr>
      <td width="50" style="font-family:monospace;color:var(--text-muted);">${String(i+1).padStart(2,"0")}</td>
      <td width="190">
        <a href="${esc(sourceLink(it.url)?.url || '')}" target="_blank" rel="noopener noreferrer" style="color:var(--accent);font-weight:600;text-decoration:none;">${esc(it.name)} ↗</a>
        <div style="margin-top:4px;"><span class="pill">${esc(it.category)}</span> <small style="color:var(--text-muted)">${esc(it.language)}</small></div>
      </td>
      <td width="110" style="font-variant-numeric:tabular-nums;">
        <strong style="color:var(--text);">${esc(String(it.stars ?? '—'))}</strong> <small style="color:var(--text-muted)">stars/pts</small><br>
        <small style="color:var(--text-muted)">${esc(it.updated_at)}</small>
      </td>
      <td style="color:var(--text-secondary);">${esc(it.description)}</td>
      <td width="270" style="color:var(--text-secondary);">${esc(it.internal_use)}</td>
      <td width="270" style="color:var(--text-secondary);">${esc(it.commercial_idea)}</td>
    </tr>
  `).join("");

  document.getElementById("tab-tech").innerHTML = `
    <div class="inspector" style="margin-bottom:16px;padding:16px 20px;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div>
          <span class="sec-label" style="margin-bottom:4px;">专项 2 · GitHub Trending 与前沿技术雷达</span>
          <div style="color:var(--text-secondary);font-size:13px;">每日自动通过 GitHub Search API 与 Hacker News 抓取高星开源工具，按“向内能否接入团队 Codex/DeepSeek 提效”与“向外能否本土化变现”双维度筛选。更新命令：<code>python3 scripts/tech_radar.py</code></div>
        </div>
      </div>
    </div>
    <div class="table-wrap tech-table" role="region" aria-label="技术雷达项目" tabindex="0">
      <table>
        <thead>
          <tr>
            <th>序号</th>
            <th>开源项目 / 工具</th>
            <th>热度与更新时间</th>
            <th>项目功能简介</th>
            <th>向内提效（接入团队 Codex / DeepSeek）</th>
            <th>向外变现（国内产品化思路）</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderToolkit() {
  document.getElementById("tab-toolkit").innerHTML = `
    <div class="inspector">
      <div class="ins-head">
        <div>
          <span class="sec-label">专项 3 · 团队统一开发与协作工具栈</span>
          <h2 class="ins-title">标准工具栈：Codex CLI + DeepSeek Harness（基于 DeepSeek-V4.1-Flash）</h2>
        </div>
        <span class="pill pill-s">已内置 team-toolkit/ 一键初始化包</span>
      </div>

      <div class="summary-lead">
        团队不再耗费精力横向对比多款 IDE 与插件，直接统一锁定 <strong>Codex CLI + DeepSeek Harness</strong> 作为标准研发与自动化底座。仓库已内置 <code>team-toolkit/</code> 目录，任何成员拉取仓库后执行一行命令即可在 3 分钟内对齐全部配置与共享 Skill。
      </div>

      <span class="sec-label">01 / 新成员 3 分钟一键对齐环境</span>
      <div class="card-cell" style="margin-bottom:20px;">
        <div class="cell-v" style="margin-bottom:8px;">在终端克隆本仓库后直接运行初始化脚本（自动检查环境、安装共享 <code>market-radar</code> Skill 到 <code>~/.codex/skills/</code> 并生成模型配置模板）：</div>
        <code style="display:block;padding:12px;">git clone https://github.com/donghyq/market-radar.git && cd market-radar && bash team-toolkit/init_team_env.sh</code>
      </div>

      <span class="sec-label">02 / 团队统一配置与协作约定（位于 team-toolkit/ 目录）</span>
      <div class="grid-3">
        <div class="card-cell">
          <span class="cell-k">1. 统一项目规则文件 (team-toolkit/AGENTS.md)</span>
          <div class="cell-v">开启任何新项目时，将 <code>team-toolkit/AGENTS.md</code> 复制到新仓库根目录，自动约束 Codex 与 DeepSeek Harness 遵循“先读后写、小步验证、JSONL 无冲突存储、平实中文文档”规范。</div>
        </div>
        <div class="card-cell">
          <span class="cell-k">2. 主力模型与 Prefix Caching 降本约定</span>
          <div class="cell-v">日常高频任务（文本清洗、结构化 JSON 提取、Remotion 动画分镜生成、代码辅助）统一调用 <code>deepseek-v4.1-flash</code>；固定系统提示词与背景置于最前以命中前缀缓存，成本降低 80%。</div>
        </div>
        <div class="card-cell">
          <span class="cell-k">3. 共享 Skill 与自动化脚本接力</span>
          <div class="cell-v">团队沉淀的通用能力统一封装为标准 Skill（含 <code>SKILL.md</code> 与无外部依赖的 <code>scripts/*.py</code>），通过 <code>init_team_env.sh</code> 一键分发至全员本地。</div>
        </div>
      </div>
    </div>
  `;
}

function switchTab(id, btn) {
  ['tab-projects','tab-persona','tab-signals','tab-tech','tab-toolkit','tab-submit','tab-whitepaper','tab-roadmap'].forEach(t => {
    document.getElementById(t).style.display = (t === id) ? 'block' : 'none';
  });
  document.querySelectorAll('.nav-btn').forEach(b => {
    b.classList.toggle('active', b === btn);
    if (b === btn) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  });
}

function signalMatches(s, query) {
  const tags = s.profile_tags ? commentTagLines(s).join(' ') : '';
  return `${s.id} ${s.title} ${s.content} ${s.author_or_app} ${s.audience_tag} ${tags}`.toLowerCase().includes(query);
}

function filterRows() {
  const sigs = DATA.signals || [];
  const q = (document.getElementById('qInput')?.value || '').trim().toLowerCase();
  const id = q.match(/^#(-?\d+)$/)?.[1];
  const ch = document.getElementById('chSelect')?.value || '';
  const aud = document.getElementById('audSelect')?.value || '';
  const tMode = document.getElementById('timeSelect')?.value || '7d';
  const sortMode = document.getElementById('sortSelect')?.value || 'post';
  const noise = document.getElementById('noiseSelect')?.value || 'valid';
  const recordType = document.getElementById('recordSelect')?.value || '';
  const now = Date.now();
  const timing = new Map(sigs.map(s => [s.id, signalTiming(s, now)]));
  const noiseMatches = s => noise === 'all' || Boolean(s.is_noise) === (noise === 'noise');
  const displayRow = s => {
    const post = !recordType && !id ? postByComment.get(s.id) : null;
    return post && noiseMatches(post) ? post : s;
  };

  const matches = sigs.filter(s => {
    const {tier: f, hour24} = timing.get(s.id);
    let timeOk = true;
    if (tMode === 'active180') timeOk = !['stale_archive', 'recent_unverified'].includes(f);
    else if (tMode === '24h') timeOk = hour24;
    else if (tMode === '7d') timeOk = (f === '7d_hot');
    else if (tMode === '30d') timeOk = (f === '7d_hot' || f === '30d_active');
    else if (tMode === 'stale_only') timeOk = (f === 'stale_archive');
    else if (tMode === 'unknown') timeOk = (f === 'recent_unverified');
    if (!timeOk && !id) return false;
    if (!noiseMatches(s)) return false;
    const post = displayRow(s);
    if (ch && cleanText(s.channel) !== ch && cleanText(post.channel) !== ch) return false;
    if (recordType && (s.record_type || 'signal') !== recordType) return false;
    if (aud && cleanText(s.audience_tag) !== aud && cleanText(post.audience_tag) !== aud) return false;
    if (q) {
      if (id) return String(s.id) === id;
      return signalMatches(s, q) || (post !== s && signalMatches(post, q));
    }
    return true;
  });
  const rows = new Map();
  for (const match of matches) {
    const signal = displayRow(match);
    if (!rows.has(signal.id)) rows.set(signal.id, {signal, matchedComment: null});
    const row = rows.get(signal.id);
    if (match !== signal && (!row.matchedComment || timing.get(match.id).order > timing.get(row.matchedComment.id).order)) {
      row.matchedComment = match;
    }
  }
  const sortTime = ({signal, matchedComment}) => {
    const commentTime = timing.get(matchedComment?.id)?.order;
    return sortMode === 'comment' && Number.isFinite(commentTime) ? commentTime : timing.get(signal.id).order;
  };
  FILTERED_SIGS = [...rows.values()].sort((a, b) => sortTime(b) - sortTime(a) || a.signal.id - b.signal.id);
  renderSigPage();
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('lblUpdated').textContent = DATA.updated_at || '未记录';
  document.getElementById('lblBatches').textContent = DATA.archives?.[0]?.date || '暂无';
  renderProjects();
  renderPersonaAndFreshness();
  renderSignals();
  renderTechRadar();
  renderToolkit();
  renderSubmitTab();
  renderWhitepaper();
  renderRoadmapAndArchive();
});
