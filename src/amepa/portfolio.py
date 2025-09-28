from pathlib import Path
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from .io_helpers import INPUTS, FIGS, TABLES, read_positions

def _detect_splits(px: pd.Series) -> pd.DataFrame:
    ratio = px / px.shift(1)
    events = []
    for d, r in ratio.items():
        if pd.isna(r):
            continue
        if r < 0.7:
            k = int(np.round(1.0 / r))
            if 2 <= k <= 10:
                events.append((d, k))
        elif r > 1.6:
            k = int(np.round(r))
            if 2 <= k <= 10:
                events.append((d, 1.0 / k))
    if not events:
        return pd.DataFrame(columns=["Date", "Factor"])
    return pd.DataFrame(events, columns=["Date", "Factor"]).drop_duplicates().sort_values("Date")

def _parse_dividends(notes_col: pd.Series, tickers: list) -> pd.DataFrame:
    div = pd.DataFrame(index=notes_col.index, columns=tickers, data=0.0)
    if notes_col is None or notes_col.empty:
        return div
    for txt in notes_col.dropna():
        t = str(txt)
        if "dividend" in t.lower():
            tick = next((T for T in tickers if T in t), None)
            m_amt = re.search(r"\$?([0-9]+\.?[0-9]*)", t)
            m_date = re.search(r"(20\d\d)[-/](\d\d)[-/](\d\d)", t)
            if tick and m_amt and m_date:
                amt = float(m_amt.group(1))
                d = pd.Timestamp(f"{m_date.group(1)}-{m_date.group(2)}-{m_date.group(3)}")
                if d in div.index:
                    div.loc[d, tick] = amt
    return div.fillna(0.0)

def run_portfolio() -> None:
    pos = read_positions(INPUTS / "starting_positions.csv")
    tickers = pos["Ticker"].tolist()
    pos0 = {r["Ticker"]: (r["Shares"] if r["Side"].lower() == "long" else -r["Shares"]) for _, r in pos.iterrows()}

    px = pd.read_excel(INPUTS / "prices.xlsx", sheet_name="prices")
    px["Date"] = pd.to_datetime(px["Date"])
    px = px.set_index("Date").sort_index()
    notes = px["Notes"] if "Notes" in px.columns else pd.Series(dtype=object)
    px = px[[t for t in px.columns if t in tickers]].astype(float).ffill().bfill()

    # Build share path with split adjustments
    shares = pd.Series(pos0, dtype=float)
    share_path = pd.DataFrame(index=px.index, columns=tickers, data=np.nan)
    share_path.iloc[0] = shares
    for i in range(1, len(share_path)):
        share_path.iloc[i] = share_path.iloc[i-1]

    for t in tickers:
        s = px[t].dropna().sort_index()
        split_df = _detect_splits(s)
        for _, row in split_df.iterrows():
            d, f = row["Date"], row["Factor"]
            if d in share_path.index:
                share_path.loc[d:, t] = share_path.loc[d:, t] * f

    share_path = share_path.ffill()

    # Dividends from notes
    div_per_share = _parse_dividends(notes, tickers)

    # Daily PnL and returns
    mv_prev = (share_path.shift(1) * px.shift(1)).sum(axis=1)
    price_pnl = ((share_path.shift(1) * px).sum(axis=1) - mv_prev).fillna(0.0)
    div_pnl = (div_per_share * share_path.shift(1)).sum(axis=1).fillna(0.0)
    total_pnl = price_pnl + div_pnl
    daily_ret = (total_pnl / mv_prev).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    ticker_pnl = (share_path.shift(1) * (px - px.shift(1))).fillna(0.0)

    # Outputs
    out_xlsx = TABLES / "portfolio_daily_pnl.xlsx"
    with pd.ExcelWriter(out_xlsx, engine="xlsxwriter") as writer:
        pd.DataFrame({
            "PortfolioValue": (share_path * px).sum(axis=1),
            "PricePnL": price_pnl,
            "DivPnL": div_pnl,
            "TotalPnL": total_pnl,
            "Return": daily_ret,
        }).to_excel(writer, sheet_name="Portfolio", index=True)
        share_path.to_excel(writer, sheet_name="Shares", index=True)
        px.to_excel(writer, sheet_name="Prices", index=True)
        div_per_share.to_excel(writer, sheet_name="Dividends_perShare", index=True)
        ticker_pnl.to_excel(writer, sheet_name="PnL_by_Ticker", index=True)

    # Drivers and EPS snapshots
    drivers = ticker_pnl.sum(axis=0).rename("TotalPnL").to_frame()
    start_values = pd.Series(pos0) * px.iloc[0][tickers]
    drivers["StartWeight"] = (start_values / start_values.sum()).values
    drivers.sort_values("TotalPnL", ascending=False).to_csv(TABLES / "portfolio_drivers.csv")

    eps = pd.read_csv(INPUTS / "eps_estimates_override.csv", parse_dates=["AsOf"])
    eps[["Ticker","AsOf","EPS_CurrentFY","EPS_NextFY"]].to_csv(TABLES / "portfolio_eps_snapshots.csv", index=False)

    # Figure
    cum = (1.0 + daily_ret).cumprod()
    plt.figure()
    plt.plot(cum.index, cum.values)
    plt.title("Portfolio cumulative return gross including dividends")
    plt.xlabel("Date")
    plt.ylabel("Growth of 1")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(FIGS / "portfolio_cumulative_return_2022.png")
    plt.close()
