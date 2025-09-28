from pathlib import Path
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from .io_helpers import EXTERNAL, FIGS, TABLES, write_json

RENAME_MAP = {
    "cusip": "cusip",
    "security_type": "security_type",
    "securityterm": "security_term",
    "security_term": "security_term",
    "auction_type": "auction_type",
    "auctiondate": "auction_date",
    "auction_date": "auction_date",
    "issuedate": "issue_date",
    "issue_date": "issue_date",
    "maturitydate": "maturity_date",
    "maturity_date": "maturity_date",
    "offering_amount": "offering_amount",
    "offering_amt": "offering_amount",
    "total_tenders": "total_tenders",
    "total_tendered": "total_tenders",
    "total_accepted": "total_accepted",
    "bid_to_cover_ratio": "bid_to_cover_ratio",
    "bidtocoverratio": "bid_to_cover_ratio",
    "high_discount_rate": "high_discount_rate",
    "high_discnt_rate": "high_discount_rate",
    "high_yield": "high_yield",
    "price": "price",
    "priceper100": "price",
    "priceper1000": "price",
    "stop_out_rate": "stop_out_rate",
    "stop_out_yield": "stop_out_rate",
    "stop_out": "stop_out_rate",
}

def _term_to_months(term: str) -> float:
    if pd.isna(term):
        return np.nan
    t = str(term).lower().strip()
    if "week" in t:
        digits = "".join(ch if (ch.isdigit() or ch == ".") else " " for ch in t)
        parts = digits.split()
        w = pd.to_numeric(parts[0], errors="coerce") if parts else np.nan
        return float(w) * 7.0 / 30.437 if pd.notna(w) else np.nan
    years, months = 0.0, 0.0
    if "year" in t:
        digits = "".join(ch if (ch.isdigit() or ch == ".") else " " for ch in t).split()
        years = pd.to_numeric(digits[0], errors="coerce") if digits else np.nan
        if "month" in t and len(digits) >= 2:
            months = pd.to_numeric(digits[1], errors="coerce")
    elif "month" in t:
        digits = "".join(ch if (ch.isdigit() or ch == ".") else " " for ch in t).split()
        months = pd.to_numeric(digits[0], errors="coerce") if digits else np.nan
    return (float(years) * 12.0 if pd.notna(years) else 0.0) + (float(months) if pd.notna(months) else 0.0)

def run_auctions(snapshot_name: str = "treasury_auctions_2022_embedded.json") -> pd.DataFrame:
    src = EXTERNAL / snapshot_name
    raw = json.loads(src.read_text())
    df = pd.DataFrame(raw)
    df = df.rename(columns={c: RENAME_MAP.get(c, c) for c in df.columns})

    for c in ["auction_date", "issue_date", "maturity_date"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    if "auction_date" in df.columns:
        df = df[(df["auction_date"].dt.year == 2022) | (df["auction_date"].isna())]

    if "security_type" in df.columns:
        df = df[df["security_type"].astype(str).str.lower().isin(["bill", "note"])]

    num_cols = [
        "offering_amount", "total_tenders", "total_accepted",
        "bid_to_cover_ratio", "high_discount_rate", "high_yield", "price",
        "stop_out_rate"
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if "stop_out_rate" not in df.columns:
        df["stop_out_rate"] = np.nan
    if "high_discount_rate" in df.columns:
        df["stop_out_rate"] = df["stop_out_rate"].fillna(df["high_discount_rate"])
    if "high_yield" in df.columns:
        df["stop_out_rate"] = df["stop_out_rate"].fillna(df["high_yield"])

    if "security_term" in df.columns:
        df["term_months"] = df["security_term"].apply(_term_to_months)

    ordered = [
        "cusip", "security_type", "security_term", "term_months",
        "auction_date", "issue_date", "maturity_date",
        "offering_amount", "total_tenders", "total_accepted",
        "bid_to_cover_ratio", "high_discount_rate", "high_yield",
        "price", "stop_out_rate"
    ]
    cols = [c for c in ordered if c in df.columns] + [c for c in df.columns if c not in ordered]
    parsed_path = TABLES / "treasury_auctions_2022_parsed.csv"
    df[cols].to_csv(parsed_path, index=False)

    dtype_suggestions = {
        "cusip": "string",
        "security_type": "category",
        "security_term": "category",
        "term_months": "float64",
        "auction_date": "datetime64[ns]",
        "issue_date": "datetime64[ns]",
        "maturity_date": "datetime64[ns]",
        "offering_amount": "int64",
        "total_tenders": "int64",
        "total_accepted": "int64",
        "bid_to_cover_ratio": "float64",
        "high_discount_rate": "float64",
        "high_yield": "float64",
        "price": "float64",
        "stop_out_rate": "float64",
    }
    write_json(TABLES / "treasury_auctions_2022_dtype_suggestions.json", dtype_suggestions)
    (TABLES / "treasury_auctions_2022_key_suggestions.txt").write_text(
        "Primary key candidates\n"
        "  • (cusip, auction_date) unique for competitive rows\n"
        "  • If cusip missing use composite (security_type, security_term, auction_date, issue_date)\n"
    )

    if "auction_date" in df.columns:
        df["month"] = df["auction_date"].dt.to_period("M").dt.to_timestamp()

    # Group and plot monthly average stop out for Bills and Notes
    if "month" in df.columns and "security_type" in df.columns:
        g = df.groupby(["month", "security_type"], dropna=False).agg(
            avg_stop_out=("stop_out_rate", "mean"),
            avg_btc=("bid_to_cover_ratio", "mean"),
            n=("cusip", "count")
        ).reset_index()

        for sec in ["Bill", "Note"]:
            sub = g[g["security_type"] == sec].sort_values("month")
            if not sub.empty:
                plt.figure()
                plt.plot(sub["month"], sub["avg_stop_out"])
                plt.title(f"Average stop out rate {sec}s 2022")
                plt.xlabel("Month")
                plt.ylabel("Rate or Yield percent")
                plt.xticks(rotation=45)
                plt.tight_layout()
                plt.savefig(FIGS / f"auction_avg_stop_out_{sec.lower()}s_2022.png")
                plt.close()

    return df
