import os
import unittest
from pathlib import Path
from src.chart_app import generate_pine_script_v5, build_chart_html, launch_chart_application
from src.engine import load_nifty_master, build_core_engine, add_regime_layer
from scan_nifty import scan_and_predict


class TestChartApplication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.forecast = scan_and_predict(update_data=False)
        df = load_nifty_master()
        df = build_core_engine(df)
        cls.df = add_regime_layer(df)

    def test_generate_pine_script_v5(self):
        script = generate_pine_script_v5(self.forecast)
        self.assertIn("//@version=5", script)
        self.assertIn("Resistance R1", script)
        self.assertIn("Support S1", script)
        self.assertIn("Day Ceiling", script)
        self.assertIn("Day Floor", script)

    def test_build_chart_html(self):
        html = build_chart_html(self.forecast, self.df)
        self.assertIn("LightweightCharts.createChart", html)
        self.assertIn("candleSeries.setData", html)
        self.assertIn("Resistance R1", html)
        self.assertIn("Support S1", html)
        self.assertIn("DOTTED TOP", html)
        self.assertIn("DOTTED BTM", html)
        self.assertIn("ACTION PLAYBOOK", html)

    def test_launch_chart_application(self):
        tmp_path = str(Path(__file__).parent / "test_out_chart.html")
        out = launch_chart_application(
            forecast=self.forecast,
            output_html_path=tmp_path,
            open_browser=False
        )
        self.assertTrue(os.path.exists(tmp_path))
        self.assertGreater(os.path.getsize(tmp_path), 1000)
        os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
