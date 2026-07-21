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
  rotationWindow: "1W",
  quadrantWindow: "1W",
  pressureFilter: "all",
  pressureSort: "change_amount",
  selectedPressureCode: null,
  trendsByCode: {},
};

// β压强表的排序维度：变动金额/今日变动按绝对值降序（最大变动），其余按数值降序。
const PRESSURE_SORTS = {
  change_amount: { label: "变动金额", keys: ["change_amount_100m", "today_change_amount_100m"], abs: true },
  today_change: { label: "今日变动", keys: ["today_change_wan_shares", "position_change_wan_shares", "change_wan_shares"], abs: true },
  margin: { label: "融资余额", keys: ["margin_balance_100m"], abs: false },
  short: { label: "融券余额", keys: ["short_balance_100m"], abs: false },
  etf_count: { label: "ETF 数量", keys: ["linked_etf_count"], abs: false },
  float_mv: { label: "流通市值", keys: ["float_market_value_100m"], abs: false },
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
  大盘宽基: "#58c7dd",
  创业科创: "#6fa8f5",
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

const CATEGORY_ORDER = ["大盘宽基", "创业科创", "宽基", "科技", "红利", "债券", "金融", "医药", "商品", "行业主题"];

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
  renderQuadrantSection(snapshot);
  renderRotation(snapshot);
  renderBetaPressure(snapshot);
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

const BENCHMARK_COLOR = "#a8b8c0";

// 基准指数（沪深300）对齐到图表日期轴并归一为 100，供对照。
function computeBenchmarkSeries(snapshot, dates) {
  const benchmark = snapshot.benchmark;
  if (!benchmark || !benchmark.dates || benchmark.dates.length < 2) return null;
  const closeByDate = {};
  for (let i = 0; i < benchmark.dates.length; i += 1) {
    closeByDate[benchmark.dates[i]] = benchmark.closes[i];
  }
  let base = null;
  const values = dates.map((dateIso) => {
    const close = closeByDate[dateIso];
    if (close === undefined) return null;
    if (base === null) base = close;
    return (close / base) * 100;
  });
  if (values.filter((value) => value !== null).length < 2) return null;
  return { name: benchmark.name || "沪深300指数", values };
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

  const benchmark = computeBenchmarkSeries(snapshot, dates);
  const allValues = series.flatMap((item) => item.values.filter((value) => value !== null));
  if (benchmark) allValues.push(...benchmark.values.filter((value) => value !== null));
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

  if (benchmark) {
    let benchPath = "";
    let benchPen = false;
    for (let i = 0; i < benchmark.values.length; i += 1) {
      if (benchmark.values[i] === null) {
        benchPen = false;
        continue;
      }
      benchPath += `${benchPen ? "L" : "M"}${xAt(i).toFixed(1)},${yAt(benchmark.values[i]).toFixed(1)}`;
      benchPen = true;
    }
    parts.push(`<path d="${benchPath}" fill="none" stroke="${BENCHMARK_COLOR}" stroke-width="1.6" stroke-dasharray="6 4" stroke-linejoin="round"/>`);
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

  const legendItems = series.map((item, index) => {
    const last = item.values.at(-1);
    const pct = last === null ? "--" : `${last - 100 >= 0 ? "+" : ""}${(last - 100).toFixed(1)}%`;
    return `<span class="legend-item"><span class="swatch" style="background:${categoryColor(item.category, index)}"></span>${escapeHtml(item.category)}（${item.count} 只）${pct}</span>`;
  });
  if (benchmark) {
    const last = benchmark.values.filter((value) => value !== null).at(-1);
    const pct = last === undefined ? "--" : `${last - 100 >= 0 ? "+" : ""}${(last - 100).toFixed(1)}%`;
    legendItems.push(
      `<span class="legend-item"><span class="swatch dashed"></span>${escapeHtml(benchmark.name)}（基准）${pct}</span>`,
    );
  }
  document.getElementById("trendLegend").innerHTML = legendItems.join("");

  attachTrendHover(svg, { dates, series, benchmark, xAt, margin, plotWidth, width });
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
    let benchRow = "";
    if (context.benchmark && context.benchmark.values[index] !== null) {
      const value = context.benchmark.values[index] - 100;
      benchRow = `<div class="tip-row"><span class="tip-label"><span class="swatch dashed"></span>${escapeHtml(context.benchmark.name)}</span><strong>${value >= 0 ? "+" : ""}${value.toFixed(2)}%</strong></div>`;
    }
    tooltip.innerHTML = `<div class="tip-date">${context.dates[index]}</div>${rows}${benchRow}`;
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

// 按当前分组聚合某窗口的 资金净流入 / 规模加权涨跌 / 板块规模。象限图与温度计共用。
function groupWindowStats(snapshot, windowKey) {
  const acc = new Map();
  for (const row of rowsForGrouping(snapshot.rows)) {
    const group = groupKeyOf(row);
    const item = acc.get(group) || { group, flow: 0, retNum: 0, retDen: 0, scale: 0 };
    const win = row.windows?.[windowKey] || {};
    if (Number.isFinite(win.amount_delta_100m)) item.flow += win.amount_delta_100m;
    if (Number.isFinite(win.return_pct) && row.scale_100m) {
      item.retNum += win.return_pct * row.scale_100m;
      item.retDen += row.scale_100m;
    }
    if (row.scale_100m) item.scale += row.scale_100m;
    acc.set(group, item);
  }
  return Array.from(acc.values())
    .map((item) => ({
      group: item.group,
      flow: item.flow,
      ret: item.retDen ? item.retNum / item.retDen : null,
      scale: item.scale,
    }))
    .filter((item) => item.ret !== null || item.flow !== 0);
}

// 板块级(固定 category 口径)资金流；供环比与温度计使用。
function categoryFlows(snapshot, windowKey) {
  const acc = new Map();
  for (const row of snapshot.rows) {
    const value = row.windows?.[windowKey]?.amount_delta_100m;
    if (!Number.isFinite(value)) continue;
    const cat = row.category || "未分类";
    acc.set(cat, (acc.get(cat) || 0) + value);
  }
  return acc;
}

function renderQuadrantSection(snapshot) {
  const section = document.getElementById("quadrantSection");
  if (!snapshot.rows || snapshot.rows.length === 0) {
    section.hidden = true;
    return;
  }
  if (!snapshot.windows.some((item) => item.key === state.quadrantWindow)) {
    state.quadrantWindow = snapshot.windows[0].key;
  }
  section.hidden = false;
  document.getElementById("quadrantWindowChips").innerHTML = snapshot.windows
    .map((item) => `<button type="button" data-window="${item.key}" class="${item.key === state.quadrantWindow ? "active" : ""}">${item.label.replace("最近", "")}</button>`)
    .join("");
  renderQuadrantChart(snapshot);
  renderRiskGauge(snapshot);
}

const QUADRANT_LABELS = [
  { corner: "tl", text: "抄底 · 跌+流入" },
  { corner: "tr", text: "追高 · 涨+流入" },
  { corner: "bl", text: "撤退 · 跌+流出" },
  { corner: "br", text: "止盈 · 涨+流出" },
];

function renderQuadrantChart(snapshot) {
  const svg = document.getElementById("quadrantChart");
  const body = document.getElementById("quadrantBody");
  const width = Math.max(body.clientWidth || 640, 320);
  const height = 340;
  const margin = { top: 26, right: 24, bottom: 40, left: 62 };
  const stats = groupWindowStats(snapshot, state.quadrantWindow).filter((item) => item.ret !== null);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.style.height = `${height}px`;
  if (stats.length === 0) {
    svg.innerHTML = `<text x="${width / 2}" y="${height / 2}" fill="#6f7a75" text-anchor="middle">当前窗口暂无数据</text>`;
    return;
  }

  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const pad = (values, ratio) => {
    const lo = Math.min(...values, 0);
    const hi = Math.max(...values, 0);
    const span = hi - lo || 1;
    return [lo - span * ratio, hi + span * ratio];
  };
  const [xMin, xMax] = pad(stats.map((item) => item.ret), 0.18);
  const [yMin, yMax] = pad(stats.map((item) => item.flow), 0.18);
  const xAt = (v) => margin.left + ((v - xMin) / (xMax - xMin)) * plotW;
  const yAt = (v) => margin.top + (1 - (v - yMin) / (yMax - yMin)) * plotH;
  const zeroX = xAt(0);
  const zeroY = yAt(0);

  const parts = [];
  // 象限浅色底：流入半区偏红、流出半区偏绿（A 股红涨绿跌习惯）
  parts.push(`<rect x="${margin.left}" y="${margin.top}" width="${plotW}" height="${Math.max(zeroY - margin.top, 0)}" fill="rgba(220,107,116,0.05)"/>`);
  parts.push(`<rect x="${margin.left}" y="${zeroY}" width="${plotW}" height="${Math.max(margin.top + plotH - zeroY, 0)}" fill="rgba(84,184,141,0.05)"/>`);
  parts.push(`<line x1="${margin.left}" y1="${zeroY}" x2="${width - margin.right}" y2="${zeroY}" stroke="#4a534f" stroke-width="1"/>`);
  parts.push(`<line x1="${zeroX}" y1="${margin.top}" x2="${zeroX}" y2="${height - margin.bottom}" stroke="#4a534f" stroke-width="1"/>`);

  for (const { corner, text } of QUADRANT_LABELS) {
    const x = corner.endsWith("l") ? margin.left + 6 : width - margin.right - 6;
    const y = corner.startsWith("t") ? margin.top + 14 : height - margin.bottom - 8;
    const anchor = corner.endsWith("l") ? "start" : "end";
    parts.push(`<text x="${x}" y="${y}" fill="#6f7a75" font-size="11" text-anchor="${anchor}">${text}</text>`);
  }
  parts.push(`<text x="${width - margin.right}" y="${height - 10}" fill="#9aa7a1" font-size="11" text-anchor="end">区间涨跌 % →</text>`);
  parts.push(`<text x="${margin.left - 46}" y="${margin.top + 10}" fill="#9aa7a1" font-size="11">流入</text>`);
  parts.push(`<text x="${margin.left - 46}" y="${height - margin.bottom}" fill="#9aa7a1" font-size="11">流出</text>`);
  parts.push(`<text x="${zeroX + 4}" y="${zeroY - 5}" fill="#6f7a75" font-size="10">0</text>`);

  const maxScale = Math.max(...stats.map((item) => item.scale), 1);
  stats
    .sort((a, b) => b.scale - a.scale)
    .forEach((item, index) => {
      const cx = xAt(item.ret);
      const cy = yAt(item.flow);
      const r = Math.max(7, Math.sqrt(item.scale / maxScale) * 24);
      const color = categoryColor(item.group, index);
      const labelRight = cx < margin.left + plotW * 0.6;
      const lx = labelRight ? cx + r + 6 : cx - r - 6;
      const anchor = labelRight ? "start" : "end";
      parts.push(`<circle cx="${cx}" cy="${cy}" r="${r}" fill="${color}" fill-opacity="0.55" stroke="${color}" stroke-width="1.5"><title>${escapeHtml(item.group)}：${formatNumber(item.ret, 1, "%")}，净流入 ${formatNumber(item.flow, 1, " 亿")}</title></circle>`);
      parts.push(`<text x="${lx}" y="${cy - 2}" fill="#f3f7f4" font-size="12.5" font-weight="700" text-anchor="${anchor}">${escapeHtml(item.group)}</text>`);
      parts.push(`<text x="${lx}" y="${cy + 12}" fill="#9aa7a1" font-size="11" text-anchor="${anchor}">${formatNumber(item.ret, 1, "%")} · ${formatNumber(item.flow, 0, "亿")}</text>`);
    });
  svg.innerHTML = parts.join("");
}

// 避险温度计：价格风格分(成长−防御收益差) 与 资金偏好分(股类−债类净流入) 的均值。
function riskGaugeModel(snapshot) {
  const windowKey = state.quadrantWindow;
  const GROWTH = new Set(["创业科创", "科技"]);
  const DEFENSE = new Set(["红利", "债券"]);
  let growthNum = 0, growthDen = 0, defenseNum = 0, defenseDen = 0;
  for (const row of snapshot.rows) {
    const ret = row.windows?.[windowKey]?.return_pct;
    if (!Number.isFinite(ret) || !row.scale_100m) continue;
    if (GROWTH.has(row.category)) { growthNum += ret * row.scale_100m; growthDen += row.scale_100m; }
    if (DEFENSE.has(row.category)) { defenseNum += ret * row.scale_100m; defenseDen += row.scale_100m; }
  }
  if (!growthDen || !defenseDen) return null;
  const spread = growthNum / growthDen - defenseNum / defenseDen;
  const styleScore = Math.round(50 + 50 * Math.tanh(spread / 8));

  const flows = categoryFlows(snapshot, windowKey);
  let equityFlow = 0, bondFlow = 0;
  for (const [cat, value] of flows) {
    if (cat === "债券") bondFlow += value;
    else equityFlow += value;
  }
  const denom = Math.abs(equityFlow) + Math.abs(bondFlow);
  const flowScore = denom ? Math.round(50 + 50 * ((equityFlow - bondFlow) / denom)) : 50;

  const total = Math.round((styleScore + flowScore) / 2);
  return { total, styleScore, flowScore, spread, equityFlow, bondFlow, diverged: Math.abs(styleScore - flowScore) >= 40 };
}

function gaugeLabelFor(model) {
  if (model.diverged) return "分歧";
  const value = model.total;
  if (value < 20) return "深度避险";
  if (value < 40) return "偏避险";
  if (value <= 60) return "中性";
  if (value <= 80) return "偏进攻";
  return "亢奋";
}

function renderRiskGauge(snapshot) {
  const panel = document.getElementById("gaugePanel");
  const model = riskGaugeModel(snapshot);
  if (!model) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  document.getElementById("gaugeValue").textContent = model.total;
  document.getElementById("gaugeLabel").textContent = gaugeLabelFor(model);
  document.getElementById("gaugeNeedle").style.left = `${Math.min(Math.max(model.total, 1), 99)}%`;

  const compBar = (score) => {
    const color = score >= 50 ? "#dc6b74" : "#54b88d";
    const left = Math.min(score, 50);
    const widthPct = Math.abs(score - 50);
    return `<span class="bar"><i style="left:${left}%;width:${widthPct}%;background:${color}"></i></span>`;
  };
  document.getElementById("gaugeComps").innerHTML = `
    <div class="gauge-comp"><span>价格风格</span>${compBar(model.styleScore)}<strong>${model.styleScore}</strong></div>
    <div class="gauge-comp"><span>资金偏好</span>${compBar(model.flowScore)}<strong>${model.flowScore}</strong></div>
  `;

  const spreadText = `成长−防御收益差 ${formatNumber(model.spread, 1, "%")}`;
  const flowText = `股类净流入 ${formatNumber(model.equityFlow, 0, " 亿")} vs 债类 ${formatNumber(model.bondFlow, 0, " 亿")}`;
  const divergeText = model.diverged
    ? `价格${model.styleScore < 50 ? "避险" : "进攻"}而资金${model.flowScore >= 50 ? "进攻" : "避险"}，两者背离——${model.styleScore < 50 && model.flowScore >= 50 ? "典型的越跌越买（抄底）分歧" : "上涨中资金撤离（止盈）分歧"}。`
    : "价格与资金方向一致。";
  document.getElementById("gaugeNote").textContent = `${spreadText}；${flowText}。${divergeText}实验性指标，仅供观察。`;
}

// 本周较上周的资金流环比：前一周 = 近2周 − 近1周。仅 1W 窗口可精确推导。
function weeklyFlowMomentum(snapshot) {
  const oneWeek = categoryFlows(snapshot, "1W");
  const twoWeek = categoryFlows(snapshot, "2W");
  if (oneWeek.size === 0 || twoWeek.size === 0) return null;
  const result = new Map();
  for (const [cat, current] of oneWeek) {
    if (!twoWeek.has(cat)) continue;
    const prior = twoWeek.get(cat) - current;
    result.set(cat, { current, prior, delta: current - prior });
  }
  return result.size ? result : null;
}

function rotationWindowKey(snapshot) {
  const windows = snapshot.rotation?.windows || {};
  if (windows[state.rotationWindow]) return state.rotationWindow;
  if (windows["1W"]) {
    state.rotationWindow = "1W";
    return "1W";
  }
  const first = Object.keys(windows)[0];
  state.rotationWindow = first || "";
  return state.rotationWindow;
}

function renderRotation(snapshot) {
  const section = document.getElementById("rotationSection");
  const rotation = snapshot.rotation;
  if (!rotation || !rotation.windows || Object.keys(rotation.windows).length === 0) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  const key = rotationWindowKey(snapshot);
  const current = rotation.windows[key];
  const chips = snapshot.windows.filter((item) => rotation.windows[item.key]);
  document.getElementById("rotationWindowChips").innerHTML = chips
    .map((item) => `<button type="button" data-window="${item.key}" class="${item.key === key ? "active" : ""}">${item.label.replace("最近", "")}</button>`)
    .join("");

  const destination = current.largest_destination
    ? `${escapeHtml(current.largest_destination)} ${formatNumber(current.largest_destination_100m, 1, " 亿")}`
    : "--";
  const kpis = [
    ["流出合计", formatNumber(current.outflow_total_100m, 1, " 亿"), "净赎回板块合计", "down"],
    ["流入合计", formatNumber(current.inflow_total_100m, 1, " 亿"), "净申购板块合计", "up"],
    ["净流入", formatNumber(current.net_flow_100m, 1, " 亿"), current.label || key, current.net_flow_100m >= 0 ? "up" : "down"],
    ["最大去向", destination, "净流入最多板块", "up"],
  ];
  document.getElementById("rotationKpis").innerHTML = kpis
    .map(([label, value, note, tone]) => `<article class="mini-kpi ${tone}"><span>${label}</span><strong>${value}</strong><small>${note}</small></article>`)
    .join("");

  const momentum = key === "1W" ? weeklyFlowMomentum(snapshot) : null;
  renderRotationChart(current, momentum);
  renderRotationReadout(current, momentum);
}

function renderRotationChart(current, momentum) {
  const svg = document.getElementById("rotationChart");
  const container = svg.closest(".rotation-chart-wrap");
  const width = Math.max(container.clientWidth || 960, 360);
  const entries = (current.entries || [])
    .filter((item) => Number.isFinite(item.value_100m))
    .sort((a, b) => a.value_100m - b.value_100m);
  const negatives = entries.filter((item) => item.value_100m < 0);
  const positives = entries.filter((item) => item.value_100m >= 0).sort((a, b) => b.value_100m - a.value_100m);
  const ordered = [...negatives, ...positives];
  const rowHeight = 38;
  const margin = { top: 18, right: 130, bottom: 18, left: 130 };
  const height = Math.max(ordered.length * rowHeight + margin.top + margin.bottom, 170);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.style.height = `${height}px`;
  if (ordered.length === 0) {
    svg.innerHTML = `<text x="${width / 2}" y="${height / 2}" fill="#6f7a75" text-anchor="middle">当前窗口暂无板块资金轮动数据</text>`;
    return;
  }

  const minValue = Math.min(...ordered.map((item) => item.value_100m), 0);
  const maxValue = Math.max(...ordered.map((item) => item.value_100m), 0);
  const plotWidth = width - margin.left - margin.right;
  const scale = plotWidth / (maxValue - minValue || 1);
  const zero = margin.left + (0 - minValue) * scale;
  const parts = [`<line x1="${zero}" y1="${margin.top - 4}" x2="${zero}" y2="${height - margin.bottom + 4}" stroke="#4a534f" stroke-width="1"/>`];

  ordered.forEach((item, index) => {
    const value = item.value_100m;
    const y = margin.top + index * rowHeight;
    const barY = y + 8;
    const barHeight = rowHeight - 16;
    const barX = value >= 0 ? zero : zero + value * scale;
    const barWidth = Math.max(Math.abs(value) * scale, 2);
    const color = value >= 0 ? "#dc6b74" : "#54b88d";
    const group = escapeHtml(item.group);
    const trend = momentum?.get(item.group);
    const deltaTspan = trend
      ? `<tspan dx="8" font-size="11" font-weight="400" fill="${trend.delta >= 0 ? "#e8909a" : "#79cba6"}">较上周${formatNumber(trend.delta, 0)}</tspan>`
      : "";
    parts.push(`<rect x="${barX}" y="${barY}" width="${barWidth}" height="${barHeight}" rx="4" fill="${color}" fill-opacity="0.78"/>`);
    if (value < 0) {
      parts.push(`<text x="${Math.max(barX - 8, 10)}" y="${y + rowHeight / 2 + 4}" fill="#f3f7f4" font-size="13" font-weight="700" text-anchor="end">${group}${deltaTspan}</text>`);
      parts.push(`<text x="${Math.min(zero - 8, width - 10)}" y="${y + rowHeight / 2 + 4}" fill="${color}" font-size="12" font-weight="800" text-anchor="end">${formatNumber(value, 1)}</text>`);
    } else {
      parts.push(`<text x="${Math.min(zero + barWidth + 8, width - 10)}" y="${y + rowHeight / 2 + 4}" fill="#f3f7f4" font-size="13" font-weight="700">${group}${deltaTspan}</text>`);
      parts.push(`<text x="${zero + 6}" y="${y + rowHeight / 2 + 4}" fill="${color}" font-size="12" font-weight="800">${formatNumber(value, 1)}</text>`);
    }
  });
  svg.innerHTML = parts.join("");
}

function renderRotationReadout(current, momentum) {
  const entries = current.entries || [];
  const positiveGroups = entries.filter((item) => (item.value_100m || 0) > 0).length;
  const negativeGroups = entries.filter((item) => (item.value_100m || 0) < 0).length;
  const sourceText = current.largest_source
    ? `${escapeHtml(current.largest_source)} ${formatNumber(current.largest_source_100m, 1, " 亿")}`
    : "暂无明显流出板块";
  const destinationText = current.largest_destination
    ? `${escapeHtml(current.largest_destination)} ${formatNumber(current.largest_destination_100m, 1, " 亿")}`
    : "暂无明显流入板块";
  const breadth = `${positiveGroups} 个板块净流入，${negativeGroups} 个板块净流出`;

  let momentumLine = "";
  if (momentum && momentum.size) {
    const ranked = Array.from(momentum.entries()).sort((a, b) => b[1].delta - a[1].delta);
    const [accName, acc] = ranked[0];
    const [decName, dec] = ranked[ranked.length - 1];
    const pieces = [];
    if (acc.delta > 0) pieces.push(`${escapeHtml(accName)}加速（${formatNumber(acc.prior, 0)}→${formatNumber(acc.current, 0)} 亿）`);
    if (dec.delta < 0 && decName !== accName) pieces.push(`${escapeHtml(decName)}降温（${formatNumber(dec.prior, 0)}→${formatNumber(dec.current, 0)} 亿）`);
    if (pieces.length) momentumLine = `<p><span>4</span>环比：${pieces.join("；")}</p>`;
  }

  document.getElementById("rotationReadout").innerHTML = `
    <h3>解读</h3>
    <div class="readout-list">
      <p><span>1</span>主要去向：${destinationText}</p>
      <p><span>2</span>主要来源：${sourceText}</p>
      <p><span>3</span>${breadth}</p>
      ${momentumLine}
    </div>
  `;
}

function renderBetaPressure(snapshot) {
  const section = document.getElementById("pressureSection");
  const data = snapshot.beta_pressure || {};
  section.hidden = false;
  const rows = Array.isArray(data.rows) ? data.rows : [];
  renderPressureFreshness(data);
  renderPressureKpis(data, rows);
  renderPressureTable(data, rows);
}

function renderPressureFreshness(data) {
  const parts = [];
  if (data.holding_as_of) parts.push(`持仓 ${data.holding_as_of}`);
  if (data.share_as_of) parts.push(`份额 ${data.share_as_of}`);
  if (data.method_label) parts.push(data.method_label);
  if (data.as_of) parts.push(`数据日 ${data.as_of}`);
  document.getElementById("pressureFreshness").textContent = parts.join(" · ") || data.reason || "持仓穿透数据";
}

function renderPressureKpis(data, rows) {
  const summary = data.summary || {};
  const coverage = data.coverage || {};
  const linkedEtfs = summary.linked_etf_count ?? rows.reduce((sum, row) => sum + (Number(row.linked_etf_count) || 0), 0);
  const coverageNote = coverage.eligible_etf_count
    ? `持仓覆盖 ${coverage.holding_etf_count || 0}/${coverage.eligible_etf_count}`
    : "样本内合计";
  const cards = [
    ["覆盖个股", formatPlain(summary.stock_count ?? rows.length, 0, " 只"), "持仓穿透样本"],
    ["关联 ETF", formatPlain(linkedEtfs || null, 0, " 只"), coverageNote],
    ["穿透净变动", formatNumber(summary.net_position_change_yi_shares, 2, " 亿股"), "按份额变化估算"],
    ["融资余额", formatPlain(summary.margin_balance_100m, 2, " 亿元"), "两融观察"],
    ["数据状态", escapeHtml(summary.data_status || data.status || "--"), coverage.holding_etf_pct != null ? `ETF 覆盖 ${coverage.holding_etf_pct}%` : data.holding_as_of || "待接入持仓"],
  ];
  document.getElementById("pressureKpis").innerHTML = cards
    .map(([label, value, note]) => `<article class="mini-kpi"><span>${label}</span><strong>${value}</strong><small>${note}</small></article>`)
    .join("");
}

function pressureMetric(row, keys) {
  for (const key of keys) {
    if (row[key] !== null && row[key] !== undefined) return row[key];
  }
  return null;
}

function formatMarginValue(row, key) {
  if (row.margin_eligible === false) return "非两融";
  return formatPlain(row[key], 1, " 亿");
}

function filteredPressureRows(rows) {
  const query = state.query.trim().toLowerCase();
  const filtered = rows.filter((row) => {
    const change = Number(pressureMetric(row, ["today_change_wan_shares", "position_change_wan_shares", "change_wan_shares"]));
    if (state.pressureFilter === "etf_increase" && !(change > 0)) return false;
    if (state.pressureFilter === "etf_decrease" && !(change < 0)) return false;
    if (!query) return true;
    return `${row.name || ""} ${row.code || ""} ${row.industry || ""}`.toLowerCase().includes(query);
  });
  const sort = PRESSURE_SORTS[state.pressureSort] || PRESSURE_SORTS.change_amount;
  filtered.sort((a, b) => {
    const av = Number(pressureMetric(a, sort.keys)) || 0;
    const bv = Number(pressureMetric(b, sort.keys)) || 0;
    return sort.abs ? Math.abs(bv) - Math.abs(av) : bv - av;
  });
  return filtered;
}

function renderPressureTable(data, rows) {
  document.querySelectorAll("#pressureFilter button").forEach((button) => {
    button.classList.toggle("active", button.dataset.pressure === state.pressureFilter);
  });
  const sortChips = document.getElementById("pressureSort");
  if (sortChips) {
    sortChips.innerHTML = `<span class="sort-label">排序</span>` + Object.entries(PRESSURE_SORTS)
      .map(([key, meta]) => `<button type="button" data-sort="${key}" class="${key === state.pressureSort ? "active" : ""}">${meta.label}</button>`)
      .join("");
  }
  const filtered = filteredPressureRows(rows);
  document.getElementById("pressureTableHead").innerHTML = `
    <tr>
      <th>#</th>
      <th class="pressure-name">名称</th>
      <th>代码</th>
      <th>关联 ETF</th>
      <th>穿透持仓</th>
      <th>当日变动</th>
      <th>变动金额</th>
      <th>融资余额</th>
      <th>融券余额</th>
      <th>流通股</th>
      <th>流通市值</th>
    </tr>
  `;
  if (filtered.length === 0) {
    const message = data.reason || "当前快照未包含 ETF 持仓穿透数据。";
    document.getElementById("pressureTableBody").innerHTML = `<tr><td colspan="11" class="pressure-empty">${escapeHtml(message)}</td></tr>`;
    renderPressureDetail(null, data);
    return;
  }
  if (!state.selectedPressureCode || !filtered.some((row) => row.code === state.selectedPressureCode)) {
    state.selectedPressureCode = filtered[0].code;
  }
  document.getElementById("pressureTableBody").innerHTML = filtered
    .map((row, index) => {
      const selected = row.code === state.selectedPressureCode ? "selected" : "";
      return `
        <tr class="${selected}" data-code="${escapeHtml(row.code)}">
          <td>${index + 1}</td>
          <td class="pressure-name"><strong>${escapeHtml(row.name || "--")}</strong><span>${escapeHtml(row.industry || "")}</span></td>
          <td>${escapeHtml(row.code || "--")}</td>
          <td>${formatPlain(row.linked_etf_count, 0, " 只")}</td>
          <td>${formatPlain(pressureMetric(row, ["penetrated_holding_yi_shares", "holding_yi_shares"]), 2, " 亿股")}</td>
          <td>${formatNumber(pressureMetric(row, ["today_change_wan_shares", "position_change_wan_shares", "change_wan_shares"]), 1, " 万股")}</td>
          <td>${formatNumber(pressureMetric(row, ["change_amount_100m", "today_change_amount_100m"]), 1, " 亿")}</td>
          <td>${formatMarginValue(row, "margin_balance_100m")}</td>
          <td>${formatMarginValue(row, "short_balance_100m")}</td>
          <td>${formatPlain(row.float_shares_100m, 2, " 亿")}</td>
          <td>${formatPlain(row.float_market_value_100m, 0, " 亿")}</td>
        </tr>
      `;
    })
    .join("");
  renderPressureDetail(filtered.find((row) => row.code === state.selectedPressureCode), data);
}

function pressureHistoryPoints(data, code) {
  return (Array.isArray(data.history) ? data.history : [])
    .map((entry) => {
      const row = (entry.rows || []).find((item) => item.code === code);
      return row ? { date: entry.date, value: Number(row.change_amount_100m) } : null;
    })
    .filter((item) => item && Number.isFinite(item.value))
    .slice(-30);
}

function renderPressureHistory(row, data) {
  const points = pressureHistoryPoints(data, row.code);
  if (points.length < 2) {
    return `
      <h4>穿透变动历史</h4>
      <div class="pressure-history-empty">历史将在每日刷新后累积，当前已有 ${points.length} 个数据点。</div>
    `;
  }
  const width = 320;
  const height = 124;
  const margin = { top: 12, right: 8, bottom: 24, left: 8 };
  const maxAbs = Math.max(...points.map((item) => Math.abs(item.value)), 0.01);
  const zeroY = margin.top + (height - margin.top - margin.bottom) / 2;
  const slot = (width - margin.left - margin.right) / points.length;
  const barWidth = Math.max(Math.min(slot * 0.62, 12), 2);
  const scale = (height - margin.top - margin.bottom) / 2 / maxAbs;
  const bars = points
    .map((item, index) => {
      const barHeight = Math.max(Math.abs(item.value) * scale, 1);
      const x = margin.left + index * slot + (slot - barWidth) / 2;
      const y = item.value >= 0 ? zeroY - barHeight : zeroY;
      const color = item.value >= 0 ? "#dc6b74" : "#54b88d";
      return `<rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${barWidth.toFixed(2)}" height="${barHeight.toFixed(2)}" rx="1" fill="${color}"><title>${escapeHtml(item.date)} ${formatNumber(item.value, 2, " 亿")}</title></rect>`;
    })
    .join("");
  return `
    <h4>穿透变动历史</h4>
    <div class="pressure-history-chart">
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(row.name || row.code)}穿透变动历史">
        <line x1="${margin.left}" y1="${zeroY}" x2="${width - margin.right}" y2="${zeroY}" stroke="#46504c" stroke-width="1" />
        ${bars}
        <text x="${margin.left}" y="${height - 6}" fill="#82908a" font-size="10">${escapeHtml(points[0].date)}</text>
        <text x="${width - margin.right}" y="${height - 6}" fill="#82908a" font-size="10" text-anchor="end">${escapeHtml(points[points.length - 1].date)}</text>
      </svg>
    </div>
  `;
}

function renderPressureContributors(row) {
  const contributors = Array.isArray(row.contributors) ? row.contributors.slice(0, 5) : [];
  if (contributors.length === 0) return "";
  return `
    <h4>贡献 ETF</h4>
    <div class="contributor-list">
      ${contributors
        .map(
          (item) => `
            <div class="contributor-row">
              <span><strong>${escapeHtml(item.name || item.code)}</strong><small>${escapeHtml(item.code || "")} · 权重 ${formatPlain(item.weight_pct, 2, "%")}</small></span>
              <b class="${Number(item.change_amount_100m) >= 0 ? "positive" : "negative"}">${formatNumber(item.change_amount_100m, 2, " 亿")}</b>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderPressureDetail(row, data) {
  const panel = document.getElementById("pressureDetail");
  if (!row) {
    panel.innerHTML = `
      <h3>选中个股</h3>
      <div class="pressure-empty-card">
        <strong>暂无穿透样本</strong>
        <p>${escapeHtml(data.reason || "接入 ETF 持仓明细后将显示个股穿透变动、贡献 ETF 和两融因子。")}</p>
      </div>
    `;
    return;
  }
  const factors = row.factors || [
    { label: "ETF 净增贡献", value: pressureMetric(row, ["etf_increase_wan_shares", "increase_wan_shares"]) },
    { label: "ETF 净减抵消", value: pressureMetric(row, ["etf_decrease_wan_shares", "decrease_wan_shares"]) },
    { label: "融资温度", value: row.margin_balance_100m },
    { label: "样本覆盖", value: row.linked_etf_count },
  ];
  const factorMax = Math.max(...factors.map((item) => Math.abs(Number(item.value) || 0)), 1);
  panel.innerHTML = `
    <h3>选中个股</h3>
    <div class="selected-stock">
      <strong>${escapeHtml(row.name || "--")}</strong>
      <span>${escapeHtml(row.code || "--")}</span>
    </div>
    <p class="selected-note">${formatPlain(row.linked_etf_count, 0, " 只")} 关联 ETF${row.industry ? ` · ${escapeHtml(row.industry)}` : ""}</p>
    <div class="detail-cards">
      <article><span>穿透持仓</span><strong>${formatPlain(pressureMetric(row, ["penetrated_holding_yi_shares", "holding_yi_shares"]), 2, " 亿股")}</strong></article>
      <article><span>当日变动</span><strong>${formatNumber(pressureMetric(row, ["today_change_wan_shares", "position_change_wan_shares", "change_wan_shares"]), 1, " 万股")}</strong></article>
      <article><span>变动金额</span><strong>${formatNumber(pressureMetric(row, ["change_amount_100m", "today_change_amount_100m"]), 1, " 亿")}</strong></article>
      <article><span>流通市值</span><strong>${formatPlain(row.float_market_value_100m, 0, " 亿")}</strong></article>
    </div>
    ${renderPressureHistory(row, data)}
    ${renderPressureContributors(row)}
    <h4>因子分解</h4>
    <div class="factor-list">
      ${factors
        .map((item) => {
          const value = Number(item.value) || 0;
          const width = Math.max((Math.abs(value) / factorMax) * 100, value === 0 ? 0 : 4);
          const tone = value >= 0 ? "positive-bar" : "negative-bar";
          return `<div class="factor-row"><span>${escapeHtml(item.label)}</span><div><i class="${tone}" style="width:${width}%"></i></div><strong>${formatNumber(value, 1)}</strong></div>`;
        })
        .join("")}
    </div>
  `;
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
  renderBetaPressure(state.snapshot);
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
  renderQuadrantSection(state.snapshot);
});

document.getElementById("quadrantWindowChips").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-window]");
  if (!button) return;
  state.quadrantWindow = button.dataset.window;
  renderQuadrantSection(state.snapshot);
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

document.getElementById("rotationWindowChips").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-window]");
  if (!button) return;
  state.rotationWindow = button.dataset.window;
  renderRotation(state.snapshot);
});

document.getElementById("pressureFilter").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-pressure]");
  if (!button) return;
  state.pressureFilter = button.dataset.pressure;
  state.selectedPressureCode = null;
  renderBetaPressure(state.snapshot);
});

document.getElementById("pressureSort").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-sort]");
  if (!button) return;
  state.pressureSort = button.dataset.sort;
  state.selectedPressureCode = null;
  renderBetaPressure(state.snapshot);
});

document.getElementById("pressureTableBody").addEventListener("click", (event) => {
  const row = event.target.closest("tr[data-code]");
  if (!row) return;
  state.selectedPressureCode = row.dataset.code;
  renderBetaPressure(state.snapshot);
});

let chartResizeTimer = null;
window.addEventListener("resize", () => {
  if (!state.snapshot) return;
  clearTimeout(chartResizeTimer);
  chartResizeTimer = setTimeout(() => {
    renderCharts(state.snapshot);
    renderQuadrantSection(state.snapshot);
    renderRotation(state.snapshot);
  }, 160);
});

function showError(error) {
  document.querySelector(".shell").insertAdjacentHTML(
    "beforeend",
    `<div class="error">${escapeHtml(error.message)}</div>`,
  );
}

if (window.location.protocol === "file:" && !embeddedSnapshot) {
  window.location.replace("../dist/etf-radar.html");
} else {
  initAutoRefresh();
  loadSnapshot().catch(showError);
}
