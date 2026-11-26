const SHORT_TITLES = {
  'STRAT-02': 'Steam「AI灵魂桌宠」挂机游戏',
  'STRAT-01': '具身宠物「灵魂大脑」· Microduck',
  'AUTO-01': '2张图爆单裂变 · 违禁词防封台',
  'PROJ-01': '免Claude · 开智小曲动画工坊',
  'TEAM-FE4500': 'TK达人寄样防白嫖 · 自动催片',
  'AUTO-02': '离线防泄密 · 标书废标红线审查',
  'PROJ-02': '判决书转60秒律所案源图解视频',
  'PROJ-03': '考研精确到页打卡 · 教培续费战报',
  'AUTO-03': '门窗定制30秒防飞单报价器',
  'PROJ-04': '反续费套路 · 离线语音提词粗剪',
  'PROJ-05': '一晚3毛钱 · 大肥鱼弹幕整活包',
};
const HERO_TITLES = {
  'STRAT-02': 'Steam 桌面挂机游戏「AI 灵魂桌宠 / 摸鱼小鸭牧场」（免版号全球发行 · 与 Microduck 软硬联动）',
  'STRAT-01': '具身 AI 宠物「灵魂大脑」固件中控 + 步态校准 + 高校实训套件（基于 Microduck）',
  'AUTO-01': '抖音/小红书「2张图带货爆款裂变 + 违禁词防封清洗」批量工作台',
  'PROJ-01': '国内免 Claude「开智小曲 / Remotion 知识动画」一键生成工坊',
  'TEAM-FE4500': 'TikTok 跨境卖家「达人寄样防白嫖自动催片 + 挂车监控」桌面助手',
  'AUTO-02': '工程与政企投标「离线防泄密 · 标书废标红线与串标雷区审查器」',
  'PROJ-02': '律所/财税高客单 IP「枯燥判决书 → 60秒动态图解获客视频」生成器',
  'PROJ-03': '一鱼两吃：闲鱼考研精确到页打卡表 + 教培机构「家长群续费战报」',
  'AUTO-03': '门窗与全屋定制老板「手机点选30秒出图 · 防同行比价飞单报价器」',
  'PROJ-04': '反自动续费套路 · 29.9元买断「离线语音同步悬浮提词 + 气口粗剪器」',
  'PROJ-05': '一晚仅耗3毛钱 · DeepSeek-V4.1-Flash「大肥鱼弹幕整活直播整合包」',
};
function heroTitle(p) {
  return HERO_TITLES[p.code] || cleanText(p.title).replace(/^(?:【[^】]+】|项目\s*\d+[：:])\s*/, "");
}
const RESEARCH_QUESTIONS = {
  'STRAT-02': '20 秒「会偷看你写代码并毒舌吐槽的桌面小鸭子」实机短视频，能否在 2 周内攒够 3,000 个 Steam 愿望单？',
  'STRAT-01': '手搓复刻玩家与高校实验室是否愿为「免配环境 Sim2Real 校准固件 + DeepSeek 情绪大脑」付费？',
  'AUTO-01': '带货创作者是否愿意为批量出图付费？',
  'PROJ-01': '收藏教程、遇到配置困难的人，是否愿意为成片付费？',
  'TEAM-FE4500': '熟人客户是否愿意为寄样跟进付定金？需求能否复制到其他卖家？',
  'AUTO-02': '投标团队是否愿意为检查付费，并愿意提供可用于验证的样本？',
  'PROJ-02': '律所是否愿意为样片付费，审核耗时会不会抵消制作效率？',
  'PROJ-03': '先验证哪类客户会付款：备考用户，还是需要续费沟通的教培机构？',
  'AUTO-03': '门窗商家是否会用快速报价替代现有流程，并为此付费？',
  'PROJ-04': '对扣费和操作不满的用户，是否愿意为离线买断版付费？',
  'PROJ-05': '直播创作者是否愿意为互动效果和低运行成本付费？',
};
const BRIEFS = {
  'STRAT-02': '避开国内小游戏版号限制与重度独游长周期风险，复用「灵魂大脑」状态机做一款驻留屏幕底部的 Steam 挂机陪伴桌宠，先赚全球买断美金，再与实体 Microduck 同步记忆。',
  'STRAT-01': '趁双足机器人硬件成本降至 1500 元左右、复刻人数激增，不做低毛利外壳加工，专注为机械躯壳装上「灵魂大脑」（多模态情绪交互固件 + 真机步态校准 + 高校实训套件）。',
  'AUTO-01': '帮图文带货创作者用一张商品图批量生成素材，并提示需要人工复核的文案。',
  'PROJ-01': '把讲义、课程笔记或科普文稿转换成带配音的知识动画，省掉手写分镜和配置环境的时间。',
  'TEAM-FE4500': '让跨境卖家按寄样状态跟进达人，及时发现未交片或未挂商品链接的订单。',
  'AUTO-02': '在本地检查标书的易漏项，帮助投标团队在提交前复核格式和约束。',
  'PROJ-02': '把判决书或政策材料做成短视频样片，帮助律所和财税创作者降低图解制作成本。',
  'PROJ-03': '用同一套规划能力生成备考打卡表，或生成教培机构发给家长的成长报告。',
  'AUTO-03': '让门窗和定制柜商家在手机上选择规格，向顾客发出可追踪的报价单。',
  'PROJ-04': '把语音跟随提词和停顿粗剪放进同一款离线工具，用买断价格验证需求。',
  'PROJ-05': '让直播创作者用本地规则处理常见弹幕，减少模型调用并保留互动效果。',
};
const FACTORS = [
  ['付费意愿', '付费意愿'], ['获客截流', '获客渠道'], ['研发交付', '研发交付'],
  ['竞争缝隙', '竞争空间'], ['48h测款', '快速验证'],
];
const STAGES = [
  ['planned', '待验证'], ['running', '验证中'], ['pass', '已达到条件'],
  ['fail', '未达到条件'], ['unclear', '结果不充分'],
];
const VALIDATION_KEY = 'mr_validation_v1';

let selectedCode = new URLSearchParams(location.hash.slice(1)).get('project') || '';
let workMode = localStorage.getItem('mr_work_mode') || 'focus';
let savedReports = readReports();

function readReports() {
  try {
    const data = JSON.parse(localStorage.getItem(VALIDATION_KEY) || '{}');
    return data && typeof data === 'object' && !Array.isArray(data) ? data : {};
  } catch { return {}; }
}

function shortTitle(p) {
  if (p.code?.startsWith('RADAR-')) return cleanText(p.title).replace('[自动发现候选] 基于近期飙升开源项目 ', '新物种候选 · ').replace(' 的本土化工具/服务封装', '');
  return SHORT_TITLES[p.code] || cleanText(p.title).replace(/^(?:【[^】]+】|项目\s*\d+[：:])\s*/, '');
}

function evidenceFor(p) {
  return [...new Set(p.evidence_ids || [])].map(id => SIG_MAP[id]).filter(Boolean);
}

function sourceLabel(p) {
  return cleanText(p.category_tag).split('·')[0].trim() || '来源未标注';
}

function factorValues(p) {
  const detail = cleanText(p.score_detail);
  return FACTORS.map(([source, label]) => {
    const m = detail.match(new RegExp(source + '\\s*(\\d+)\\s*/\\s*(\\d+)'));
    if (!m || +m[2] <= 0 || +m[1] > +m[2]) return { label };
    return { label, score: +m[1], max: +m[2] };
  });
}

function stageName(key) {
  return STAGES.find(([id]) => id === key)?.[1] || STAGES[0][1];
}

function scoreText(p) {
  return Number.isFinite(p.score) ? String(p.score) : '—';
}

function renderProjects() {
  const list = getAllProjects();
  const signals = DATA.signals || [];
  const valid = signals.filter(s => !s.is_noise).length;
  if (!list.some(p => p.code === selectedCode)) selectedCode = list[0]?.code || '';
  const archived = (DATA.archives || []).length;
  document.getElementById('tab-projects').innerHTML = `
    <div class="research-heading">
      <div>
        <div class="research-kicker"><span aria-hidden="true"></span> 商机研究 / 本期观察</div>
        <h2>市场机会工作台<span>.</span></h2>
        <p>从市场信号出发，找到下一个值得验证的方向。</p>
      </div>
      <div class="mode-select" aria-label="查看方式">
        <button type="button" class="btn" id="quickMode" aria-pressed="${workMode === 'quick'}" onclick="setWorkMode('quick')">速读概览</button>
        <button type="button" class="btn" id="focusMode" aria-pressed="${workMode === 'focus'}" onclick="setWorkMode('focus')">完整深度</button>
        <button type="button" class="btn" id="matrixMode" aria-pressed="${workMode === 'matrix'}" onclick="setWorkMode('matrix')">横向比较</button>
      </div>
    </div>
    <div class="research-stats" aria-label="本期数据概况">
      <div><span>候选方向</span><strong id="kpiProjects">${list.length}</strong><small>包含本机提报</small></div>
      <div><span>有效信号</span><strong>${valid}</strong><small>采集 ${signals.length} · 过滤 ${signals.length - valid}</small></div>
      <div><span>实际来源渠道</span><strong>${new Set(signals.map(s => s.channel).filter(Boolean)).size}</strong><small>按入库渠道统计</small></div>
      <div><span>已归档批次</span><strong>${archived}</strong><small>按采集批次归档</small></div>
    </div>
    ${list.length ? workMode === 'matrix' ? renderMatrix(list) : `
    <div class="research-desk">
      <aside class="desk-panel watch-panel">
        <div class="panel-head"><h3>候选方向</h3><span class="panel-count">${list.length} 个</span></div>
        <div class="watch-sort"><span>方向 / 验证状态</span><span>评分 ↓</span></div>
        <div id="watchList" onkeydown="navigateCandidates(event)"></div>
      </aside>
      <div id="researchSelection" class="research-selection"></div>
    </div>` : '<div class="inspector">当前批次暂无候选方向。</div>'}
  `;
  if (list.length && workMode !== 'matrix') updateSelection(list);
}

function renderWatchlist(list) {
  return list.map((p, i) => `
    <button type="button" class="watch-item" data-rank="${i}" aria-pressed="${p.code === selectedCode}" onclick="selectProject(${i})">
      <span class="watch-rank">${String(i+1).padStart(2, '0')}</span>
      <span class="watch-label"><strong>${esc(shortTitle(p))}</strong><small>${esc(stageName(savedReports[p.code]?.stage))} · ${evidenceFor(p).length} 条关联</small></span>
      <span class="watch-score">${scoreText(p)}</span>
    </button>`).join('');
}

function updateSelection(list) {
  const watch = document.getElementById('watchList');
  if (!watch.children.length) watch.innerHTML = renderWatchlist(list);
  for (const item of watch.children) {
    item.setAttribute('aria-pressed', String(list[Number(item.dataset.rank)]?.code === selectedCode));
  }
  const index = list.findIndex(p => p.code === selectedCode);
  const p = list[index];
  if (!p) return;
  const selection = document.getElementById('researchSelection');
  selection.innerHTML = `
    <div class="research-main">
      <section class="desk-panel project-brief" aria-labelledby="activeProject">
        <div class="brief-grid">
          <div>
            <div class="brief-eyebrow"><span class="asset-code">${esc(p.code)}</span><span>${esc(sourceLabel(p))}</span><span class="asset-code" style="color:var(--gold);border-color:#5c4d26;background:#262013;">${esc((p.compounding && p.compounding.tier) || "重点方向")}</span></div>
            <h3 id="activeProject">${esc(heroTitle(p))}</h3>
            <p class="brief-lead">${esc(p.plain_what_to_do || BRIEFS[p.code])}</p>
          </div>
          ${scoreDial(p)}
        </div>
        ${p.ai_sharp_review ? `
        <div class="sharp-callout">
          <div class="sharp-badge">AI 锐评 · 商业切入点与真实数据诊断</div>
          <p>${esc(p.ai_sharp_review)}</p>
        </div>` : ""}
        ${RESEARCH_QUESTIONS[p.code] ? `<div class="brief-question"><span>关键问题</span><p>${esc(RESEARCH_QUESTIONS[p.code])}</p></div>` : ""}
      </section>
      ${workMode === 'quick' ? `
      <section class="desk-panel" style="padding:14px 16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <strong style="font-size:13.5px;">核心商业速览（一屏看懂投多少、赚多少、需要几人）</strong>
          <button type="button" class="btn" onclick="setWorkMode('focus')">切换完整深度档案 →</button>
        </div>
        <div class="quick-digest-grid">
          <div class="card-cell"><span class="cell-k">利润预估与收入来源</span><div class="cell-v">${esc(p.biz_eval?.profit || "待核算")}</div></div>
          <div class="card-cell"><span class="cell-k">所需人数与研发周期</span><div class="cell-v">${esc(p.biz_eval?.team || "1~2人")} · ${esc(p.biz_eval?.time || "1周内")}</div></div>
          <div class="card-cell"><span class="cell-k">初期资金成本与合规</span><div class="cell-v">${esc(p.biz_eval?.cost || "<100元")}</div></div>
        </div>
      </section>
      <div class="research-panels" style="grid-template-columns:1fr;">
        ${renderFactors(p)}
      </div>
      ` : `
      <div class="research-panels">
        ${renderLinkedEvidence(p)}
        ${renderFactors(p)}
      </div>
      <section class="desk-panel archive-open">
        <div class="panel-head"><h3>完整立项评估档案（执行流程 · 长期技术壁垒 · 成本利润与合规核算）</h3><span class="panel-count">${esc(p.code)}</span></div>
        <div class="archive-open-body">
          ${renderUnfoldedArchive(p)}
        </div>
      </section>`}
    </div>
    <aside class="research-context">
      ${renderValidation(p)}
      ${p.who_pays_and_price ? `<section class="desk-panel"><div class="panel-head"><h3>客群与定价</h3></div><div class="context-note">${esc(p.who_pays_and_price)}</div></section>` : ''}
    </aside>`;
}

function scoreDial(p) {
  const value = Number.isFinite(p.score) ? Math.max(0, Math.min(100, p.score)) : 0;
  return `<div class="score-dial" aria-label="评估分 ${scoreText(p)}，满分 100">
    <svg viewBox="0 0 120 120" aria-hidden="true">
      <circle class="dial-guide" cx="60" cy="60" r="56"/>
      <circle class="dial-track" cx="60" cy="60" r="48"/>
      <circle class="dial-fill" cx="60" cy="60" r="48" pathLength="100" stroke-dasharray="${value} 100" transform="rotate(-90 60 60)"/>
    </svg>
    <div class="dial-caption" aria-hidden="true"><strong>${scoreText(p)}</strong><span>评估分 / 100</span></div>
  </div>`;
}

function navigateCandidates(event) {
  const directions = {ArrowUp:-1, ArrowDown:1, ArrowLeft:-1, ArrowRight:1};
  const step = directions[event.key];
  const item = event.target.closest('.watch-item');
  if (!item || !step) return;
  const next = Number(item.dataset.rank) + step;
  if (next < 0 || next >= event.currentTarget.children.length) return;
  event.preventDefault();
  selectProject(next);
  document.querySelector('.watch-item[aria-pressed=true]')?.scrollIntoView({block:'nearest',inline:'nearest'});
}

function selectProject(index) {
  const list = getAllProjects();
  if (!list[index]) return;
  if (list[index].code === selectedCode && workMode !== 'matrix') return;
  selectedCode = list[index].code;
  history.replaceState(null, '', '#project=' + encodeURIComponent(selectedCode));
  if (workMode === 'matrix') {
    workMode = 'focus';
    renderProjects();
    const active = document.querySelector('.watch-item[aria-pressed=true]');
    active?.focus({preventScroll: true});
    document.getElementById('tab-projects').scrollIntoView({block: 'start'});
  } else {
    updateSelection(list);
    document.querySelector('.watch-item[aria-pressed=true]')?.focus({preventScroll: true});
  }
}

function setWorkMode(mode) {
  if (mode === workMode) return;
  workMode = mode;
  try { localStorage.setItem('mr_work_mode', mode); } catch {}
  renderProjects();
  document.getElementById(mode === 'quick' ? 'quickMode' : mode === 'focus' ? 'focusMode' : 'matrixMode')?.focus();
}

function renderFactors(p) {
  const reasons = p.score_reasons || {};
  const payScore = factorValues(p)[0]?.score ?? 30;
  const warnHtml = payScore < 20 ? `<div style="margin-bottom:10px;padding:7px 10px;border-radius:6px;background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.35);color:#fca5a5;font-size:12px;">注意：该方向尚未验证真实付费交易（付费分 &lt; 20），严禁直接投入重度开发，须先测款。</div>` : "";
  return `
    <section class="desk-panel" aria-label="立项评分依据">
      <div class="panel-head"><h3>立项评分与给分依据</h3><span class="panel-count">客观证据档位制</span></div>
      <div class="factor-body">
        ${warnHtml}
        ${factorValues(p).map(({label, score, max}) => {
          const rText = reasons[label] || "";
          return `
          <div class="factor-row">
            <div><span style="font-weight:500;color:var(--text);">${label}</span><span class="mono">${max ? score + ' / ' + max : '—'}</span></div>
            ${max ? `<meter min="0" max="${max}" value="${score}" aria-label="${label}"></meter>` : ''}
            ${rText ? `<div class="factor-reason">${esc(rText)}</div>` : ''}
          </div>`;
        }).join('')}
        <details class="rubric-guide">
          <summary>查看评分标尺说明（每档怎么给分？）</summary>
          <ul class="rubric-list">
            <li><strong>付费意愿 (40分)</strong>：闲鱼/蝉妈妈同款想要&gt;500或已收定金=35~40分；想要50~500或万评内购App=26~34分；仅口头求链接无交易=15~22分；无付费迹象=0~14分（一票否决预警）。</li>
            <li><strong>获客渠道 (25分)</strong>：高赞痛点帖评论区可直接截流或有现成精准群=20~25分；靠闲鱼/Steam长尾搜索自然获客=14~19分；需起号赌流量或买量=5~12分。</li>
            <li><strong>研发交付 (15分)</strong>：复用现有代码3~5天出MVP=12~15分；1~2周含硬件/跨端联调=9~11分；超2周重度开发=0~8分。</li>
            <li><strong>竞争空间 (10分)</strong>：切中大厂盲区或软硬/离线隐私独家切口=8~10分；存量红海做差异化单点=5~7分；大厂免费功能已覆盖=0~4分。</li>
            <li><strong>快速验证 (10分)</strong>：48小时内零代码挂闲鱼/发样片即可测出真金白银询单=8~10分；需做出完整版才能测=3~6分。</li>
          </ul>
        </details>
      </div>
    </section>`;
}

function renderMatrix(list) {
  return `
    <section class="desk-panel matrix-panel">
      <div class="panel-head"><h3>候选方向比较</h3><span class="panel-count">按评估分排序 · 分项显示得分 / 满分</span></div>
      <div class="table-wrap" role="region" aria-label="五维评分对照表" tabindex="0">
        <table class="matrix-table">
          <thead><tr><th>排名</th><th>候选方向</th><th>总分</th>${FACTORS.map(([,label]) => `<th>${label}</th>`).join('')}<th>可查证据</th><th>验证状态</th></tr></thead>
          <tbody>${list.map((p,i) => `
          <tr>
            <td class="mono">${String(i+1).padStart(2,'0')}</td>
            <td><button type="button" class="matrix-link" onclick="selectProject(${i})">${esc(shortTitle(p))}<small>${esc(sourceLabel(p))}</small></button></td>
            <td class="matrix-total mono">${scoreText(p)}</td>
            ${factorValues(p).map(x => `<td class="mono">${x.max ? x.score + '/' + x.max : '—'}</td>`).join('')}
            <td class="mono">${evidenceFor(p).filter(s => !s.is_noise).length}</td>
            <td>${esc(stageName(savedReports[p.code]?.stage))}</td>
          </tr>`).join('')}</tbody>
        </table>
      </div>
    </section>`;
}

function evidenceKind(s) {
  if (/导表/.test(s.source_tier + ' ' + s.channel)) return '导入记录';
  if (/AppStore/i.test(s.channel)) return '用户差评';
  if (/B站/.test(s.channel)) return '视频与评论';
  if (/微信/.test(s.channel)) return '公开文章摘要';
  if (/V2EX/i.test(s.channel)) return '社区讨论';
  return '采集记录';
}

function renderLinkedEvidence(p) {
  const evidence = evidenceFor(p);
  const missing = new Set(p.evidence_ids || []).size - evidence.length;
  const active = evidence.filter(s => !s.is_noise);
  const kinds = new Set(active.map(s => s.channel).filter(Boolean));
  const rows = evidence.map(s => `
    <button type="button" class="evidence-item" onclick="openSnap(${Number(s.id)})">
      <span class="evidence-meta">#${Number(s.id)} · 时间 ${esc(signalPublishedText(s))}${signalTiming(s).tier === 'stale_archive' ? ' (超半年旧帖)' : ''} · ${esc(s.audience_tag || evidenceKind(s))}</span>
      <strong>${esc(s.title)}</strong>
      <small>${[s.author_or_app, s.metric_primary].filter(Boolean).map(esc).join(' · ')}</small>
      <span class="evidence-arrow" aria-hidden="true">↗</span>
    </button>`);
  return `
    <section class="desk-panel evidence-panel">
      <div class="panel-head"><h3>关联市场信号</h3><span class="panel-count">${active.length} 条有效 · ${kinds.size} 个渠道</span></div>
      ${evidence.length ? `
        <div class="evidence-list">${rows.slice(0,3).join('')}</div>
        ${rows.length > 3 ? `<details><summary>查看其余 ${rows.length - 3} 条关联</summary><div class="evidence-list">${rows.slice(3).join('')}</div></details>` : ''}
      ` : '<p class="panel-empty">暂无关联信号记录。</p>'}
    </section>`;
}

function renderValidation(p) {
  const report = savedReports[p.code] || {};
  return `
    <section class="desk-panel validation-panel">
      <div class="panel-head"><h3>48 小时验证</h3><span class="panel-count" id="validationStage">${stageName(report.stage)}</span></div>
      <div class="validation-body">
        <span class="section-kicker">建议动作</span>
        <p>${esc(p.plan_48h) || '暂无验证建议。'}</p>
        <details id="validationRecord">
          <summary>${report.updated ? '查看 / 更新验证记录' : '记录通过条件与实际结果'}</summary>
          <form class="validation-form" onsubmit="saveValidation(event)">
            <label>验证状态<select id="validationStatus">${STAGES.map(([key,label]) => `<option value="${key}" ${report.stage === key ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
            <label>通过条件<textarea id="validationCriterion" rows="2" maxlength="600" placeholder="例如：联系 10 位目标客户，至少 2 位支付定金">${escapeFormValue(report.criterion)}</textarea></label>
            <label>实际结果<textarea id="validationResult" rows="2" maxlength="1200" placeholder="记录触达、询价、付定金人数，以及观察到的阻碍">${escapeFormValue(report.result)}</textarea></label>
            <button class="btn btn-primary" type="submit">保存记录</button>
            <small class="quiet-note">${report.updated ? '上次保存：' + esc(report.updated) : ''}</small>
            <p id="validationMessage" role="status"></p>
          </form>
        </details>
      </div>
    </section>`;
}

function escapeFormValue(value) {
  return String(value ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function saveValidation(event) {
  event.preventDefault();
  const stage = document.getElementById('validationStatus').value;
  const criterion = document.getElementById('validationCriterion').value.trim();
  const result = document.getElementById('validationResult').value.trim();
  const message = document.getElementById('validationMessage');
  if (['pass', 'fail'].includes(stage) && (!criterion || !result)) {
    message.textContent = '请填写通过条件和实际结果，再记录结论。';
    return;
  }
  const time = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', dateStyle: 'short', timeStyle: 'short',
  }).format(new Date());
  const next = {...savedReports};
  if (stage === 'planned' && !criterion && !result) delete next[selectedCode];
  else next[selectedCode] = {stage, criterion, result, updated: time};
  try {
    localStorage.setItem(VALIDATION_KEY, JSON.stringify(next));
  } catch {
    message.textContent = '当前浏览器无法保存记录，请保留填写内容。';
    return;
  }
  savedReports = next;
  const watch = document.getElementById('watchList');
  const scroll = watch.scrollLeft;
  watch.innerHTML = renderWatchlist(getAllProjects());
  watch.scrollLeft = scroll;
  document.getElementById('validationStage').textContent = stageName(stage);
  const exists = Boolean(next[selectedCode]);
  event.currentTarget.querySelector('.quiet-note').textContent = exists ? '上次保存：' + time : '';
  document.querySelector('#validationRecord summary').textContent = exists ? '查看 / 更新验证记录' : '记录通过条件与实际结果';
  message.textContent = exists ? '验证记录已保存。' : '已恢复为待验证。';
}


function renderUnfoldedArchive(p) {
  const steps = (p.workflow_steps || []).map((st, i) =>
    `<div class="step-row"><span class="step-no">0${i+1}</span><div>${esc(st)}</div></div>`
  ).join("");
  const comp = p.compounding || {
    tier: "可持续积累",
    snowball: "初期通过轻量服务验证需求，中期沉淀行业模板与自动化流水线转为订阅制工具。",
    skill_gain: "沉淀领域工作流编排与产品工程能力。"
  };
  const b = p.biz_eval || {
    cost: "初期成本 <100元", profit: "毛利率 90%+", time: "MVP 5~7天",
    team: "1~2人", landing: "48h测款 -> 自动化交付 -> 订阅工具", compliance: "遵守平台与数据脱敏规范"
  };
  return `
    <div class="inspector">
      <span class="sec-label">01 / 分阶段推进计划与交付流程</span>
      <div class="card-cell" style="margin-bottom:18px;">
        <div class="cell-v">${steps}</div>
      </div>

      <span class="sec-label">02 / 长期复利壁垒与团队技术沉淀</span>
      <div class="grid-2" style="margin-bottom:18px;">
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
      <div class="grid-3" style="margin-bottom:0;">
        <div class="card-cell"><span class="cell-k">1. 初步资金成本预估</span><div class="cell-v">${esc(b.cost)}</div></div>
        <div class="card-cell"><span class="cell-k">2. 利润预估与多元收入来源</span><div class="cell-v">${esc(b.profit)}</div></div>
        <div class="card-cell"><span class="cell-k">3. 时间成本（研发与回本周期）</span><div class="cell-v">${esc(b.time)}</div></div>
        <div class="card-cell"><span class="cell-k">4. 需要人数与角色配置</span><div class="cell-v">${esc(b.team)}</div></div>
        <div class="card-cell"><span class="cell-k">5. 落地推进路径</span><div class="cell-v">${esc(b.landing)}</div></div>
        <div class="card-cell"><span class="cell-k">6. 国内法律与平台合规边界</span><div class="cell-v">${esc(b.compliance)}</div></div>
      </div>
    </div>
  `;
}
