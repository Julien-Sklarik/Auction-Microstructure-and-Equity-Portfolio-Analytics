from pathlib import Path

def test_outputs_exist():
    base = Path("reports") / "tables"
    expect = [
        "treasury_auctions_2022_parsed.csv",
        "treasury_auctions_2022_dtype_suggestions.json",
        "treasury_auctions_2022_key_suggestions.txt",
    ]
    for name in expect:
        assert (base / name).exists()
