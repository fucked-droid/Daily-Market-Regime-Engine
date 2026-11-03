#!/usr/bin/env python3
"""
Test runner for Daily-Market-Regime-Engine.
Discovers and executes all test suites across the repository.
"""

import os
import sys
import unittest
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
os.chdir(REPO_DIR)
sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(REPO_DIR / "src"))


def main():
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(REPO_DIR), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
