"""State (JSON) + trade-log (CSV). Bewust simpel; CSV is direct in Excel/pandas te openen."""
import os, json, csv, time
from contextlib import contextmanager
from datetime import datetime, timezone
import config as C

@contextmanager
def locked(timeout=60.0, stale_after=300.0):
    """Bestands-lock rond lees+wijzig+schrijf van state.json: de dagelijkse job en
       de Telegram-listener draaien als losse processen. Cross-platform (O_EXCL).
       Een lock ouder dan `stale_after` (gecrasht proces) wordt overgenomen."""
    lock = C.STATE_JSON + ".lock"
    t0 = time.time()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock) > stale_after:
                    os.remove(lock); continue
            except OSError:
                pass
            if time.time() - t0 > timeout:
                raise RuntimeError(f"state-lock niet verkregen binnen {timeout}s: {lock}")
            time.sleep(0.2)
    try:
        yield
    finally:
        os.close(fd)
        try: os.remove(lock)
        except OSError: pass

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
