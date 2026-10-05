import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gpx2elev.smoke import run_smoke


class UiTests(unittest.TestCase):
    def test_real_window_drop_worker_cache_chart_and_export(self):
        resources = Path(__file__).resolve().parents[2] / "app/src/test/resources"
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "ui.json"
            self.assertEqual(run_smoke(report, resources), 0)
            self.assertTrue(report.with_suffix(".png").exists())


if __name__ == "__main__":
    unittest.main()
