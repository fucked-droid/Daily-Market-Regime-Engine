from universe import (
    load_nifty50_universe,
    validate_nifty50_universe,
    get_nifty50_constituents,
)


universe = load_nifty50_universe()

validate_nifty50_universe(universe)

print("Universe loaded successfully")
print("Rows:", len(universe))
print("Columns:", list(universe.columns))

today = universe["Start_Date"].max()

active = get_nifty50_constituents(
    today,
    universe
)

print("Test date:", today.date())
print("Active constituents:", len(active))
print()
print(active["Symbol"].to_list())
