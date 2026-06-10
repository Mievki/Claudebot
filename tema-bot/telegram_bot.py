"""Telegram-integratie.
   - notify(text): push naar de eigenaar; mag NOOIT de trading-job laten crashen.
   - `python telegram_bot.py listen`: long-polling listener voor commando's,
     UITSLUITEND van het gewhiteliste TELEGRAM_CHAT_ID (jouw numerieke user-id).

   Commando's:
     /status  positie, stop, equity, trading aan/uit
     /trades  laatste 10 trades
     /equity  actuele equity (mark-to-market op de live prijs)
     /off     geen NIEUWE entries meer (open positie behoudt trailing stop)
     /on      trading weer aan
     /stop    PANIEK: verkoop open positie NU + trading uit"""
import os
import sys
import time
from datetime import datetime, timezone

import requests

import config as C
import storage as S

API = f"https://api.telegram.org/bot{C.TELEGRAM_BOT_TOKEN}"


# ---------- uitgaand ----------

def notify(text):
    """Stuur een bericht naar de eigenaar. Fail-soft: fouten alleen loggen."""
    if not (C.TELEGRAM_BOT_TOKEN and C.TELEGRAM_CHAT_ID):
        return False
    try:
        r = requests.post(f"{API}/sendMessage",
                          json={"chat_id": C.TELEGRAM_CHAT_ID, "text": text},
                          timeout=10)
        if not r.ok:
            print(f"[TG] sendMessage faalde: {r.status_code} {r.text[:200]}")
        return r.ok
    except Exception as e:
        print(f"[TG] notify faalde (genegeerd): {e}")
        return False


# ---------- helpers ----------

def _live_price():
    import okx_client as okx
    return float(okx.ticker(C.INST_ID).get("last", 0) or 0)


def _equity_now():
    from broker import make_broker
    price = _live_price()
    return make_broker().equity(price), price


def _fmt_ts(ms):
    if not ms:
        return "-"
    return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).strftime("%Y-%m-%d")


# ---------- commando's ----------

def cmd_status():
    st = S.load_state()
    pos = st.get("position") or {}
    enabled = st.get("trading_enabled", True)
    lines = [f"mode: {C.MODE} | {C.INST_ID}",
             f"trading: {'AAN' if enabled else 'UIT'}",
             f"laatste candle: {_fmt_ts(st.get('last_bar_ts'))}"]
    if pos.get("in_position"):
        lines += [f"positie: {pos.get('units'):.8f} BTC @ {pos.get('entry_price'):.2f}",
                  f"stop: {pos.get('stop'):.2f} | hoogste close: {pos.get('highest'):.2f}"]
    else:
        lines.append("positie: geen (cash)")
    try:
        eq, price = _equity_now()
        lines.append(f"equity: {eq:.2f} USDT (BTC {price:.0f})")
    except Exception as e:
        lines.append(f"equity: {st.get('equity', '?')} (live prijs faalde: {e})")
    return "\n".join(lines)


def cmd_trades():
    if not os.path.exists(C.TRADES_CSV):
        return "Nog geen trades gelogd."
    lines = open(C.TRADES_CSV).read().strip().splitlines()
    if len(lines) < 2:
        return "Nog geen trades gelogd."
    return "Laatste trades:\n" + "\n".join(lines[-10:])


def cmd_equity():
    try:
        eq, price = _equity_now()
        return f"Equity: {eq:.2f} USDT (BTC {price:.2f}, mode={C.MODE})"
    except Exception as e:
        st = S.load_state()
        return f"Live prijs faalde ({e}); laatst bekende equity: {st.get('equity', '?')}"


def cmd_on():
    with S.locked():
        st = S.load_state()
        st["trading_enabled"] = True
        S.save_state(st)
    return "Trading staat AAN: entries zijn weer toegestaan."


def cmd_off():
    with S.locked():
        st = S.load_state()
        st["trading_enabled"] = False
        S.save_state(st)
    return ("Trading staat UIT: geen nieuwe entries.\n"
            "Een open positie behoudt haar trailing stop. /on om te hervatten.")


def cmd_stop():
    """PANIEK-knop: verkoop een open positie direct en zet trading uit."""
    from broker import make_broker
    from strategy import Position
    with S.locked():
        st = S.load_state()
        st["trading_enabled"] = False
        pos = Position.from_dict(st.get("position"))
        if not pos.in_position:
            S.save_state(st)
            return "Geen open positie. Trading staat nu UIT (/on om te hervatten)."
        price = _live_price() or pos.entry_price
        broker = make_broker()
        units, fill, fee = broker.sell_all(price)
        st["position"] = Position().__dict__
        st = broker.persist_extra(st)
        eq = broker.equity(fill)
        st["equity"] = eq
        S.save_state(st)
        S.log_trade({"ts_utc": S.now_iso(), "action": "PANIC_EXIT",
                     "price": f"{fill:.2f}", "units": units, "fee": f"{fee:.2f}",
                     "equity_after": f"{eq:.2f}", "reason": "/stop via Telegram"})
    return (f"PANIEK-EXIT uitgevoerd: {units:.8f} BTC verkocht @ {fill:.2f} "
            f"(fee {fee:.2f}).\nEquity: {eq:.2f} USDT. Trading staat UIT.")


HELP = ("Commando's: /status /trades /equity /off /on /stop\n"
        "/off = geen nieuwe entries | /stop = verkoop positie NU + trading uit")

COMMANDS = {"/status": cmd_status, "/trades": cmd_trades, "/equity": cmd_equity,
            "/on": cmd_on, "/off": cmd_off, "/stop": cmd_stop}


def handle_command(text):
    cmd = (text or "").strip().split()[0].split("@")[0].lower() if text else ""
    fn = COMMANDS.get(cmd)
    if fn is None:
        return HELP
    try:
        return fn()
    except Exception as e:
        return f"FOUT bij {cmd}: {e}"


def authorized(update):
    """Alleen privé-berichten van exact het gewhiteliste user-id."""
    msg = update.get("message") or {}
    uid = str((msg.get("from") or {}).get("id", ""))
    return bool(uid) and uid == str(C.TELEGRAM_CHAT_ID)


# ---------- listener ----------

def listen():
    if not (C.TELEGRAM_BOT_TOKEN and C.TELEGRAM_CHAT_ID):
        raise SystemExit("TELEGRAM_BOT_TOKEN en TELEGRAM_CHAT_ID ontbreken in .env")
    print(f"[TG] listener gestart (whitelist: {C.TELEGRAM_CHAT_ID}, mode={C.MODE})")
    offset = None
    while True:
        try:
            params = {"timeout": 50}
            if offset is not None:
                params["offset"] = offset
            r = requests.get(f"{API}/getUpdates", params=params, timeout=60)
            for u in r.json().get("result", []):
                offset = u["update_id"] + 1
                text = ((u.get("message") or {}).get("text") or "").strip()
                if not authorized(u):
                    frm = ((u.get("message") or {}).get("from") or {}).get("id")
                    print(f"[TG] GENEGEERD: bericht van niet-gewhitelist id {frm!r}")
                    continue
                if not text:
                    continue
                print(f"[TG] commando: {text}")
                notify(handle_command(text))
        except KeyboardInterrupt:
            print("[TG] gestopt."); return
        except Exception as e:
            print(f"[TG] fout (opnieuw over 5s): {e}")
            time.sleep(5)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        ok = notify(f"tema-bot testbericht ({S.now_iso()}) — Telegram werkt.")
        print("verzonden!" if ok else "NIET verzonden — check token/chat_id.")
    else:
        listen()
