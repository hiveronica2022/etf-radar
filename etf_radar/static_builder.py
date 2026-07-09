from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def build_static_html(snapshot_path: Path, output_path: Path) -> None:
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "dashboard" / "styles.css").read_text(encoding="utf-8")
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    html = html.replace('<link rel="stylesheet" href="styles.css">', f"<style>\n{css}\n</style>")
    html = html.replace("<script src=\"app.js\"></script>", f"<script>\nwindow.__ETF_SNAPSHOT__ = {json.dumps(snapshot, ensure_ascii=False)};\n{js}\n</script>")
    html = html.replace("<body>", '<body data-embedded="true">')

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def build_pages_site(snapshot_path: Path, output_dir: Path) -> None:
    """组装 GitHub Pages 静态站点：index.html + app.js + styles.css + 同目录快照 JSON。

    与单文件版不同，页面按同目录 URL 拉取快照，保留 5 分钟自动轮询——推新数据后
    朋友的页面无需刷新即可更新。
    """
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "dashboard" / "styles.css").read_text(encoding="utf-8")
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    snapshot_text = snapshot_path.read_text(encoding="utf-8")

    # 把快照地址指到同目录，覆盖 app.js 里的本地默认路径。
    html = html.replace(
        "<script src=\"app.js\"></script>",
        '<script>window.__SNAPSHOT_URL__ = "dashboard_snapshot.json";</script>\n    <script src="app.js"></script>',
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(html, encoding="utf-8")
    (output_dir / "styles.css").write_text(css, encoding="utf-8")
    (output_dir / "app.js").write_text(js, encoding="utf-8")
    (output_dir / "dashboard_snapshot.json").write_text(snapshot_text, encoding="utf-8")
