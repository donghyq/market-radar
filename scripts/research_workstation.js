const SHORT_TITLES = {
  'AUTO-01': '带货图文批量制作',
  'PROJ-01': '知识动画生成',
  'TEAM-FE4500': '跨境达人寄样跟进',
  'AUTO-02': '标书废标项检查',
  'PROJ-02': '律所获客短视频',
  'PROJ-03': '备考规划与教培成长报告',
  'AUTO-03': '门窗与定制柜快速报价',
  'PROJ-04': '离线提词与视频粗剪',
  'PROJ-05': '直播弹幕互动工具',
};
const RESEARCH_QUESTIONS = {
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
const FACTORS = [
  ['付费意愿', '付费意愿'], ['获客截流', '获客渠道'], ['研发交付', '研发交付'],
  ['竞争缝隙', '竞争空间'], ['48h测款', '快速验证'],
];
const STAGES = [
  ['planned', '待验证'], ['running', '验证中'], ['pass', '已达到条件'],
  ['fail', '未达到条件'], ['unclear', '结果不充分'],
];
const VALIDATION_KEY = 'mr_validation_v1';

let selectedCode = '';
let workMode = 'focus';
let savedReports = readReports();

function readReports() {
  try {
    const data = JSON.parse(localStorage.getItem(VALIDATION_KEY) || '{}');
    return data && typeof data === 'object' && !Array.isArray(data) ? data : {};
  } catch { return {}; }
}

function shortTitle(p) {
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
        <span class="section-kicker">RESEARCH DESK</span>
        <h2>市场机会工作台</h2>
        <p>比较候选方向，追溯关键证据，记录验证结果。</p>
      </div>
      <div class="mode-select" aria-label="查看方式">
        <button type="button" class="btn" id="focusMode" aria-pressed="${workMode === 'focus'}" onclick="setWorkMode('focus')">项目研究</button>
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
        <div class="panel-head"><h3>候选列表</h3><span class="panel-count">${list.length}</span></div>
        <p class="watch-sort">按评估分排序</p>
        <div id="watchList"></div>
      </aside>
      <div id="researchSelection" class="research-selection"></div>
    </div>` : '<div class="inspector">当前批次暂无候选方向。</div>'}
  `;
  if (list.length && workMode === 'focus') updateSelection(list);
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
  document.getElementById('researchSelection').innerHTML = `
    <div class="research-main">
      <section class="desk-panel project-brief" aria-labelledby="activeProject">
        <div class="brief-eyebrow"><span class="asset-code">${esc(p.code)}</span><span>${esc(sourceLabel(p))}</span></div>
        <h3 id="activeProject">${esc(shortTitle(p))}</h3>
        <p class="brief-lead">${esc(p.plain_what_to_do) || '暂无产品定位。'}</p>
        ${p.who_pays_and_price ? `<div class="brief-buyer"><span>客群与定价假设</span><p>${esc(p.who_pays_and_price)}</p></div>` : ''}
      </section>
      ${renderLinkedEvidence(p)}
      <details class="desk-panel archive-detail">
        <summary>展开完整评估档案</summary>
        ${renderDetailCard(p, index)}
      </details>
    </div>
    <aside class="research-context">
      ${renderFactors(p)}
      ${renderValidation(p)}
    </aside>`;
}

function selectProject(index) {
  const list = getAllProjects();
  if (!list[index]) return;
  selectedCode = list[index].code;
  if (workMode !== 'focus') {
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
  renderProjects();
  document.getElementById(mode === 'focus' ? 'focusMode' : 'matrixMode')?.focus();
}

function renderFactors(p) {
  const rules = p.code?.startsWith('TEAM-') ? '团队提报评分' : '评估模型评分';
  return `
    <section class="desk-panel" aria-label="立项评分">
      <div class="panel-head"><h3>五维评分</h3><span class="panel-count">${rules}</span></div>
      <div class="factor-body">
        <div class="factor-total"><strong>${scoreText(p)}</strong><span> / 100</span></div>
        ${factorValues(p).map(({label, score, max}) => `
          <div class="factor-row">
            <div><span>${label}</span><span>${max ? score + '/' + max : '未记录'}</span></div>
            ${max ? `<meter min="0" max="${max}" value="${score}" aria-label="${label}"></meter>` : ''}
          </div>`).join('')}
        <p class="quiet-note">评分用于比较方向；不代表付费已验证。</p>
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
      <span class="evidence-meta">#${Number(s.id)} · ${esc(evidenceKind(s))}${s.is_noise ? ' · 已过滤' : ''}</span>
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
      ` : '<p class="panel-empty">暂无可打开的关联快照。提报描述和评分不能替代来源记录。</p>'}
      ${missing ? `<p class="panel-empty">${missing} 条引用未找到当前批次快照。</p>` : ''}
    </section>`;
}

function renderValidation(p) {
  const report = savedReports[p.code] || {};
  return `
    <section class="desk-panel validation-panel">
      <div class="panel-head"><h3>48 小时验证</h3><span class="panel-count" id="validationStage">${stageName(report.stage)}</span></div>
      <div class="validation-body">
        ${RESEARCH_QUESTIONS[p.code] ? `<div class="validation-question"><span class="section-kicker">待验证问题</span><p>${esc(RESEARCH_QUESTIONS[p.code])}</p></div>` : ''}
        <span class="section-kicker">建议动作</span>
        <p>${esc(p.plan_48h) || '暂无验证建议。'}</p>
        <details id="validationRecord">
          <summary>${report.updated ? '查看 / 更新验证记录' : '记录通过条件与实际结果'}</summary>
          <form class="validation-form" onsubmit="saveValidation(event)">
            <label>验证状态<select id="validationStatus">${STAGES.map(([key,label]) => `<option value="${key}" ${report.stage === key ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
            <label>通过条件<textarea id="validationCriterion" rows="2" maxlength="600" placeholder="例如：联系 10 位目标客户，至少 2 位支付定金">${escapeFormValue(report.criterion)}</textarea></label>
            <label>实际结果<textarea id="validationResult" rows="2" maxlength="1200" placeholder="记录触达、询价、付定金人数，以及观察到的阻碍">${escapeFormValue(report.result)}</textarea></label>
            <button class="btn btn-primary" type="submit">保存记录</button>
            <small class="quiet-note">仅保存在当前浏览器。${report.updated ? ' 上次保存于 ' + esc(report.updated) + '。' : ''}</small>
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
  event.currentTarget.querySelector('.quiet-note').textContent = '仅保存在当前浏览器。' + (exists ? '上次保存于 ' + time + '。' : '');
  document.querySelector('#validationRecord summary').textContent = exists ? '查看 / 更新验证记录' : '记录通过条件与实际结果';
  message.textContent = exists ? '验证记录已保存。' : '已恢复为待验证。';
}
