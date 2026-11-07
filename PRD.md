# Product Requirements Document (PRD) — Advanced Institutional Tools

## Objective
Supercharge the Daily Market Regime Engine with five institutional-grade modules:
1. FII / DII Smart Money Inflow & Derivatives Positioning (`src/institutional_flow.py`)
2. Market Breadth: NIFTY 50 Advance-Decline (A/D) & Divergence Engine (`src/market_breadth.py`)
3. Global Cues & GIFT NIFTY Opening Gap Predictor (`src/global_cues.py`)
4. Intraday Order Flow: Cumulative Volume Delta (CVD) & Absorption Engine (`src/order_flow.py`)
5. Sectoral Rotation & Heavyweight Weightage Heatmap Engine (`src/sectoral_rotation.py`)

## Tasks
- [x] Task 1: Build `src/institutional_flow.py` and `data/sample_fii_dii.json` for FII/DII cash flows & Index Futures Long/Short ratio.
- [x] Task 2: Build `src/market_breadth.py` and `data/sample_breadth.json` for Advance/Decline ratio, hollow rally traps, and breadth scoring.
- [x] Task 3: Build `src/global_cues.py` for GIFT Nifty gap forecasting and macro cues (Crude, US yields).
- [x] Task 4: Create comprehensive unit tests in `test_advanced_tools.py` with 100% test pass.
- [x] Task 5: Integrate Institutional Flows, Market Breadth, and Global Cues into `scan_nifty.py` and `src/live_scanner.py`.
- [x] Task 6: Run master test suite (`python run_all_tests.py`), verify CodeRabbit standards, and commit.
- [x] Task 7: Build `src/order_flow.py` and `data/sample_order_flow.json` for Cumulative Volume Delta (CVD), buyer/seller dominance ratio, and absorption divergence traps.
- [x] Task 8: Build `src/sectoral_rotation.py` and `data/sample_sectoral.json` for Sector Index weights, heavyweight point contribution, and Risk-On vs Defensive rotation classification.
- [x] Task 9: Add comprehensive unit tests in `test_order_flow_and_sectoral.py` with 100% test pass across all edge cases (19/19 tests passing).
- [x] Task 10: Integrate Order Flow (CVD) and Sectoral Rotation into `scan_nifty.py` and `src/live_scanner.py` with enriched Hinglish playbook.
- [x] Task 11: Execute complete test suites (`python run_all_tests.py` & `npm test`), verify zero regressions (81/81 Python tests passing), and update documentation.
