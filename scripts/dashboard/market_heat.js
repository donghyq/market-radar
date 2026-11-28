const HEAT_DAY_MS = 86400000;
const HEAT_HOUR_MS = 3600000;
const HEAT_METRICS = {
  discussion: {name: '讨论热度', color: '#75c6f2', dash: []},
  demand: {name: '需求热度', color: '#81d1bd', dash: [6, 3]},
  production: {name: '生产热度', color: '#efc285', dash: [2, 4]},
};
const HEAT_KEYS = Object.keys(HEAT_METRICS);
const HEAT_CATEGORY_COLORS = [
  '#75c6f2', '#efb06e', '#7bd6ab', '#ee82a2', '#b7a1fa',
  '#f2d77e', '#79d9dd', '#ff937e', '#8baaf4', '#b9db81',
  '#f097ea', '#53cba2', '#d9aa91', '#89caf8', '#d7d8e8',
];

function heatDate(ms) {
  return new Date(ms).toISOString().slice(0, 10);
}

function heatHour(ms) {
  return new Date(ms + MARKET_OFFSET_MS).toISOString().slice(0, 16).replace('T', ' ');
}

function heatPeriodLabel(period) {
  return period.first === period.last ? period.first : period.first + ' 至 ' + period.last;
}

function heatPeriods(start, end, grain, events, coverage, comparison = null) {
  const keys = comparison ? comparison.categories : HEAT_KEYS;
  const periods = new Map();
  const slotIndex = new Map();
  const verified = new Map();
  const hourly = grain === 'hour';
  const size = hourly ? HEAT_HOUR_MS : HEAT_DAY_MS;
  const first = Date.parse(start), last = Date.parse(end);
  const slotOf = time => Math.floor(time / size) * size;
  for (const [day, metric] of coverage) {
    if (!verified.has(day)) verified.set(day, new Set());
    verified.get(day).add(metric);
  }
  for (let time = slotOf(first); time <= last; time += size) {
    const day = heatDate(time + (hourly ? MARKET_OFFSET_MS : 0));
    const offset = (new Date(time).getUTCDay() + 6) % 7;
    const key = grain === 'week' ? time - offset * size : time;
    if (!periods.has(key)) {
      periods.set(key, {
        first: hourly ? heatHour(Math.max(time, first)) : day,
        tick: hourly ? heatHour(time).slice(5) : day,
        slots: 0,
        series: Object.fromEntries(keys.map(key => [key, {refs: [], covered: 0}])),
      });
    }
    const period = periods.get(key);
    period.last = hourly ? heatHour(Math.min(time + size, last)) : day;
    period.slots++;
    for (const key of verified.get(day) || []) {
      if (period.series[key]) period.series[key].covered++;
    }
    slotIndex.set(time, period);
  }
  for (const event of events) {
    const time = Date.parse(hourly ? event.timestamp : event.day);
    if (time < first || time > last) continue;
    const period = slotIndex.get(slotOf(time));
    if (!period) continue;
    if (comparison) {
      if (event.metrics.includes(comparison.metric)) period.series[event.category]?.refs.push(event);
    } else {
      for (const metric of event.metrics) period.series[metric].refs.push(event);
    }
  }
  for (const period of periods.values()) {
    for (const series of Object.values(period.series)) {
      series.count = series.refs.length || (series.covered === period.slots ? 0 : null);
    }
  }
  return [...periods.values()];
}

function drawHeatChart(canvas, periods, selected, cursor, styles = HEAT_METRICS, focus = '') {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (!width || !height || !periods.length) return null;
  const ratio = window.devicePixelRatio || 1;
  const pixelWidth = Math.round(width * ratio);
  const pixelHeight = Math.round(height * ratio);
  if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
  if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  const left = 48, right = width - 18, top = 18, bottom = height - 34;
  const span = right - left;
  const last = periods.length - 1;
  const x = index => last ? left + index * span / last : left + span / 2;
  const lines = Object.entries(styles);
  let max = 0;
  for (const point of periods) for (const [key] of lines) max = Math.max(max, point.series[key].count || 0);
  const estimate = Math.max(1, max / 4);
  const unit = 10 ** Math.floor(Math.log10(estimate));
  const step = unit * [1, 2, 5, 10].find(multiplier => unit * multiplier >= estimate);
  const y = count => bottom - count * (bottom - top) / (4 * step);
  ctx.font = '11px ui-monospace, monospace';
  ctx.lineWidth = 1;
  ctx.setLineDash([]);
  ctx.strokeStyle = '#2b3b4c';
  ctx.fillStyle = '#a5b6c9';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let i = 0; i <= 4; i++) {
    const value = i * step;
    ctx.beginPath();
    ctx.moveTo(left, y(value));
    ctx.lineTo(right, y(value));
    ctx.stroke();
    ctx.fillText(String(value), left - 9, y(value));
  }
  const tickCount = Math.max(2, Math.min(8, Math.floor(span / 100)));
  const ticks = new Set(Array.from({length: tickCount}, (_, i) => Math.round(last * i / (tickCount - 1))));
  ctx.textBaseline = 'top';
  for (const i of ticks) {
    ctx.textAlign = i === 0 ? 'left' : i === last ? 'right' : 'center';
    ctx.fillText(periods[i].tick, x(i), bottom + 10);
  }
  const marker = cursor ?? selected;
  if (marker >= 0) {
    ctx.strokeStyle = '#546b82';
    ctx.setLineDash([3, 4]);
    ctx.beginPath();
    ctx.moveTo(x(marker), top);
    ctx.lineTo(x(marker), bottom);
    ctx.stroke();
  }
  for (const [key, {color, dash}] of lines) {
    ctx.globalAlpha = focus && key !== focus ? 0.26 : 1;
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = key === focus ? 2.8 : 1.85;
    ctx.setLineDash(dash);
    let connected = false;
    periods.forEach((period, i) => {
      const count = period.series[key].count;
      if (count === null) {
        connected = false;
        return;
      }
      if (connected) ctx.lineTo(x(i), y(count));
      else ctx.moveTo(x(i), y(count));
      connected = true;
    });
    ctx.stroke();
    ctx.fillStyle = color;
    periods.forEach((period, i) => {
      const count = period.series[key].count;
      if (count === null) return;
      ctx.beginPath();
      ctx.arc(x(i), y(count), i === marker && (!focus || key === focus) ? 4.2 : 2.5, 0, Math.PI * 2);
      ctx.fill();
    });
  }
  ctx.globalAlpha = 1;
  return {left, right, top, bottom, x, y};
}

function heatContributors(refs, products) {
  const counts = new Map();
  for (const event of refs) {
    const name = products[event.product]?.name || event.category;
    counts.set(name, (counts.get(name) || 0) + 1);
  }
  return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'zh-CN')).slice(0, 3);
}

function renderMarketHeat() {
  const tab = document.getElementById('tab-heat');
  if (tab.childElementCount) return;
  const data = DATA.market_heat;
  if (!data) {
    tab.textContent = '热度数据待生成';
    return;
  }
  tab.innerHTML = [
    '<section class="inspector market-heat"><div class="heat-heading"><h2>市场热度</h2>',
    '<div class="heat-controls"><label>时间 <select id="heatRange"><option value="24h">近 24 小时</option>',
    '<option value="7">近 7 天</option><option value="30" selected>近 30 天</option>',
    '<option value="90">近 90 天</option><option value="180">近 180 天</option><option value="all">全部时间</option></select></label>',
    '<label>周期 <select id="heatGrain"><option value="hour">按小时</option><option value="day" selected>按日</option><option value="week">按周</option></select></label>',
    '<label>品类 <select id="heatCategory"></select></label><label>产品 <select id="heatProduct"></select></label>',
    '<label id="heatCompareControl">对比热度 <select id="heatCompareMetric"></select></label></div></div>',
    '<div id="heatTotals" class="heat-totals"></div>',
    '<div id="heatLegend" class="heat-legend" role="group" aria-label="切换品类曲线"></div>',
    '<div class="heat-plot"><canvas id="heatChart" tabindex="0" aria-label="市场热度折线图，方向键切换时段，回车查看证据"></canvas>',
    '<div id="heatEmpty" class="heat-empty" hidden></div>',
    '<div id="heatHint" class="heat-hint" role="tooltip" hidden></div></div>',
    '<div class="heat-foot"><span id="heatTimeNote"></span>',
    '<button class="btn" id="heatUndated" type="button"></button></div></section>',
    '<section class="inspector heat-evidence"><div class="heat-heading"><h3>对应证据</h3>',
    '<div class="heat-controls"><label>时段 <select id="heatPeriod"></select></label>',
    '<label id="heatEvidenceMetricControl">热度 <select id="heatMetric"></select></label>',
    '<label id="heatEvidenceCategoryControl">品类 <select id="heatEvidenceCategory"></select></label></div></div>',
    '<p id="heatEvidenceSummary" aria-live="polite"></p><ul id="heatEvidenceList"></ul>',
    '<button class="btn" id="heatMore" type="button" hidden>显示更多</button></section>',
  ].join('');
  const el = id => document.getElementById(id);
  const range = el('heatRange'), grain = el('heatGrain'), category = el('heatCategory'), product = el('heatProduct');
  const chart = el('heatChart'), hint = el('heatHint'), dateSelect = el('heatPeriod'), metricSelect = el('heatMetric');
  const comparisonMetric = el('heatCompareMetric'), evidenceCategory = el('heatEvidenceCategory');
  const legend = el('heatLegend'), empty = el('heatEmpty');
  const unknownButton = el('heatUndated'), more = el('heatMore');
  const allRecords = new Map(DATA.signals.map(row => [row.display_id, row]));
  const productChoices = Object.entries(data.products).sort((a, b) => a[1].name.localeCompare(b[1].name, 'zh-CN'));
  const categoryStyles = Object.fromEntries(data.categories.map((name, index) => [name, {
    color: HEAT_CATEGORY_COLORS[index % HEAT_CATEGORY_COLORS.length],
    dash: [[], [6, 3], [2, 3]][index % 3],
  }]));
  const hiddenCategories = new Set();
  let periods = [], chartPeriods = [], undated = [], active = -1, hover = null, hoveredLine = '';
  let comparing = false, showUndated = false, limit = 20, axes = null;

  const option = (value, label) => new Option(label, value);
  category.replaceChildren(option('', '全部品类同图'), ...data.categories.map(name => option(name, name)));
  for (const select of [metricSelect, comparisonMetric]) {
    select.replaceChildren(...HEAT_KEYS.map(key => option(key, HEAT_METRICS[key].name)));
  }
  evidenceCategory.replaceChildren(option('', '全部品类'), ...data.categories.map(name => option(name, name)));

  const selectedMetric = () => comparing ? comparisonMetric.value : metricSelect.value;

  function visibleStyles() {
    return comparing ? Object.fromEntries(Object.entries(categoryStyles)
      .filter(([name]) => !hiddenCategories.has(name))) : HEAT_METRICS;
  }

  function draw() {
    const styles = visibleStyles();
    axes = drawHeatChart(chart, chartPeriods, showUndated ? -1 : active, hover, styles, hoveredLine);
    const keys = Object.keys(styles);
    empty.hidden = !comparing || chartPeriods.some(period => keys.some(key => period.series[key].count !== null));
    if (!empty.hidden) empty.textContent = keys.length ? '当前时段暂无可核实的' + HEAT_METRICS[selectedMetric()].name + '记录'
      : '请选择要显示的品类';
  }

  function renderLegend() {
    legend.hidden = !comparing;
    if (!comparing) return;
    const totals = data.categories.map(name => {
      const points = chartPeriods.map(period => period.series[name].count);
      const total = points.some(count => count !== null)
        ? points.reduce((sum, count) => sum + (count ?? 0), 0) : null;
      return {name, total};
    }).sort((a, b) => (b.total ?? -1) - (a.total ?? -1));
    const buttons = totals.map(({name, total}) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn heat-legend-item';
      button.style.setProperty('--heat-color', categoryStyles[name].color);
      button.setAttribute('aria-pressed', String(!hiddenCategories.has(name)));
      const label = document.createElement('span');
      label.textContent = name;
      const count = document.createElement('small');
      count.textContent = total?.toLocaleString('zh-CN') ?? '—';
      button.append(label, count);
      button.onclick = () => {
        if (hiddenCategories.has(name)) hiddenCategories.delete(name);
        else hiddenCategories.add(name);
        button.setAttribute('aria-pressed', String(!hiddenCategories.has(name)));
        draw();
      };
      return button;
    });
    legend.replaceChildren(...buttons);
  }

  function updateProducts() {
    product.replaceChildren(option('', '全部产品'), ...productChoices
      .filter(([, item]) => !category.value || item.category === category.value)
      .map(([key, item]) => option(key, item.name.length > 55 ? item.name.slice(0, 55) + '…' : item.name)));
  }

  function showEvidence() {
    const period = periods[active];
    const metric = selectedMetric();
    const scopedCategory = comparing ? evidenceCategory.value : '';
    const series = scopedCategory ? chartPeriods[active]?.series[scopedCategory] : period?.series[metric];
    const refs = showUndated ? undated.filter(row => row.metrics.includes(metric)
      && (!scopedCategory || row.category === scopedCategory)) : series?.refs || [];
    const caption = showUndated ? '时间待核实' : period ? heatPeriodLabel(period) : '当前范围';
    const status = !showUndated && series?.count === null ? '覆盖待核实' : refs.length + ' 条';
    el('heatEvidenceSummary').textContent = [caption, scopedCategory, HEAT_METRICS[metric].name, status].filter(Boolean).join(' · ');
    const list = el('heatEvidenceList');
    list.replaceChildren();
    for (const event of refs.slice(0, limit)) {
      const row = allRecords.get(event.id);
      if (!row) continue;
      const item = document.createElement('li');
      const open = document.createElement('button');
      open.type = 'button';
      open.className = 'btn';
      open.textContent = event.id;
      open.onclick = () => openSnap(recordKey(row));
      const excerpt = document.createElement('span');
      const group = data.products[event.product]?.name || event.category;
      const when = grain.value === 'hour' && event.timestamp ? heatHour(Date.parse(event.timestamp)) : event.day;
      excerpt.textContent = [event.release, when, group, signalExcerpt(
        row.record_type === 'comment' ? row.content : row.title, 72)].filter(Boolean).join(' · ');
      item.append(open, excerpt);
      const source = sourceLink(row.source_url) || sourceLink(row.parent_url);
      if (source) item.append(evidenceLink(source, '来源'));
      list.append(item);
    }
    more.hidden = refs.length <= limit;
  }

  function selectPeriod(index, metric, unknown = false) {
    active = index;
    showUndated = unknown;
    limit = 20;
    metricSelect.value = metric;
    const selectedValue = unknown ? 'undated' : String(index);
    if (!Array.from(dateSelect.options).some(item => item.value === selectedValue) && periods[index]) {
      dateSelect.add(option(selectedValue, heatPeriodLabel(periods[index]) + '（覆盖待核实）'));
    }
    dateSelect.value = selectedValue;
    unknownButton.setAttribute('aria-pressed', String(unknown));
    showEvidence();
    draw();
  }

  function refresh() {
    const hourly = range.value === '24h';
    const recentDays = range.value === '7' || range.value === '30';
    grain.querySelector('[value="hour"]').hidden = !hourly;
    grain.disabled = hourly || recentDays;
    if (hourly) grain.value = 'hour';
    else if (recentDays || grain.value === 'hour') grain.value = 'day';
    el('heatTimeNote').textContent = hourly
      ? '按精确源站时间（UTC+8）统计导出前 24 小时。断点表示覆盖待核实。'
      : '按源站日期（UTC+8）去重统计。断点表示覆盖待核实。';
    const scopeCategory = product.value ? data.products[product.value].category : category.value;
    comparing = !scopeCategory && !product.value;
    el('heatCompareControl').hidden = !comparing;
    el('heatEvidenceCategoryControl').hidden = !comparing;
    el('heatEvidenceMetricControl').hidden = comparing;
    const inScope = data.events.filter(event => (!scopeCategory || event.category === scopeCategory)
      && (!product.value || event.product === product.value));
    const coverage = data.coverage.filter(([, c, p]) => p === product.value
      && (c || data.products[p]?.category || '') === scopeCategory)
      .map(([day, , , metric]) => [day, metric]);
    const compareCoverage = comparing ? data.coverage.filter(([, c, p, metric]) =>
      c && !p && metric === comparisonMetric.value).map(([day, c]) => [day, c]) : [];
    const dates = inScope.map(event => event.day).filter(Boolean)
      .concat(coverage.map(([day]) => day), compareCoverage.map(([day]) => day)).sort();
    const reference = Date.parse(data.as_of_time);
    const exported = Number.isFinite(reference) ? reference : Date.now();
    const end = hourly ? new Date(exported).toISOString() : data.as_of;
    const start = hourly ? new Date(exported - HEAT_DAY_MS).toISOString()
      : range.value === 'all' ? dates[0] || data.as_of
        : heatDate(Date.parse(data.as_of) - (Number(range.value) - 1) * HEAT_DAY_MS);
    const inRange = hourly ? inScope.filter(event => {
      const time = Date.parse(event.timestamp);
      return time >= exported - HEAT_DAY_MS && time <= exported;
    }) : inScope.filter(event => event.day >= start && event.day <= end);
    periods = heatPeriods(start, end, grain.value, inRange, coverage);
    chartPeriods = comparing ? heatPeriods(start, end, grain.value, inRange, compareCoverage,
      {categories: data.categories, metric: comparisonMetric.value}) : periods;
    const firstMarketDay = heatDate(exported - HEAT_DAY_MS + MARKET_OFFSET_MS);
    undated = inScope.filter(event => !event.day || (hourly && !event.timestamp && event.day >= firstMarketDay));
    el('heatTotals').innerHTML = HEAT_KEYS.map(key => {
      const metric = HEAT_METRICS[key];
      const total = inRange.filter(event => event.metrics.includes(key)).length;
      const hasValues = periods.some(period => period.series[key].count !== null);
      return '<div style="--heat-color:' + metric.color + '"><span>' + metric.name +
        '</span><strong>' + (hasValues ? total.toLocaleString('zh-CN') : '—') + '</strong></div>';
    }).join('');
    const hasData = period => Object.values(period.series).some(series => series.count !== null);
    const available = chartPeriods.flatMap((period, i) => hasData(period) ? [i] : []);
    dateSelect.replaceChildren(...available.map(i => option(String(i), heatPeriodLabel(periods[i]))));
    if (undated.length) dateSelect.add(option('undated', '时间待核实'));
    unknownButton.textContent = '时间待核实 ' + undated.length.toLocaleString('zh-CN') + ' 条';
    unknownButton.disabled = !undated.length;
    hover = null;
    hoveredLine = '';
    hint.hidden = true;
    renderLegend();
    const index = available.at(-1) ?? periods.length - 1;
    const metric = comparing ? comparisonMetric.value
      : HEAT_KEYS.find(key => periods[index]?.series[key].refs.length) || 'discussion';
    selectPeriod(index, metric);
  }

  function location(event) {
    if (!axes) return null;
    const rect = chart.getBoundingClientRect();
    const x = event.clientX - rect.left, y = event.clientY - rect.top;
    if (x < axes.left - 6 || x > axes.right + 6 || y < axes.top - 8 || y > axes.bottom + 8) return null;
    const index = Math.min(periods.length - 1, Math.max(0,
      Math.round((x - axes.left) * (periods.length - 1) / (axes.right - axes.left))));
    const series = chartPeriods[index].series;
    const preferred = comparing ? evidenceCategory.value : metricSelect.value;
    const candidates = Object.keys(visibleStyles()).filter(key => series[key].count !== null);
    candidates.sort((a, b) => Math.abs(axes.y(series[a].count) - y) - Math.abs(axes.y(series[b].count) - y)
      || Number(b === preferred) - Number(a === preferred));
    return {index, key: candidates[0] || preferred, x, y, width: rect.width};
  }

  chart.addEventListener('pointermove', event => {
    const previous = hover;
    const previousLine = hoveredLine;
    const hit = location(event);
    if (!hit) {
      hint.hidden = true;
      hover = null;
      hoveredLine = '';
      if (previous !== null) draw();
      return;
    }
    const period = chartPeriods[hit.index];
    hover = hit.index;
    const series = period.series[hit.key];
    hoveredLine = comparing && series && series.count !== null ? hit.key : '';
    const contributors = heatContributors(series?.refs || [], data.products);
    const fields = comparing
      ? [[hit.key || '品类对比', series?.count, true]]
      : HEAT_KEYS.map(key => [HEAT_METRICS[key].name, period.series[key].count, key === hit.key]);
    const heading = heatPeriodLabel(period) + (comparing ? ' · ' + HEAT_METRICS[selectedMetric()].name : '');
    hint.innerHTML = '<strong>' + esc(heading) + '</strong>' + fields.map(([label, count, focused]) =>
      '<div class="' + (focused ? 'heat-hint-active' : '') + '">' + esc(label) + ' ' +
      (count ?? '覆盖待核实') + '</div>').join('') + contributors.map(([name, count]) =>
      '<small>' + esc(name) + ' · ' + count + '</small>').join('');
    hint.style.left = Math.max(8, Math.min(hit.x + 12, hit.width - 250)) + 'px';
    hint.style.top = Math.max(5, hit.y - 64) + 'px';
    hint.hidden = false;
    if (previous !== hover || previousLine !== hoveredLine) draw();
  });
  chart.addEventListener('pointerleave', () => {
    hint.hidden = true;
    hover = null;
    hoveredLine = '';
    draw();
  });
  chart.addEventListener('click', event => {
    const hit = location(event);
    if (!hit) return;
    if (comparing) evidenceCategory.value = hit.key;
    selectPeriod(hit.index, comparing ? comparisonMetric.value : hit.key);
  });
  chart.addEventListener('keydown', event => {
    const delta = {ArrowLeft: -1, ArrowRight: 1, Enter: 0}[event.key];
    if (delta === undefined) return;
    event.preventDefault();
    selectPeriod(Math.max(0, Math.min(periods.length - 1, (hover ?? active) + delta)), selectedMetric());
  });
  range.onchange = grain.onchange = product.onchange = refresh;
  comparisonMetric.onchange = refresh;
  category.onchange = () => { updateProducts(); refresh(); };
  metricSelect.onchange = evidenceCategory.onchange = () => { limit = 20; showEvidence(); };
  dateSelect.onchange = () => {
    const unknown = dateSelect.value === 'undated';
    selectPeriod(unknown ? active : Number(dateSelect.value), selectedMetric(), unknown);
  };
  unknownButton.onclick = () => {
    const metric = comparing ? comparisonMetric.value : HEAT_KEYS.find(key => undated.some(event => event.metrics.includes(key)));
    selectPeriod(active, metric || 'discussion', true);
  };
  more.onclick = () => { limit += 20; showEvidence(); };
  updateProducts();
  refresh();
  new ResizeObserver(draw).observe(chart);
}
