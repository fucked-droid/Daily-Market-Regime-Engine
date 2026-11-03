# Product Requirements Document (PRD) — Advanced Institutional Tools

## Objective
Supercharge the Daily Market Regime Engine with three institutional-grade modules:
1. FII / DII Smart Money Inflow & Derivatives Positioning (`src/institutional_flow.py`)
2. Market Breadth: NIFTY 50 Advance-Decline (A/D) & Divergence Engine (`src/market_breadth.py`)
3. Global Cues & GIFT NIFTY Opening Gap Predictor (`src/global_cues.py`)

## Tasks
- [x] Task 1: Build `src/institutional_flow.py` and `data/sample_fii_dii.json` for FII/DII cash flows & Index Futures Long/Short ratio.
- [x] Task 2: Build `src/market_breadth.py` and `data/sample_breadth.json` for Advance/Decline ratio, hollow rally traps, and breadth scoring.
- [x] Task 3: Build `src/global_cues.py` for GIFT Nifty gap forecasting and macro cues (Crude, US yields).
- [x] Task 4: Create comprehensive unit tests in `test_advanced_tools.py` with 100% test pass.
- [x] Task 5: Integrate Institutional Flows, Market Breadth, and Global Cues into `scan_nifty.py` and `src/live_scanner.py`.
- [x] Task 6: Run master test suite (`python run_all_tests.py`), verify CodeRabbit standards, and commit.
