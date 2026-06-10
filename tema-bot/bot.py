"""Orchestratie. Twee draaivormen:
   - python bot.py once  -> één beslissing en stoppen (ideaal voor cron / systemd-timer)
   - python bot.py run   -> blijft draaien, wordt elke dag wakker na de candle-close
   - python bot.py stop  -> zet stop-flag (run-modus stopt netjes)
"""
import sys, time, json, os
from datetime import datetime, timezone, timedelta

import config as C
import storage as S
import okx_client as okx
from strategy import Position, decide
from broker import make_broker

def fetch_history():
    rows = okx.candles(C.INST_ID, C.BAR, C.HIST_BARS)
    if len(rows) < C.TEMA_LEN + C.VOL_WIN + 5:
        raise RuntimeError(f"Te weinig candles: {len(rows)}")
    closes = [r["c"] for r in rows]; highs = [r["h"] for r in rows]; lows = [r["l"] for r in rows]
    return closes, highs, lows, rows[-1]["ts"]

def run_once():
    okx.periodic_time_sync()
    st = S.load_state()
    pos = Position.from_dict(st.get("position"))
    closes, highs, lows, last_ts = fetch_history()

    # idempotent: niet twee keer op dezelfde candle handelen
    if st.get("last_bar_ts") == last_ts:
        print(f"[SKIP] candle {last_ts} al verwerkt."); return

    broker = make_broker()
    price = closes[-1]
    eq_before = broker.equity(price)

    decision, pos = decide(closes, highs, lows, pos)
    act = decision["action"]
    # Kill-switch (Telegram /off of /stop): geen NIEUWE entries; een open positie
    # behoudt haar trailing stop, dus EXIT blijft altijd toegestaan.
    if act == "ENTER" and not st.get("trading_enabled", True):
        act = "HOLD"
        decision = {**decision, "action": "HOLD",
                    "reason": "ENTER-signaal onderdrukt: trading staat uit (/on om te hervatten)"}
    print(f"[{S.now_iso()}] price={price:.0f} TEMA={decision['tema']:.0f} "
          f"CMO={decision['cmo']:.1f} ATR={decision['atr']:.0f} "
          f"vol={decision['vol']*100:.1f}% -> {act} ({decision['reason']})")

    log = {"ts_utc": S.now_iso(), "action": act, "price": f"{price:.2f}", "reason": decision["reason"]}

    if act == "ENTER":
        usdt = eq_before * decision["fraction"]
        units, fill, fee = broker.buy(usdt, price)
        pos.in_position = True
        pos.entry_price = fill
        pos.units = units if units is not None else pos.units
        pos.highest = price
        pos.stop = decision["stop"]
        log.update({"units": units, "usdt": f"{usdt:.2f}", "fee": f"{fee:.2f}", "stop": f"{pos.stop:.2f}"})
    elif act == "EXIT":
        units, fill, fee = broker.sell_all(price)
        pos = Position()  # terug naar flat
        log.update({"units": units, "fee": f"{fee:.2f}"})

    eq_after = broker.equity(price)
    log["equity_after"] = f"{eq_after:.2f}"

    # state wegschrijven
    st["position"] = pos.__dict__
    st["last_bar_ts"] = last_ts
    st["equity"] = eq_after
    st = broker.persist_extra(st)
    S.save_state(st)
    if act in ("ENTER", "EXIT"):
        S.log_trade(log)
    print(f"[STATE] equity={eq_after:.2f} in_position={pos.in_position} stop={pos.stop:.0f}")

def next_daily_boundary():
    now = datetime.now(timezone.utc)
    nb = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return nb

def run_loop():
    if os.path.exists(C.STOP_FLAG): os.remove(C.STOP_FLAG)
    print(f"[RUN] mode={C.MODE} inst={C.INST_ID} bar={C.BAR}. Ctrl-C of `bot.py stop` om te stoppen.")
    while True:
        if os.path.exists(C.STOP_FLAG):
            print("[STOP] flag gezien, afsluiten."); return
        nb = next_daily_boundary() + timedelta(minutes=2)  # 2 min na close, candle settled
        wait = nb.timestamp() - time.time()
        print(f"[WAIT] volgende run om {nb.isoformat()} (~{int(wait)}s)")
        while time.time() < nb.timestamp():
            if os.path.exists(C.STOP_FLAG):
                print("[STOP] flag gezien."); return
            time.sleep(min(30, max(1, nb.timestamp() - time.time())))
        try:
            run_once()
        except Exception as e:
            print("[ERROR] run_once faalde:", e)  # niet crashen; morgen weer

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "once"
    if cmd == "once":  run_once()
    elif cmd == "run": run_loop()
    elif cmd == "stop":
        open(C.STOP_FLAG, "w").close(); print("[CMD] stop-flag gezet.")
    else: print("Gebruik: once | run | stop")

if __name__ == "__main__":
    main()
