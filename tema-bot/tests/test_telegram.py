"""Tests voor de Telegram-laag: whitelist-autorisatie, commando-routing en de
kill-switch/paniek-flows. Volledig offline (netwerk gemockt, state in tmp_path)."""
import json
import os

import pytest

import config as C
import storage as S
import telegram_bot as tb


@pytest.fixture
def tmp_state(monkeypatch, tmp_path):
    """Wijs state/trades naar een tijdelijke map zodat tests nooit echte data raken."""
    monkeypatch.setattr(C, "STATE_JSON", str(tmp_path / "state.json"))
    monkeypatch.setattr(C, "TRADES_CSV", str(tmp_path / "trades.csv"))
    monkeypatch.setattr(C, "TELEGRAM_CHAT_ID", "12345")
    monkeypatch.setattr(C, "MODE", "paper")
    return tmp_path


def update_from(uid, text="/status"):
    return {"update_id": 1, "message": {"from": {"id": uid}, "text": text}}


# ---------- whitelist ----------

def test_authorized_only_whitelisted_id(tmp_state):
    assert tb.authorized(update_from(12345))
    assert not tb.authorized(update_from(99999))          # vreemde -> genegeerd
    assert not tb.authorized({"update_id": 1, "message": {}})  # geen afzender
    assert not tb.authorized({"update_id": 1})            # geen message (bv. edited)


# ---------- routing ----------

def test_unknown_command_returns_help(tmp_state):
    assert tb.handle_command("/foo") == tb.HELP
    assert tb.handle_command("") == tb.HELP

def test_command_with_botname_suffix_routes(tmp_state):
    # Telegram stuurt in groepen "/status@MijnBot"; moet gewoon routeren
    out = tb.handle_command("/off@temabot")
    assert "UIT" in out


# ---------- kill-switch ----------

def test_off_and_on_toggle_state(tmp_state):
    tb.handle_command("/off")
    assert S.load_state()["trading_enabled"] is False
    tb.handle_command("/on")
    assert S.load_state()["trading_enabled"] is True


def test_off_suppresses_entry_in_bot(tmp_state, monkeypatch):
    """De dagelijkse job moet een ENTER-signaal onderdrukken als trading uit staat."""
    import bot
    import numpy as np
    S.save_state({"trading_enabled": False})
    monkeypatch.setattr(bot.okx, "periodic_time_sync", lambda: None)
    monkeypatch.setattr(bot, "fetch_history",
                        lambda: ([100.0] * 50, [101.0] * 50, [99.0] * 50, 1234))
    import strategy
    monkeypatch.setattr(strategy.ind, "tema", lambda c, n: np.array([90.0]))
    monkeypatch.setattr(strategy.ind, "cmo", lambda c, n: np.array([50.0]))
    monkeypatch.setattr(strategy.ind, "atr", lambda h, l, c, n: np.array([2.0]))
    monkeypatch.setattr(strategy.ind, "realized_vol", lambda c, n: np.array([0.02]))
    sent = []
    monkeypatch.setattr(bot.tg, "notify", lambda t: sent.append(t) or True)

    bot.run_once()

    st = S.load_state()
    assert st["position"]["in_position"] is False         # GEEN positie geopend
    assert any("ONDERDRUKT" in m for m in sent)           # wel gemeld via Telegram


# ---------- paniek-knop ----------

def test_stop_without_position_only_disables(tmp_state):
    out = tb.handle_command("/stop")
    assert "Geen open positie" in out
    assert S.load_state()["trading_enabled"] is False


def test_stop_with_position_sells_and_disables(tmp_state, monkeypatch):
    # paper-positie: 0.02 BTC, 100 USDT cash
    S.save_state({"trading_enabled": True, "cash": 100.0, "units": 0.02,
                  "position": {"in_position": True, "units": 0.02,
                               "entry_price": 50000.0, "stop": 48000.0, "highest": 52000.0}})
    monkeypatch.setattr(tb, "_live_price", lambda: 51000.0)

    out = tb.handle_command("/stop")

    st = S.load_state()
    assert st["trading_enabled"] is False
    assert st["position"]["in_position"] is False
    assert st["units"] == 0.0
    assert st["equity"] > 1000.0                          # ~100 + 0.02*51000 - kosten
    assert "PANIEK-EXIT" in out
    # trade is gelogd
    assert "PANIC_EXIT" in open(C.TRADES_CSV).read()


# ---------- notify is fail-soft ----------

def test_notify_without_credentials_is_noop(monkeypatch):
    monkeypatch.setattr(C, "TELEGRAM_BOT_TOKEN", "")
    assert tb.notify("x") is False                        # geen exception, geen netwerk
