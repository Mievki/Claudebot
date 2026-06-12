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
import csv
import os
import sys
import time
from datetime import datetime, timezone

import requests

import config as C
import storage as S

API = f"https://api.telegram.org/bot{C.TELEGRAM_BOT_TOKEN}"
SEP = "───────────────────"


# ---------- uitgaand ----------

def notify(text, parse_mode=None):
    """Stuur een bericht naar de eigenaar. Fail-soft: fouten alleen loggen."""
    if not (C.TELEGRAM_BOT_TOKEN and C.TELEGRAM_CHAT_ID):
        return False
    try:
        payload = {"chat_id": C.TELEGRAM_CHAT_ID, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        r = requests.post(f"{API}/sendMessage", json=payload, timeout=10)
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


def _fmt_dt(iso_str):
    """ISO timestamp → 'YYYY-MM-DD HH:MM'"""
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(iso_str)[:16]


def _nl(n, decimals=2):
    """Getal met Nederlandse opmaak: 75.078,33"""
    s = f"{float(n):,.{decimals}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


# ---------- commando's ----------

def cmd_status():
    st = S.load_state()
    pos = st.get("position") or {}
    enabled = st.get("trading_enabled", True)
    mode_label = C.MODE.upper()
    trading_icon = "🟢" if enabled else "🔴"
    trading_text = "AAN" if enabled else "UIT"
    last_candle = _fmt_ts(st.get("last_bar_ts"))

    try:
        eq, price = _equity_now()
        price_str = f"${_nl(price)}"
    except Exception:
        eq = float(st.get("equity", 0))
        price = None
        price_str = "_(niet beschikbaar)_"

    if not pos.get("in_position"):
        return (
            f"🤖 *TEMA-BOT DASHBOARD*\n"
            f"{SEP}\n"
            f"⚙️ *Systeem Status*\n"
            f"• *Modus:* `{mode_label}`\n"
            f"• *Trading:* {trading_icon} `{trading_text}`\n"
            f"• *Laatste Candle:* 📅 `{last_candle}`\n"
            f"\n"
            f"💰 *Financieel Overzicht*\n"
            f"• *Beschikbaar Cash:* `{_nl(eq)} USDT`\n"
            f"• *Totale Equity:* `{_nl(eq)} USDT`\n"
            f"• *Live BTC Koers:* {price_str}\n"
            f"\n"
            f"📈 *Strategie Status*\n"
            f"• *Positie:* ⚪ `GEEN (Volledig in Cash)`"
        )

    units = float(pos.get("units", 0))
    entry = float(pos.get("entry_price", 0))
    highest = float(pos.get("highest", 0))
    stop = float(pos.get("stop", 0))
    inzet = units * entry
    if C.MODE == "paper":
        remaining = float(st.get("cash", 0))
    else:
        remaining = (eq - units * price) if price else 0.0

    return (
        f"🤖 *TEMA-BOT DASHBOARD*\n"
        f"{SEP}\n"
        f"⚙️ *Systeem Status*\n"
        f"• *Modus:* `{mode_label}`\n"
        f"• *Trading:* {trading_icon} `{trading_text}`\n"
        f"• *Laatste Candle:* 📅 `{last_candle}`\n"
        f"\n"
        f"💰 *Financieel Overzicht*\n"
        f"• *Inzet Positie:* `{_nl(inzet)} USDT`\n"
        f"• *Resterend Cash:* `{_nl(remaining)} USDT`\n"
        f"• *Totale Equity:* `{_nl(eq)} USDT`\n"
        f"• *Live BTC Koers:* {price_str}\n"
        f"\n"
        f"📈 *Strategie Status*\n"
        f"• *Positie:* 🔵 `ACTIEF`\n"
        f"• *Omvang:* `{units:.8f} BTC`\n"
        f"• *Instapprijs:* `${_nl(entry)}`\n"
        f"• *Hoogste Close:* `${_nl(highest)}`\n"
        f"• *Trailing Stop:* 🚨 `${_nl(stop)}`"
    )


def _parse_trades():
    """Laad alle trades; koppel EXIT-rijen aan hun voorafgaande ENTER voor P&L."""
    if not os.path.exists(C.TRADES_CSV):
        return []
    with open(C.TRADES_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    result = []
    last_enter = None
    for row in rows:
        action = row.get("action", "")
        if action == "ENTER":
            last_enter = row
            result.append({"type": "ENTER", "row": row})
        elif action in ("EXIT", "PANIC_EXIT"):
            result.append({"type": action, "row": row, "entry": last_enter})
            last_enter = None
    return result


def cmd_trades():
    trades = _parse_trades()
    if not trades:
        return f"📜 *LAATSTE TRANSACTIES*\n{SEP}\nNog geen trades gelogd."

    parts = [f"📜 *LAATSTE TRANSACTIES*\n{SEP}"]
    for t in reversed(trades[-10:]):
        row = t["row"]
        dt = _fmt_dt(row.get("ts_utc", ""))
        price = float(row.get("price", 0) or 0)
        reason = row.get("reason", "-") or "-"

        if t["type"] == "ENTER":
            usdt = float(row.get("usdt", 0) or 0)
            stop_val = float(row.get("stop", 0) or 0)
            block = (
                f"🟢 *ENTER* | 📅 `{dt}`\n"
                f"• *Prijs:* `${_nl(price)}` | *Inzet:* `{_nl(usdt)} USDT`\n"
                f"• *Stop-loss:* 🚨 `${_nl(stop_val)}`\n"
                f"• *Reden:* {reason}"
            )
        else:
            units = float(row.get("units", 0) or 0)
            entry_row = t.get("entry")
            if entry_row:
                ep = float(entry_row.get("price", 0) or 0)
                pct = (price - ep) / ep * 100 if ep else 0.0
                pl = (price - ep) * units
                pct_sign = "+" if pct >= 0 else ""
                pl_sign = "+" if pl >= 0 else ""
                trend = "📈" if pl >= 0 else "📉"
                result_str = f"{trend} `{pct_sign}{_nl(pct)}% ({pl_sign}{_nl(pl)} USDT)`"
            else:
                result_str = "_onbekend_"

            exit_icon = "🛑" if t["type"] == "PANIC_EXIT" else "🔴"
            exit_label = "PANIC-EXIT" if t["type"] == "PANIC_EXIT" else "EXIT"
            block = (
                f"{exit_icon} *{exit_label}* | 📅 `{dt}`\n"
                f"• *Prijs:* `${_nl(price)}` | *Units:* `{units:.8f} BTC`\n"
                f"• *Resultaat:* {result_str}\n"
                f"• *Reden:* {reason}"
            )

        parts.append(block)

    return "\n\n".join(parts)


def cmd_equity():
    try:
        eq, price = _equity_now()
        return (
            f"💳 *PORTFOLIO WAARDERING*\n"
            f"{SEP}\n"
            f"• *Totale Equity:* `{_nl(eq)} USDT`\n"
            f"• *Live BTC Koers:* `${_nl(price)}`\n"
            f"• *Actieve Modus:* `{C.MODE.upper()}`"
        )
    except Exception as e:
        st = S.load_state()
        eq = float(st.get("equity", 0))
        return (
            f"💳 *PORTFOLIO WAARDERING*\n"
            f"{SEP}\n"
            f"• *Totale Equity:* `{_nl(eq)} USDT` _(live prijs niet beschikbaar)_\n"
            f"• *Actieve Modus:* `{C.MODE.upper()}`"
        )


def cmd_on():
    with S.locked():
        st = S.load_state()
        st["trading_enabled"] = True
        S.save_state(st)
    return (
        f"🟢 *TRADING INGESCHAKELD*\n"
        f"{SEP}\n"
        f"De bot zoekt vanaf nu automatisch naar nieuwe instapmomenten (entries) "
        f"vlak na de dagsluiting."
    )


def cmd_off():
    with S.locked():
        st = S.load_state()
        st["trading_enabled"] = False
        S.save_state(st)
    return (
        f"🔴 *TRADING PAUZE*\n"
        f"{SEP}\n"
        f"Nieuwe entries worden vanaf nu onderdrukt. Trading staat *UIT*.\n"
        f"⚠️ *Let op:* Als er momenteel een open positie actief is, blijft de "
        f"trailing stop hiervan gewoon actief totdat deze geraakt wordt."
    )


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
            return (
                f"🛑 *PANIEK-EXIT MISLUKT*\n"
                f"{SEP}\n"
                f"Geen open positie om te verkopen.\n"
                f"Trading staat nu UIT. Gebruik /on om de bot weer te activeren."
            )
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
    return (
        f"🛑 *CRITICAL: PANIEK-EXIT UITGEVOERD*\n"
        f"{SEP}\n"
        f"⚠️ *Algoritme Status:* 🔴 `STILGELEGD`\n"
        f"\n"
        f"*Uitvoering details:*\n"
        f"• *Verkocht:* `{units:.8f} BTC` @ `${_nl(fill)}`\n"
        f"• *Betaalde Fee:* `{_nl(fee)} USDT`\n"
        f"• *Resterende Equity:* `{_nl(eq)} USDT`\n"
        f"\n"
        f"_Trading staat nu volledig UIT. Gebruik /on om de bot weer te activeren._"
    )


HELP = (
    f"❌ *ONBEKEND COMMANDO*\n"
    f"{SEP}\n"
    f"Het ingevoerde commando wordt niet herkend.\n"
    f"\n"
    f"💡 *Beschikbare Commando's:*\n"
    f"• `/status` - Bekijk het live dashboard en open posities\n"
    f"• `/trades` - Toon de laatste 10 uitgevoerde trades\n"
    f"• `/equity` - Actuele mark-to-market waarde\n"
    f"• `/on` - Activeer het zoeken naar nieuwe posities\n"
    f"• `/off` - Pauzeer nieuwe posities (open stops blijven actief)\n"
    f"• `/stop` - 🚨 *PANIEK:* Verkoop alles NU direct marktconform"
)

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
        return f"⚠️ *FOUT bij* `{cmd}`: `{e}`"


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
                notify(handle_command(text), parse_mode="Markdown")
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
