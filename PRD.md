# Product Requirements Document (PRD)

## Objective
Enhance the Daily Market Regime Engine with Option Chain analysis to identify institutional buyer/seller positioning (Open Interest, Call/Put writing, Max Pain, PCR) and predict intraday and daily momentum on both historical and live data.

## Tasks
- [x] Task 1: Create `src/option_data.py` with NSE option chain fetching, parser, PCR, Max Pain, and strike concentration analysis.
- [x] Task 2: Create offline sample option fixture `data/sample_option_chain.json` and unit test suite `test_option_data.py`.
- [x] Task 3: Integrate Option Chain analysis into `src/live_scanner.py` for real-time buyer/seller alerts and intraday momentum tracking.
- [x] Task 4: Integrate Option Chain insights into `scan_nifty.py` daily forecast CLI report.
- [x] Task 5: Run full test suite (`python run_all_tests.py`) and perform CodeRabbit pre-merge review.
