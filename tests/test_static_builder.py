import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from etf_radar.sample_data import sample_snapshot
from etf_radar.static_builder import build_pages_site, build_static_html


class StaticBuilderTest(unittest.TestCase):
    def _write_snapshot(self, directory: Path) -> Path:
        path = directory / "snap.json"
        path.write_text(json.dumps(sample_snapshot(), ensure_ascii=False), encoding="utf-8")
        return path

    def test_build_static_html_embeds_snapshot_and_marks_embedded(self):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            snapshot = self._write_snapshot(tmp_path)
            out = tmp_path / "dist" / "etf.html"
            build_static_html(snapshot, out)
            html = out.read_text(encoding="utf-8")

        self.assertIn("window.__ETF_SNAPSHOT__", html)
        self.assertIn('data-embedded="true"', html)

    def test_build_pages_site_writes_assets_and_sibling_snapshot(self):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            snapshot = self._write_snapshot(tmp_path)
            out = tmp_path / "docs"
            build_pages_site(snapshot, out)

            names = {p.name for p in out.iterdir()}
            self.assertEqual(names, {"index.html", "app.js", "styles.css", "dashboard_snapshot.json"})

            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn('window.__SNAPSHOT_URL__ = "dashboard_snapshot.json"', index)
            # 不是内嵌单文件：不应把整份快照塞进 HTML
            self.assertNotIn("window.__ETF_SNAPSHOT__", index)

            embedded = json.loads((out / "dashboard_snapshot.json").read_text(encoding="utf-8"))
            self.assertIn("rows", embedded)


if __name__ == "__main__":
    unittest.main()
