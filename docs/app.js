const state = {
  snapshot: null,
  query: "",
  flow: "all",
  metric: "amount_delta_100m",
  category: "all",
  sortWindow: "1D",
  sortDir: "desc",
  trendRange: "3M",
  flowWindow: "1D",
  flowMetric: "amount",
  grouping: "category",
  trendsByCode: {},
};

// 分类对比图的三个维度：资金流（窗口相关）、涨跌幅（窗口相关，板块内规模加权）、规模（时点值）。
const FLOW_METRICS = {
  amount: { label: "资金流", windowed: true, digits: 1, note: "板块内 ETF 金额净流入合计，亿元。" },
  return: { label: "涨跌幅", windowed: true, digits: 2, note: "板块内 ETF 区间涨跌幅，按规模加权平均，%。" },
  scale: { label: "规模", windowed: false, digits: 0, note: "板块内 ETF 最新规模合计，亿元。" },
};

const TREND_RANGES = [
  { key: "1M", label: "1月", days: 30 },
  { key: "3M", label: "3月", days: 90 },
  { key: "6M", label: "6月", days: 180 },
  { key: "YTD", label: "今年", ytd: true },
  { key: "12M", label: "12月", days: 365 },
];

const CATEGORY_COLORS = {
  宽基: "#58c7dd",
  科技: "#b487f0",
  债券: "#f1b64a",
  金融: "#5b9cf5",
  商品: "#e8927c",
  红利: "#d16ba5",
  医药: "#67c587",
  货币: "#9aa7a1",
  行业主题: "#8fa3b0",
  未分类: "#6f7a75",
};

// 细分子类配色，供分组下钻时使用。
const SUBCATEGORY_COLORS = {
  // 红利
  宽口径红利: "#d16ba5",
  红利低波: "#e8927c",
  国企央企红利: "#c78ae0",
  港股红利: "#e5b567",
  红利质量: "#9b8bd6",
  // 科技（半导体细分：设备/科创芯片/芯片半导体）
  半导体设备: "#b487f0",
  科创芯片: "#8f6fd6",
  芯片半导体: "#c9a0ff",
  通信: "#58c7dd",
  人工智能: "#f0857d",
  软件计算机: "#7fd1b9",
  电子: "#e5b567",
  互联网科技: "#5b9cf5",
  // 宽基
  沪深300: "#58c7dd",
  中证500: "#7fd1b9",
  中证1000: "#5b9cf5",
  上证50: "#67c587",
  创业板: "#b487f0",
  科创板: "#c78ae0",
  中证A500: "#e8927c",
  中证A50: "#f0b46a",
  深证100: "#e5b567",
  双创: "#9b8bd6",
  // 债券
  利率债: "#f1b64a",
  信用债: "#e8927c",
  科创债: "#c78ae0",
  可转债: "#58c7dd",
  短融: "#7fd1b9",
};

const FALLBACK_COLORS = ["#7fd1b9", "#c9a0ff", "#f5a3b5", "#a3c9f5", "#f5d76e"];

function categoryColor(key, index = 0) {
  return CATEGORY_COLORS[key] || SUBCATEGORY_COLORS[key] || FALLBACK_COLORS[index % FALLBACK_COLORS.length];
}

// 分组维度：state.grouping === "category" 时按板块；否则钻取到某板块的子类。
function groupKeyOf(row) {
  if (state.grouping === "category") return row.category || "未分类";
  return row.subcategory || row.category || "未分类";
}

function rowsForGrouping(rows) {
  if (state.grouping === "category") return rows;
  return rows.filter((row) => row.category === state.grouping);
}

const CATEGORY_ORDER = ["宽基", "科技", "红利", "债券", "金融", "医药", "商品", "行业主题"];

// 可用分组选项：板块（默认）+ 数据里子类 ≥2 的板块。
function availableGroupings(snapshot) {
  const subcatsByCategory = {};
  for (const row of snapshot.rows) {
    const category = row.category || "未分类";
    (subcatsByCategory[category] ||= new Set()).add(row.subcategory || category);
  }
  const drilldowns = Object.entries(subcatsByCategory)
    .filter(([, subs]) => subs.size >= 2)
    .map(([category]) => category)
    .sort((a, b) => CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b));
  return [{ key: "category", label: "板块" }, ...drilldowns.map((category) => ({ key: category, label: `${category}细分` }))];
}

const embeddedSnapshot = window.__ETF_SNAPSHOT__ || null;

const metricLabels = {
  amount_delta_100m: "亿元",
  share_delta_yi: "亿份",
  return_pct: "%",
};

const metricSummary = {
  amount_delta_100m: "金额",
  share_delta_yi: "份额",
  return_pct: "涨跌幅",
};

// 快照地址：Pages 站点用同目录 JSON（window.__SNAPSHOT_URL__），本地开发用 ../data。
const SNAPSHOT_URL = window.__SNAPSHOT_URL__ || "../data/dashboard_snapshot.json";

async function loadSnapshot() {
  if (embeddedSnapshot) {
    state.snapshot = embeddedSnapshot;
    indexTrends();
    render();
    return;
  }
  const response = await fetch(SNAPSHOT_URL, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`无法读取 dashboard_snapshot.json: ${response.status}`);
  }
  state.snapshot = await response.json();
  indexTrends();
  render();
}

const AUTO_REFRESH_INTERVAL_MS = 5 * 60 * 1000;
let autoRefreshTimer = null;

async function checkForNewSnapshot() {
  try {
    const response = await fetch(SNAPSHOT_URL, { cache: "no-store" });
    if (!response.ok) return;
    const fresh = await response.json();
    if (fresh?.meta?.generated_at && fresh.meta.generated_at !== state.snapshot?.meta?.generated_at) {
      state.snapshot = fresh;
      indexTrends();
      render();
    }
  } catch (error) {
    // 自动检查失败保持静默，下个周期再试；手动刷新仍会报错。
  }
}

function setAutoRefresh(enabled) {
  clearInterval(autoRefreshTimer);
  autoRefreshTimer = null;
  if (enabled) {
    autoRefreshTimer = setInterval(checkForNewSnapshot, AUTO_REFRESH_INTERVAL_MS);
  }
}

function initAutoRefresh() {
  const toggle = document.getElementById("autoToggle");
  const input = document.getElementById("autoRefreshInput");
  if (embeddedSnapshot) {
    // 单文件版数据内嵌，没有可轮询的数据源。
    toggle.hidden = true;
    return;
  }
  input.addEventListener("change", () => setAutoRefresh(input.checked));
  setAutoRefresh(input.checked);
}

function indexTrends() {
  state.trendsByCode = {};
  for (const trend of state.snapshot?.trends || []) {
    state.trendsByCode[trend.code] = trend;
  }
}

function formatNumber(value, digits = 1, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Number(value).toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}${suffix}`;
}

function formatPlain(value, digits = 0, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `${Number(value).toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}${suffix}`;
}

function render() {
  const snapshot = state.snapshot;
  if (!snapshot) return;
  if (!state.sortWindow) state.sortWindow = snapshot.windows[0].key;
  renderFreshness(snapshot);
  renderKpis(snapshot);
  renderDailyChanges(snapshot);
  renderCharts(snapshot);
  renderControls(snapshot);
  renderTable(snapshot);
  renderSources(snapshot);
}

const DEFAULT_STALE_AFTER_TRADING_DAYS = 3;

// 数据日到今天之间的交易日数（跳过周末），as_of 与今天都不计入。
// 用交易日而非日历日，避免正常周末让周一误报滞后。
function tradingDaysBehind(asOfIso, today = new Date()) {
  const cursor = new Date(`${asOfIso}T00:00:00`);
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  if (Number.isNaN(cursor.getTime())) return 0;
  let count = 0;
  cursor.setDate(cursor.getDate() + 1);
  while (cursor < end) {
    const weekday = cursor.getDay();
    if (weekday !== 0 && weekday !== 6) count += 1;
    cursor.setDate(cursor.getDate() + 1);
  }
  return count;
}

function formatGeneratedAt(iso) {
  if (!iso) return "--";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// 快照重建至今的自然日数；无法解析时返回 Infinity（视作管线已停）。
function generatedAgeInDays(iso, now = new Date()) {
  if (!iso) return Infinity;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return Infinity;
  return (now.getTime() - parsed.getTime()) / 86400000;
}

function renderFreshness(snapshot) {
  const meta = snapshot.meta || {};
  const statusText = meta.status === "fixture" ? "示例数据" : "公开数据";
  const generated = formatGeneratedAt(meta.generated_at);
  const threshold = meta.stale_after_trading_days || DEFAULT_STALE_AFTER_TRADING_DAYS;
  const lag = meta.as_of ? tradingDaysBehind(meta.as_of) : 0;
  // 组合判据：数据日滞后 且 快照本身也超过阈值天数没重建，才判为真滞后。
  // 长假期间只要定时任务在跑（generated_at 是新的），就不会误报。
  const pipelineStale = generatedAgeInDays(meta.generated_at) >= threshold;
  const stale = lag >= threshold && pipelineStale;
  const element = document.getElementById("freshness");
  const base = `${statusText} · 数据日 ${meta.as_of || "--"} · 生成 ${generated}`;
  element.innerHTML = stale
    ? `${base} <span class="stale-badge" title="数据日已滞后，且快照超过 ${threshold} 天未重建">⚠ 数据滞后 ${lag} 个交易日</span>`
    : base;
  element.classList.toggle("stale", stale);
}

function renderKpis(snapshot) {
  const summary = snapshot.summary || {};
  const cards = [
    ["ETF 数量", formatPlain(summary.etf_count, 0, " 只"), "A 股场内 ETF"],
    ["合计规模", formatPlain(summary.total_scale_100m, 0, " 亿元"), "按最新份额 × 最新价估算"],
    ["今日净流入", formatNumber(summary.flow_1d_100m, 1, " 亿元"), "份额变化估算"],
    ["近 1 周净流入", formatNumber(summary.flow_1w_100m, 1, " 亿元"), "份额变化估算"],
  ];
  document.getElementById("kpiGrid").innerHTML = cards
    .map(([label, value, note]) => `<article class="kpi"><span>${label}</span><strong>${value}</strong><small>${note}</small></article>`)
    .join("");
}

// 「较昨日变化」= 最近 1 个交易日（1D 窗口）的当日看点：领涨/领跌、净申赎最多。
function renderDailyChanges(snapshot) {
  const section = document.getElementById("dailySection");
  const rows = snapshot.rows || [];
  const val1d = (row, key) => row.windows?.["1D"]?.[key];
  const withReturn = rows.filter((row) => Number.isFinite(val1d(row, "return_pct")));
  const withFlow = rows.filter((row) => Number.isFinite(val1d(row, "amount_delta_100m")));
  if (withReturn.length === 0 && withFlow.length === 0) {
    section.hidden = true;
    return;
  }
  section.hidden = false;

  const anchor = snapshot.rows.find((row) => row.windows?.["1D"]?.price_anchor_date)?.windows?.["1D"]?.price_anchor_date;
  document.getElementById("dailyDate").textContent = anchor ? `对比基准 ${anchor}` : "最近 1 个交易日";

  const pickMax = (list, key) => list.reduce((best, row) => (val1d(row, key) > val1d(best, key) ? row : best), list[0]);
  const pickMin = (list, key) => list.reduce((best, row) => (val1d(row, key) < val1d(best, key) ? row : best), list[0]);

  const tiles = [];
  if (withReturn.length) {
    const up = pickMax(withReturn, "return_pct");
    const down = pickMin(withReturn, "return_pct");
    tiles.push(dailyTile("今日领涨", up, formatNumber(val1d(up, "return_pct"), 2, "%"), "up", up.subcategory));
    tiles.push(dailyTile("今日领跌", down, formatNumber(val1d(down, "return_pct"), 2, "%"), "down", down.subcategory));
  }
  if (withFlow.length) {
    const inflow = pickMax(withFlow, "amount_delta_100m");
    const outflow = pickMin(withFlow, "amount_delta_100m");
    tiles.push(dailyTile("净申购最多", inflow, formatNumber(val1d(inflow, "amount_delta_100m"), 1, " 亿"), "up", "较昨日申购"));
    tiles.push(dailyTile("净赎回最多", outflow, formatNumber(val1d(outflow, "amount_delta_100m"), 1, " 亿"), "down", "较昨日赎回"));
  }
  document.getElementById("dailyGrid").innerHTML = tiles.join("");
}

function dailyTile(label, row, value, dir, sub) {
  return `<article class="daily-tile">
    <span class="tile-label">${label}</span>
    <span class="tile-name" title="${escapeHtml(row.name)}">${escapeHtml(row.name)}</span>
    <span class="tile-value ${dir}">${value}</span>
    <span class="tile-sub">${escapeHtml(row.code)}${sub ? ` · ${escapeHtml(sub)}` : ""}</span>
  </article>`;
}

function trendCutoffIso(snapshot, rangeKey) {
  const asOf = new Date(`${snapshot.meta.as_of}T00:00:00Z`);
  const range = TREND_RANGES.find((item) => item.key === rangeKey) || TREND_RANGES[1];
  if (range.ytd) return `${asOf.getUTCFullYear()}-01-01`;
  const cutoff = new Date(asOf);
  cutoff.setUTCDate(cutoff.getUTCDate() - range.days);
  return cutoff.toISOString().slice(0, 10);
}

// 板块等权合成指数：每日收益取有连续报价成员的平均，再从 100 起累乘。
// 新上市成员从其有数据的第一天开始参与，不影响之前的走势。
function computeCategorySeries(snapshot, rangeKey) {
  const cutoff = trendCutoffIso(snapshot, rangeKey);
  const members = new Map();
  const dateSet = new Set();
  for (const row of rowsForGrouping(snapshot.rows)) {
    const trend = state.trendsByCode[row.code];
    if (!trend) continue;
    const priceByDate = {};
    for (let i = 0; i < trend.dates.length; i += 1) {
      if (trend.dates[i] >= cutoff) {
        priceByDate[trend.dates[i]] = trend.closes[i];
        dateSet.add(trend.dates[i]);
      }
    }
    if (Object.keys(priceByDate).length < 2) continue;
    const group = groupKeyOf(row);
    if (!members.has(group)) members.set(group, []);
    members.get(group).push(priceByDate);
  }
  const dates = Array.from(dateSet).sort();
  if (dates.length < 2) return { dates: [], series: [] };

  const series = [];
  for (const [category, priceMaps] of members) {
    const values = new Array(dates.length).fill(null);
    let level = null;
    for (let i = 0; i < dates.length; i += 1) {
      const returns = [];
      if (i > 0) {
        for (const priceByDate of priceMaps) {
          const current = priceByDate[dates[i]];
          const previous = priceByDate[dates[i - 1]];
          if (current !== undefined && previous !== undefined && previous !== 0) {
            returns.push(current / previous - 1);
          }
        }
      }
      const hasQuote = priceMaps.some((priceByDate) => priceByDate[dates[i]] !== undefined);
      if (level === null) {
        if (hasQuote) level = 100;
      } else if (returns.length > 0) {
        level *= 1 + returns.reduce((sum, item) => sum + item, 0) / returns.length;
      }
      values[i] = level;
    }
    series.push({ category, values, count: priceMaps.length });
  }
  series.sort((a, b) => (b.values.at(-1) ?? 0) - (a.values.at(-1) ?? 0));
  return { dates, series };
}

function renderCharts(snapshot) {
  const section = document.querySelector(".charts");
  if (!section) return;
  if (!snapshot.trends || snapshot.trends.length === 0) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  renderGroupingChips(snapshot);
  renderTrendChips(snapshot);
  renderTrendChart(snapshot);
  renderFlowChips(snapshot);
  renderFlowChart(snapshot);
}

function renderGroupingChips(snapshot) {
  const groupings = availableGroupings(snapshot);
  if (!groupings.some((item) => item.key === state.grouping)) state.grouping = "category";
  document.getElementById("groupingChips").innerHTML = groupings
    .map((item) => `<button type="button" data-group="${item.key}" class="${item.key === state.grouping ? "active" : ""}">${item.label}</button>`)
    .join("");
}

function renderTrendChips(snapshot) {
  document.getElementById("trendRange").innerHTML = TREND_RANGES.map(
    (range) => `<button type="button" data-range="${range.key}" class="${range.key === state.trendRange ? "active" : ""}">${range.label}</button>`,
  ).join("");
}

function renderTrendChart(snapshot) {
  const svg = document.getElementById("trendChart");
  const body = document.getElementById("trendBody");
  const width = Math.max(body.clientWidth || 960, 320);
  const height = 300;
  const margin = { top: 14, right: 16, bottom: 28, left: 50 };
  const { dates, series } = computeCategorySeries(snapshot, state.trendRange);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  if (dates.length < 2 || series.length === 0) {
    svg.innerHTML = `<text x="${width / 2}" y="${height / 2}" fill="#6f7a75" text-anchor="middle">当前区间暂无走势数据</text>`;
    document.getElementById("trendLegend").innerHTML = "";
    return;
  }

  const allValues = series.flatMap((item) => item.values.filter((value) => value !== null));
  let minValue = Math.min(...allValues);
  let maxValue = Math.max(...allValues);
  const pad = Math.max((maxValue - minValue) * 0.08, 0.5);
  minValue -= pad;
  maxValue += pad;

  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const xAt = (index) => margin.left + (index / (dates.length - 1)) * plotWidth;
  const yAt = (value) => margin.top + (1 - (value - minValue) / (maxValue - minValue)) * plotHeight;

  const parts = [];
  const tickCount = 5;
  for (let i = 0; i < tickCount; i += 1) {
    const value = minValue + ((maxValue - minValue) * i) / (tickCount - 1);
    const y = yAt(value);
    parts.push(`<line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" stroke="#2a312f" stroke-width="1"/>`);
    const pct = value - 100;
    parts.push(`<text x="${margin.left - 8}" y="${y + 4}" fill="#9aa7a1" font-size="11" text-anchor="end">${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%</text>`);
  }
  if (100 >= minValue && 100 <= maxValue) {
    const y = yAt(100);
    parts.push(`<line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" stroke="#4a534f" stroke-width="1" stroke-dasharray="4 4"/>`);
  }
  const xTickCount = Math.min(6, dates.length);
  for (let i = 0; i < xTickCount; i += 1) {
    const index = Math.round((i / (xTickCount - 1)) * (dates.length - 1));
    const x = xAt(index);
    parts.push(`<text x="${x}" y="${height - 8}" fill="#9aa7a1" font-size="11" text-anchor="middle">${dates[index].slice(5)}</text>`);
  }

  series.forEach((item, seriesIndex) => {
    const color = categoryColor(item.category, seriesIndex);
    let path = "";
    let pen = false;
    for (let i = 0; i < item.values.length; i += 1) {
      if (item.values[i] === null) {
        pen = false;
        continue;
      }
      path += `${pen ? "L" : "M"}${xAt(i).toFixed(1)},${yAt(item.values[i]).toFixed(1)}`;
      pen = true;
    }
    parts.push(`<path d="${path}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`);
  });

  parts.push(`<line id="trendCrosshair" x1="0" y1="${margin.top}" x2="0" y2="${height - margin.bottom}" stroke="#77d8eb" stroke-width="1" visibility="hidden"/>`);
  parts.push(`<rect id="trendHover" x="${margin.left}" y="${margin.top}" width="${plotWidth}" height="${plotHeight}" fill="transparent"/>`);
  svg.innerHTML = parts.join("");

  document.getElementById("trendLegend").innerHTML = series
    .map((item, index) => {
      const last = item.values.at(-1);
      const pct = last === null ? "--" : `${last - 100 >= 0 ? "+" : ""}${(last - 100).toFixed(1)}%`;
      return `<span class="legend-item"><span class="swatch" style="background:${categoryColor(item.category, index)}"></span>${escapeHtml(item.category)}（${item.count} 只）${pct}</span>`;
    })
    .join("");

  attachTrendHover(svg, { dates, series, xAt, margin, plotWidth, width });
}

function attachTrendHover(svg, context) {
  const hover = svg.querySelector("#trendHover");
  const crosshair = svg.querySelector("#trendCrosshair");
  const tooltip = document.getElementById("trendTooltip");
  const body = document.getElementById("trendBody");
  if (!hover) return;

  const onMove = (event) => {
    const rect = svg.getBoundingClientRect();
    const scaleX = context.width / rect.width;
    const x = (event.clientX - rect.left) * scaleX;
    const ratio = Math.min(Math.max((x - context.margin.left) / context.plotWidth, 0), 1);
    const index = Math.round(ratio * (context.dates.length - 1));
    const snapX = context.xAt(index);
    crosshair.setAttribute("x1", snapX);
    crosshair.setAttribute("x2", snapX);
    crosshair.setAttribute("visibility", "visible");

    const rows = context.series
      .filter((item) => item.values[index] !== null)
      .map((item, itemIndex) => {
        const value = item.values[index] - 100;
        return `<div class="tip-row"><span class="tip-label"><span class="swatch" style="background:${categoryColor(item.category, itemIndex)}"></span>${escapeHtml(item.category)}</span><strong>${value >= 0 ? "+" : ""}${value.toFixed(2)}%</strong></div>`;
      })
      .join("");
    tooltip.innerHTML = `<div class="tip-date">${context.dates[index]}</div>${rows}`;
    tooltip.hidden = false;
    const bodyRect = body.getBoundingClientRect();
    const pixelX = snapX / scaleX;
    const flip = pixelX > bodyRect.width * 0.62;
    tooltip.style.left = flip ? `${pixelX - tooltip.offsetWidth - 14}px` : `${pixelX + 14}px`;
    tooltip.style.top = "10px";
  };

  hover.addEventListener("mousemove", onMove);
  hover.addEventListener("mouseleave", () => {
    tooltip.hidden = true;
    crosshair.setAttribute("visibility", "hidden");
  });
}

function renderFlowChips(snapshot) {
  document.getElementById("flowMetricChips").innerHTML = Object.entries(FLOW_METRICS)
    .map(([key, meta]) => `<button type="button" data-metric="${key}" class="${key === state.flowMetric ? "active" : ""}">${meta.label}</button>`)
    .join("");

  if (!snapshot.windows.some((item) => item.key === state.flowWindow)) {
    state.flowWindow = snapshot.windows[0].key;
  }
  const windowed = FLOW_METRICS[state.flowMetric].windowed;
  document.getElementById("flowWindowChips").parentElement.hidden = !windowed;
  document.getElementById("flowWindowChips").innerHTML = snapshot.windows
    .map((item) => `<button type="button" data-window="${item.key}" class="${item.key === state.flowWindow ? "active" : ""}">${item.label.replace("最近", "")}</button>`)
    .join("");
  document.getElementById("flowNote").textContent = FLOW_METRICS[state.flowMetric].note;
}

// 按当前分组维度聚合对比指标：资金流求和、规模求和、涨跌幅按规模加权平均。
function categoryComparisonEntries(snapshot) {
  const metric = state.flowMetric;
  const rows = rowsForGrouping(snapshot.rows);
  if (metric === "scale") {
    const totals = new Map();
    for (const row of rows) {
      if (row.scale_100m === null || row.scale_100m === undefined) continue;
      totals.set(groupKeyOf(row), (totals.get(groupKeyOf(row)) || 0) + row.scale_100m);
    }
    return Array.from(totals.entries());
  }
  if (metric === "return") {
    const acc = new Map(); // group -> {weighted, weight}
    for (const row of rows) {
      const ret = row.windows?.[state.flowWindow]?.return_pct;
      const weight = row.scale_100m;
      if (ret === null || ret === undefined || !weight) continue;
      const group = groupKeyOf(row);
      const prev = acc.get(group) || { weighted: 0, weight: 0 };
      acc.set(group, { weighted: prev.weighted + ret * weight, weight: prev.weight + weight });
    }
    return Array.from(acc.entries()).map(([group, { weighted, weight }]) => [group, weight ? weighted / weight : 0]);
  }
  const totals = new Map();
  for (const row of rows) {
    const value = row.windows?.[state.flowWindow]?.amount_delta_100m;
    if (value === null || value === undefined) continue;
    totals.set(groupKeyOf(row), (totals.get(groupKeyOf(row)) || 0) + value);
  }
  return Array.from(totals.entries());
}

function renderFlowChart(snapshot) {
  const svg = document.getElementById("flowChart");
  const container = svg.closest(".chart-body");
  const width = Math.max(container.clientWidth || 460, 280);
  const meta = FLOW_METRICS[state.flowMetric];
  const entries = categoryComparisonEntries(snapshot).sort((a, b) => b[1] - a[1]);
  const rowHeight = 36;
  const margin = { top: 8, right: 70, bottom: 8, left: 92 };
  const height = Math.max(entries.length * rowHeight + margin.top + margin.bottom, 120);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.style.height = `${height}px`;
  if (entries.length === 0) {
    svg.innerHTML = `<text x="${width / 2}" y="${height / 2}" fill="#6f7a75" text-anchor="middle">当前维度暂无数据</text>`;
    return;
  }

  const suffix = state.flowMetric === "return" ? "%" : "";

  const plotWidth = width - margin.left - margin.right;
  const minValue = Math.min(...entries.map(([, value]) => value), 0);
  const maxValue = Math.max(...entries.map(([, value]) => value), 0);
  const scale = plotWidth / (maxValue - minValue || 1);
  const zero = margin.left + (0 - minValue) * scale;

  const divergent = state.flowMetric !== "scale";
  const parts = divergent
    ? [`<line x1="${zero}" y1="${margin.top}" x2="${zero}" y2="${height - margin.bottom}" stroke="#4a534f" stroke-width="1"/>`]
    : [];
  entries.forEach(([category, value], index) => {
    const y = margin.top + index * rowHeight;
    const barY = y + 8;
    const barHeight = rowHeight - 16;
    const barX = value >= 0 ? zero : zero + value * scale;
    const barWidth = Math.max(Math.abs(value) * scale, 1);
    const color = divergent ? (value >= 0 ? "#dc6b74" : "#54b88d") : categoryColor(category, index);
    const signPrefix = divergent && value >= 0 ? "+" : "";
    parts.push(`<text x="${margin.left - 8}" y="${y + rowHeight / 2 + 4}" fill="#f3f7f4" font-size="13" text-anchor="end">${escapeHtml(category)}</text>`);
    parts.push(`<rect x="${barX}" y="${barY}" width="${barWidth}" height="${barHeight}" rx="3" fill="${color}" fill-opacity="0.82"/>`);
    let labelX = value >= 0 ? zero + Math.abs(value) * scale + 6 : zero - Math.abs(value) * scale - 6;
    let anchor = value >= 0 ? "start" : "end";
    if (value < 0 && labelX < margin.left + 40) {
      labelX = zero + 6;
      anchor = "start";
    }
    parts.push(`<text x="${labelX}" y="${y + rowHeight / 2 + 4}" fill="${color}" font-size="12" font-weight="700" text-anchor="${anchor}">${signPrefix}${value.toFixed(meta.digits)}${suffix}</text>`);
  });
  svg.innerHTML = parts.join("");
}

function renderControls(snapshot) {
  const categories = ["all", ...Array.from(new Set(snapshot.rows.map((row) => row.category || "未分类"))).sort()];
  const category = document.getElementById("categorySelect");
  category.innerHTML = categories.map((item) => `<option value="${item}">${item === "all" ? "全部" : item}</option>`).join("");
  category.value = state.category;

  const sortWindow = document.getElementById("sortWindow");
  sortWindow.innerHTML = snapshot.windows.map((windowItem) => `<option value="${windowItem.key}">${windowItem.label}</option>`).join("");
  sortWindow.value = state.sortWindow;

  document.querySelectorAll("#flowFilter button").forEach((button) => {
    button.classList.toggle("active", button.dataset.flow === state.flow);
  });
  document.querySelectorAll("#metricMode button").forEach((button) => {
    button.classList.toggle("active", button.dataset.metric === state.metric);
  });
  document.getElementById("sortDirection").textContent = state.sortDir === "desc" ? "降序" : "升序";
  document.getElementById("sortDirection").dataset.dir = state.sortDir;
}

function filteredRows(snapshot) {
  const query = state.query.trim().toLowerCase();
  const rows = snapshot.rows.filter((row) => {
    const windowMetric = row.windows?.[state.sortWindow]?.amount_delta_100m;
    if (state.flow === "inflow" && !(windowMetric > 0)) return false;
    if (state.flow === "outflow" && !(windowMetric < 0)) return false;
    if (state.category !== "all" && row.category !== state.category) return false;
    if (!query) return true;
    return `${row.name} ${row.code} ${row.manager || ""} ${row.category || ""}`.toLowerCase().includes(query);
  });

  rows.sort((a, b) => {
    const av = a.windows?.[state.sortWindow]?.[state.metric];
    const bv = b.windows?.[state.sortWindow]?.[state.metric];
    const left = av === null || av === undefined ? Number.NEGATIVE_INFINITY : av;
    const right = bv === null || bv === undefined ? Number.NEGATIVE_INFINITY : bv;
    return state.sortDir === "desc" ? right - left : left - right;
  });
  return rows;
}

function renderTable(snapshot) {
  const rows = filteredRows(snapshot);
  document.getElementById("rowCount").textContent = `${rows.length} / ${snapshot.rows.length} 只`;
  const hasTrends = Boolean(snapshot.trends && snapshot.trends.length);
  document.getElementById("tableHead").innerHTML = `
    <tr>
      <th class="rank">#</th>
      <th class="name-cell">基金名称</th>
      <th class="scale">规模</th>
      ${hasTrends ? '<th class="spark">近3月走势</th>' : ""}
      ${snapshot.windows.map((windowItem) => `<th class="heat">${windowItem.label}</th>`).join("")}
    </tr>
  `;

  const maxByWindow = {};
  snapshot.windows.forEach((windowItem) => {
    const values = rows
      .map((row) => Math.abs(row.windows?.[windowItem.key]?.[state.metric] ?? 0))
      .filter((value) => value > 0);
    maxByWindow[windowItem.key] = Math.max(...values, 1);
  });

  document.getElementById("tableBody").innerHTML = rows
    .map((row, index) => {
      const cells = snapshot.windows.map((windowItem) => renderHeatCell(row, windowItem, maxByWindow[windowItem.key])).join("");
      return `
        <tr>
          <td class="rank">${String(index + 1).padStart(2, "0")}</td>
          <td class="name-cell">
            <div class="fund-name">
              <strong title="${escapeHtml(row.name)}">${escapeHtml(row.name)}</strong>
              ${row.tag ? `<span class="tag">${escapeHtml(row.tag)}</span>` : ""}
            </div>
            <div class="code">${row.code} · ${row.category || "未分类"}</div>
          </td>
          <td class="scale">${formatPlain(row.scale_100m, 0)}</td>
          ${hasTrends ? `<td class="spark">${renderSparkline(row.code)}</td>` : ""}
          ${cells}
        </tr>
      `;
    })
    .join("");
}

function renderSparkline(code) {
  const trend = state.trendsByCode[code];
  if (!trend || trend.closes.length < 2) return '<span class="empty">--</span>';
  const closes = trend.closes.slice(-63);
  const width = 116;
  const height = 38;
  const padding = 3;
  const minClose = Math.min(...closes);
  const maxClose = Math.max(...closes);
  const span = maxClose - minClose || 1;
  const points = closes
    .map((close, index) => {
      const x = padding + (index / (closes.length - 1)) * (width - padding * 2);
      const y = padding + (1 - (close - minClose) / span) * (height - padding * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const up = closes.at(-1) >= closes[0];
  const color = up ? "#dc6b74" : "#54b88d";
  return `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true"><polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.6" stroke-linejoin="round"/></svg>`;
}

function renderHeatCell(row, windowItem, maxValue) {
  const metric = row.windows?.[windowItem.key];
  if (!metric || metric[state.metric] === null || metric[state.metric] === undefined) {
    return `<td class="heat empty"><strong>--</strong><span>--</span></td>`;
  }
  const value = metric[state.metric];
  const amount = metric.amount_delta_100m;
  const intensity = Math.min(Math.abs(value) / maxValue, 1);
  const color = value >= 0 ? [220, 107, 116] : [84, 184, 141];
  const alpha = 0.13 + intensity * 0.58;
  const suffix = metricLabels[state.metric];
  const valueDigits = state.metric === "return_pct" ? 1 : 1;
  const sub = state.metric === "return_pct"
    ? formatNumber(amount, 1, " 亿")
    : formatNumber(metric.return_pct, 1, "%");
  const className = value >= 0 ? "positive" : "negative";
  return `
    <td class="heat" style="background: rgba(${color[0]}, ${color[1]}, ${color[2]}, ${alpha})">
      <strong class="${className}">${formatNumber(value, valueDigits, state.metric === "return_pct" ? "%" : "")}</strong>
      <span>${metricSummary[state.metric]} · ${suffix}${sub === "--" ? "" : ` · ${sub}`}</span>
    </td>
  `;
}

function renderSources(snapshot) {
  const items = snapshot.sources || [];
  document.getElementById("sources").innerHTML = items
    .map((source) => {
      const label = escapeHtml(source.label || "来源");
      if (source.href) return `<a href="${source.href}" target="_blank" rel="noreferrer">${label}</a>`;
      return `<span>${label}</span>`;
    })
    .join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

document.getElementById("searchInput").addEventListener("input", (event) => {
  state.query = event.target.value;
  renderTable(state.snapshot);
});

document.getElementById("flowFilter").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-flow]");
  if (!button) return;
  state.flow = button.dataset.flow;
  render();
});

document.getElementById("metricMode").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-metric]");
  if (!button) return;
  state.metric = button.dataset.metric;
  render();
});

document.getElementById("categorySelect").addEventListener("change", (event) => {
  state.category = event.target.value;
  renderTable(state.snapshot);
});

document.getElementById("sortWindow").addEventListener("change", (event) => {
  state.sortWindow = event.target.value;
  renderTable(state.snapshot);
});

document.getElementById("sortDirection").addEventListener("click", () => {
  state.sortDir = state.sortDir === "desc" ? "asc" : "desc";
  render();
});

document.getElementById("refreshButton").addEventListener("click", () => {
  loadSnapshot().catch(showError);
});

document.getElementById("trendRange").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-range]");
  if (!button) return;
  state.trendRange = button.dataset.range;
  renderCharts(state.snapshot);
});

document.getElementById("groupingChips").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-group]");
  if (!button) return;
  state.grouping = button.dataset.group;
  renderCharts(state.snapshot);
});

document.getElementById("flowMetricChips").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-metric]");
  if (!button) return;
  state.flowMetric = button.dataset.metric;
  renderCharts(state.snapshot);
});

document.getElementById("flowWindowChips").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-window]");
  if (!button) return;
  state.flowWindow = button.dataset.window;
  renderCharts(state.snapshot);
});

let chartResizeTimer = null;
window.addEventListener("resize", () => {
  if (!state.snapshot) return;
  clearTimeout(chartResizeTimer);
  chartResizeTimer = setTimeout(() => renderCharts(state.snapshot), 160);
});

function showError(error) {
  document.querySelector(".shell").insertAdjacentHTML(
    "beforeend",
    `<div class="error">${escapeHtml(error.message)}</div>`,
  );
}

initAutoRefresh();
loadSnapshot().catch(showError);
