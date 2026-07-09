# ETF 份额雷达

一个本地静态看板，用 ETF 份额变化估算资金流，观察哪些 ETF 在不同时间窗口里被申购、赎回，以及这些资金变化发生在上涨还是下跌阶段。覆盖 A 股主要宽基、科技成长和债券（利率债/信用债/科创债/可转债/短融）三大观察池，除热力表外还提供分类走势对比图、分类资金流对比图和每只 ETF 的迷你走势。

## 快速预览

当前仓库已经带有示例 snapshot 和单文件 HTML：

```bash
open dist/etf-radar.html
```

仓库里的默认 snapshot 是用计划里的样例 ETF 代码抓取的公开数据，用来验证真实数据链路。重新生成示例数据时，页面左上角会显示 `示例数据`。

## 生成公开数据 snapshot

真实数据抓取依赖 AKShare：

```bash
python3 -m pip install -r requirements.txt
python3 -m etf_radar.cli fetch --out data/dashboard_snapshot.json --cache-dir cache --retries 4
python3 -m etf_radar.cli build-html --snapshot data/dashboard_snapshot.json --out dist/etf-radar.html
open dist/etf-radar.html
```

调试少量 ETF：

```bash
python3 -m etf_radar.cli fetch --codes 510300 510330 159915 159600 159516 --out data/dashboard_snapshot.json --cache-dir cache --retries 4
```

推荐日常更新命令（宽基 + 科技 + 红利 + 债券观察池，全部 8 个窗口）：

```bash
python3 -m etf_radar.cli fetch --preset core --preset bond --preset dividend --window-set full --out data/dashboard_snapshot.json --cache-dir cache --retries 4 --retry-sleep 1.5 --price-pause 0.6 --no-proxy
python3 -m etf_radar.cli build-html --snapshot data/dashboard_snapshot.json --out dist/etf-radar.html
```

东财历史行情接口对连续请求有限流（触发后按 IP 硬断连），因此价格历史默认在东财失败时自动回退到新浪接口（`fund_etf_hist_sina`），单次即可返回完整历史、不受东财限流影响。仍失败的代码会退回上次缓存，重复运行同一命令即可增量补齐。加 `--no-sina-fallback` 可关闭兜底。

只想快速刷新短窗口时用 `--window-set short`（1D/1W/2W/1M）。

全市场抓取不传 `--codes`。AKShare 的历史价格接口按 ETF 逐只请求，全市场首跑会比较久；默认缓存会保存当天 spot 列表和每只 ETF 的历史价格，后续日更会复用缓存。建议先用少量代码或 `--limit` 做烟测。

常用抓取参数：

- `--preset core`：主要宽基、创业板/科创和科技成长板块观察池。
- `--preset bond`：利率债、信用债、科创债、可转债和短融 ETF 观察池，可与 core 叠加。
- `--preset dividend`：上证/中证红利、红利低波、国企/央企红利和港股红利 ETF 观察池。
- `--no-proxy`：忽略系统代理环境变量直连数据源（本机代理不可用时必加）。
- `--price-pause 0.6`：逐只请求历史价格的间隔秒数，缓解东财限流。
- `--no-sina-fallback`：禁用新浪历史行情兜底。默认东财逐只接口失败时自动回退新浪 `fund_etf_hist_sina`（一次返回全历史、不受东财限流影响），是缺数据能补齐的关键。
- `--window-set short`：只生成 1D、1W、2W、1M，适合公开源不稳定时快速刷新。
- `--cache-dir cache`：缓存 spot 列表和历史价格，默认就是 `cache`。
- `--no-cache`：临时禁用缓存。
- `--retries 4`：公开数据源失败重试次数。
- `--retry-sleep 0.5`：重试间隔秒数。
- `--source-timeout 8`：单次公开源调用超时秒数。
- `--lookback-days 380`：历史价格回看天数，默认覆盖 12M 窗口。

生成示例数据：

```bash
python3 -m etf_radar.cli sample --out data/dashboard_snapshot.json
```

## 自动更新

一条命令完成「多轮抓取直到数据补齐 + 重建单文件 HTML」：

```bash
python3 -m etf_radar.cli refresh --preset core --preset bond --window-set full --no-proxy --retries 4 --retry-sleep 1.5 --price-pause 0.6 --max-passes 3
```

`refresh` 会在一轮抓取后检查每只 ETF 是否有规模和走势数据，缺数据就等 `--pass-sleep`（默认 20 秒）后再抓一轮，最多 `--max-passes` 轮。价格缓存让后续轮次只补缺失部分。

本地常驻服务（可选，用于本机查看）：

```bash
bash automation/install.sh   # 只装 http://127.0.0.1:8765 的 serve agent
```

- 页面右上角「自动更新」开关默认打开，每 5 分钟检查一次新数据，数据更新后自动重渲染。
- 卸载：`bash automation/uninstall.sh`

> macOS 说明：launchd 自身无法在 `~/Desktop` 等 TCC 保护目录写日志（否则按需触发会 `EX_CONFIG` 失败），因此 launchd 日志放在 `~/Library/Logs/etf-radar/`；数据快照仍写在项目目录内。

`dist/etf-radar.html` 是数据内嵌的单文件版本，适合分享，不支持自动更新（开关会自动隐藏）。

## 分享给朋友（GitHub Pages + 云端自动更新）

看板发布成公开网址，朋友打开即可看，**数据由 GitHub Actions 在云端每天自动更新，本机不用开机**。已实测 GitHub 海外服务器能完整拉到东财/新浪/沪深交易所数据（0 缺失）。

- 站点：`https://<user>.github.io/etf-radar/`，Pages 源 `main` 分支 `/docs`。
- 更新：`.github/workflows/refresh.yml` 工作日 13:00 UTC（北京 21:00）云端抓数 → 重建 `docs/` → 提交推送 → Pages 重建。带**完整性安全阀**：只有 0 缺失才发布，抓不全就跳过、绝不覆盖线上。
- 站点目录 `docs/` 由 `build-pages` 组装（`index.html` + `app.js` + `styles.css` + 同目录 `dashboard_snapshot.json`），保留 5 分钟轮询，推新数据后朋友页面无需刷新即可更新。

首次部署（`gh` CLI 已登录时可全自动）：

```bash
python3 -m etf_radar.cli build-pages --snapshot data/dashboard_snapshot.json --out docs
git init && git add -A && git commit -m "init"
gh repo create etf-radar --public --source=. --push
gh api -X POST repos/{owner}/etf-radar/pages -f 'source[branch]=main' -f 'source[path]=/docs'
gh workflow run refresh-data          # 手动触发一次云端更新
```

**可选：本机也跑一份备份更新**（云端挂了时兜底，工作日 21:30 晚于云端）：

```bash
ETF_LOCAL_REFRESH=1 bash automation/install.sh
```

本机与云端两个推送方都会先 `git pull --rebase` 再推，互不冲突。

## 本地开发预览

```bash
python3 -m http.server 8765
```

然后打开：

```text
http://127.0.0.1:8765/dashboard/index.html
```

`dashboard/index.html` 读取 `data/dashboard_snapshot.json`。`dist/etf-radar.html` 会把 CSS、JS 和 snapshot 嵌入成单文件，适合直接打开或分享。

## 数据口径

- ETF 范围：A 股场内 ETF，不包含 ETF 联接基金。
- 份额净流入：`当前份额 - 窗口起点份额`。
- 金额净流入：`份额净流入 × 当前净值或收盘价`，单位为亿元。
- 涨跌幅：`当前收盘价 / 窗口起点收盘价 - 1`。
- 窗口：1D、1W、2W、1M、3M、6M、YTD、12M。
- 节假日或停牌：窗口锚点取目标日前最近一个可用交易日；过远缺口会显示 `--`。
- 金额净流入来自份额变化估算，不等同于二级市场成交额，也不构成投资建议。
- 分类走势：板块内成分 ETF 的日收益取平均后从 100 累乘（等权合成），新上市成员从有数据的第一天开始参与。
- 分类对比：右侧面板可切换资金流（金额净流入合计）、涨跌幅（按规模加权平均）、规模（最新规模合计）三个维度横向对比各板块。
- 分组下钻：走势图和对比图顶部的「分组」可从「板块」下钻到某板块的细分子类。例如红利细分为宽口径红利/红利低波/国企央企红利/港股红利，科技细分为半导体芯片/通信/人工智能/软件计算机/电子/互联网科技，宽基和债券同理。子类由 `classify_subcategory` 按名称关键词判定。
- 折算处理：ETF 份额折算/拆分会让原始价格单日跳变，涨跌幅和走势用复权价（单日跳变超 30% 视为折算并抹平），规模和最新价仍用原始价。
- 数据新鲜度：看板顶部显示红色「⚠ 数据滞后 N 个交易日」的条件是**数据日（as_of）滞后 ≥ 阈值交易日，且快照本身也 ≥ 阈值天数没重建**（组合判据）。阈值取 `meta.stale_after_trading_days`（默认 3，在 `metrics.DEFAULT_STALE_AFTER_TRADING_DAYS` 调整）。用交易日（跳过周末）计数，正常周末/周一不会误报；长假期间只要定时任务在跑（快照每天重建、generated_at 是新的）也不会误报，只有管线真的停了（数据旧 + 快照也旧）才标红。
- 债券 ETF 不在东财 ETF 实时行情列表内，名称与份额来自沪深交易所公开数据，价格来自逐只历史行情接口。

## 公开数据源

- [AKShare 公募基金数据](https://akshare.akfamily.xyz/data/fund/fund_public.html)
- 东财 ETF 实时行情 `fund_etf_spot_em`：名称、最新价、最新份额（不含债券 ETF）。
- 东财 / 新浪 ETF 历史行情 `fund_etf_hist_em` / `fund_etf_hist_sina`：日线收盘价，新浪为限流兜底源。
- [上交所 ETF 基金规模](https://www.sse.com.cn/assortment/fund/etf/list/scale/) `fund_etf_scale_sse`：含债券 ETF 份额。
- [深交所基金规模日频数据](http://www.szse.cn/market/fund/volume/etf/index.html) `fund_scale_daily_szse`：含债券 ETF 份额。

## 项目结构

```text
etf_radar/
  metrics.py          # 窗口、金额、涨跌幅、标签、走势序列和 summary 计算
  normalization.py    # 公开数据字段、日期、单位标准化
  price_cache.py      # spot 列表和价格历史缓存
  akshare_fetcher.py  # AKShare 数据采集适配层
  presets.py          # core / bond 观察池和名称映射
  cli.py              # sample / fetch / build-html / refresh 命令
automation/
  install.sh          # 安装 launchd 定时刷新 + 常驻服务
  uninstall.sh
dashboard/
  index.html          # 静态看板
  styles.css
  app.js
data/
  dashboard_snapshot.json
dist/
  etf-radar.html
tests/
  test_fetcher.py
  test_metrics.py
  test_price_cache.py
  test_normalization.py
```
