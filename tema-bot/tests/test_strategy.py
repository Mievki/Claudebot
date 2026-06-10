"""Pure unit-tests voor strategy.decide(). Indicatoren worden gemockt zodat
elke regel van de beslislogica geisoleerd getest wordt (de formules zelf
worden in test_parity.py bewezen)."""
import math

import numpy as np
import pytest

import strategy
from strategy import Position, decide

DUMMY = np.array([100.0])  # highs/lows worden alleen door (gemockte) ATR gebruikt


def patch_ind(monkeypatch, tema, cmo, atr, vol):
    monkeypatch.setattr(strategy.ind, "tema", lambda c, n: np.array([tema]))
    monkeypatch.setattr(strategy.ind, "cmo", lambda c, n: np.array([cmo]))
    monkeypatch.setattr(strategy.ind, "atr", lambda h, l, c, n: np.array([atr]))
    monkeypatch.setattr(strategy.ind, "realized_vol", lambda c, n: np.array([vol]))


def closes(price):
    return np.array([price] * 5, dtype=float)


# ---------- ENTRY ----------

def test_enter_on_signal(monkeypatch):
    patch_ind(monkeypatch, tema=100.0, cmo=20.0, atr=2.0, vol=0.8 / math.sqrt(365))
    d, pos = decide(closes(105.0), DUMMY, DUMMY, Position())
    assert d["action"] == "ENTER"
    assert d["fraction"] == pytest.approx(0.40 / 0.8)          # vol-targeting
    assert d["stop"] == pytest.approx(105.0 - 3.5 * 2.0)       # close - 3.5*ATR
    assert not pos.in_position                                  # decide doet GEEN IO/positie-mutatie bij entry


def test_no_enter_when_cmo_at_trigger(monkeypatch):
    # trigger is STRIKT groter dan 10 (backtest: cmo_v > cmo_trigger)
    patch_ind(monkeypatch, tema=100.0, cmo=10.0, atr=2.0, vol=0.02)
    d, _ = decide(closes(105.0), DUMMY, DUMMY, Position())
    assert d["action"] == "HOLD"


def test_no_enter_below_tema(monkeypatch):
    patch_ind(monkeypatch, tema=100.0, cmo=50.0, atr=2.0, vol=0.02)
    d, _ = decide(closes(100.0), DUMMY, DUMMY, Position())   # close == TEMA -> geen entry
    assert d["action"] == "HOLD"


# ---------- POSITIE-SIZING (clip) ----------

@pytest.mark.parametrize("vol_ann,expected", [
    (4.00, 0.10),   # extreem hoge vol -> floor 0.10
    (0.20, 1.00),   # lage vol -> cap 1.0 (geen hefboom)
    (0.80, 0.50),   # midden: 0.40/0.80
])
def test_fraction_clip(monkeypatch, vol_ann, expected):
    patch_ind(monkeypatch, tema=100.0, cmo=20.0, atr=2.0, vol=vol_ann / math.sqrt(365))
    d, _ = decide(closes(105.0), DUMMY, DUMMY, Position())
    assert d["fraction"] == pytest.approx(expected)


def test_fraction_when_vol_zero(monkeypatch):
    patch_ind(monkeypatch, tema=100.0, cmo=20.0, atr=2.0, vol=0.0)
    d, _ = decide(closes(105.0), DUMMY, DUMMY, Position())
    assert d["fraction"] == 1.0                                # F_MAX fallback, zoals backtest


# ---------- EXIT ----------

def test_exit_when_close_at_stop(monkeypatch):
    # exit op close <= stop (inclusief gelijk), tegen de stop van GISTEREN
    patch_ind(monkeypatch, tema=0.0, cmo=0.0, atr=2.0, vol=0.02)
    pos = Position(in_position=True, units=1.0, entry_price=100.0, stop=95.0, highest=110.0)
    d, pos2 = decide(closes(95.0), DUMMY, DUMMY, pos)
    assert d["action"] == "EXIT"
    assert pos2.stop == 95.0                                   # exit VOOR ratchet: stop onaangetast


def test_exit_checked_before_ratchet(monkeypatch):
    # close raakt stop EN zou een nieuwe high zijn -> backtest-volgorde eist EXIT
    patch_ind(monkeypatch, tema=0.0, cmo=0.0, atr=100.0, vol=0.02)
    pos = Position(in_position=True, units=1.0, entry_price=100.0, stop=120.0, highest=110.0)
    d, pos2 = decide(closes(115.0), DUMMY, DUMMY, pos)
    assert d["action"] == "EXIT"
    assert pos2.highest == 110.0                               # geen ratchet meer na exit-beslissing


# ---------- TRAILING STOP ----------

def test_stop_ratchets_up(monkeypatch):
    patch_ind(monkeypatch, tema=0.0, cmo=0.0, atr=2.0, vol=0.02)
    pos = Position(in_position=True, units=1.0, entry_price=100.0, stop=95.0, highest=100.0)
    d, pos2 = decide(closes(110.0), DUMMY, DUMMY, pos)
    assert d["action"] == "HOLD"
    assert pos2.highest == 110.0
    assert pos2.stop == pytest.approx(110.0 - 3.5 * 2.0)       # 103: omhoog geratchet


def test_stop_never_moves_down(monkeypatch):
    # grote ATR -> kandidaat-stop onder de huidige stop -> stop blijft staan
    patch_ind(monkeypatch, tema=0.0, cmo=0.0, atr=50.0, vol=0.02)
    pos = Position(in_position=True, units=1.0, entry_price=100.0, stop=98.0, highest=110.0)
    d, pos2 = decide(closes(109.0), DUMMY, DUMMY, pos)
    assert d["action"] == "HOLD"
    assert pos2.stop == 98.0
