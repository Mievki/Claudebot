"""State (JSON) + trade-log (CSV). Bewust simpel; CSV is direct in Excel/pandas te openen."""
import os, json, csv
from datetime import datetime, timezone
import config as C

def load_state():
    try:
        with open(C.STATE_JSON) as f: return json.load(f)
    except Exception:
        return {}

def save_state(st):
    with open(C.STATE_JSON, "w") as f: json.dump(st, f, indent=2)

def log_trade(row: dict):
    new = not os.path.exists(C.TRADES_CSV)
    fields = ["ts_utc", "action", "price", "units", "usdt", "fee",
              "equity_after", "stop", "reason"]
    with open(C.TRADES_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new: w.writeheader()
        w.writerow({k: row.get(k, "") for k in fields})

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
