from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
EXTERNAL = DATA / "external"
INPUTS = DATA / "inputs"
REPORTS = ROOT / "reports"
FIGS = REPORTS / "figures"
TABLES = REPORTS / "tables"

for p in [EXTERNAL, INPUTS, FIGS, TABLES]:
    p.mkdir(parents=True, exist_ok=True)

def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2))

def write_csv(path, df):
    df.to_csv(path, index=False)

def read_positions(path):
    df = pd.read_csv(path)
    df["Side"] = df["Side"].str.strip().str.capitalize()
    return df
