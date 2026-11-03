import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from universe import (
    load_nifty50_universe,
    validate_nifty50_universe,
    get_nifty50_constituents,
)


class TestUniverseConstituents(unittest.TestCase):
    def test_load_and_validate_universe(self):
        universe = load_nifty50_universe()
        self.assertIsNotNone(universe)
        self.assertGreater(len(universe), 0)
        validate_nifty50_universe(universe)

        today = universe["Start_Date"].max()
        active = get_nifty50_constituents(today, universe)
        self.assertGreater(len(active), 0)
        self.assertIn("Symbol", active.columns)


if __name__ == "__main__":
    unittest.main()
