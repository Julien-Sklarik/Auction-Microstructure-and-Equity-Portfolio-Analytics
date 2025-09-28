from pathlib import Path

def test_portfolio_outputs_exist():
    tables = Path("reports") / "tables"
    assert (tables / "portfolio_daily_pnl.xlsx").exists()
    assert (tables / "portfolio_drivers.csv").exists()
    assert (tables / "portfolio_eps_snapshots.csv").exists()
