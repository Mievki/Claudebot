"""END-TO-END PARITEIT: de volledige backtest-loop uit de notebook (referentie,
letterlijk gekopieerd) versus dezelfde historie dag-voor-dag door strategy.decide().
Als deze test groen is, neemt de bot exact dezelfde beslissingen als de backtest:
zelfde trades, zelfde data, zelfde eindwaarde."""
import numpy as np
import pytest

from strategy import Position, decide
from test_parity import nb_tema, nb_cmo, nb_atr, nb_vol

FEE, SLIP = 0.002, 0.001          # backtest: 0,2% per kant, 0,1% slippage op stop-exit
START = 1000.0


def reference_backtest(df):
    """VERBATIM de loop uit TEMA_CMO_BTC_voltarget.ipynb, cel 2 (alleen prints weg)."""
    df = df.copy()
    df["TEMA"] = nb_tema(df["close"], 120)
    df["CMO"] = nb_cmo(df["close"], 14)
    df["ATR"] = nb_atr(df, 14)
    df["VOL"] = nb_vol(df, 30)
    df = df.dropna().reset_index(drop=True)

    cmo_trigger, atr_multiplier = 10, 3.5
    target_vol, f_min, f_max = 0.40, 0.10, 1.0
    cash, btc_holding, in_position = START, 0.0, False
    stop_loss_price = highest_price_in_trade = 0.0
    trades = []

    for i in range(len(df)):
        row = df.iloc[i]
        price, tema_v, cmo_v = row["close"], row["TEMA"], row["CMO"]
        atr_v, vol_v, date = row["ATR"], row["VOL"], row["date"]

        if in_position and price <= stop_loss_price:
            fill = price * (1 - SLIP)
            cash += btc_holding * fill * (1 - FEE)
            btc_holding, in_position = 0.0, False
            trades.append(("EXIT", date, price))
            continue

        if in_position:
            if price > highest_price_in_trade:
                highest_price_in_trade = price
            pot = highest_price_in_trade - atr_multiplier * atr_v
            if pot > stop_loss_price:
                stop_loss_price = pot

        if (not in_position) and price > tema_v and cmo_v > cmo_trigger:
            vol_ann = vol_v * np.sqrt(365)
            fraction = min(f_max, max(f_min, target_vol / vol_ann)) if vol_ann > 0 else f_max
            invest = cash * fraction
            btc_holding = invest * (1 - FEE) / price
            cash -= invest
            in_position = True
            highest_price_in_trade = price
            stop_loss_price = price - atr_multiplier * atr_v
            trades.append(("ENTER", date, price))

    return trades, cash + btc_holding * df.iloc[-1]["close"]


def bot_replay(df):
    """Zelfde historie, maar elke dag beslist strategy.decide() — zoals de live bot."""
    closes = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    dates = df["date"].to_numpy()

    cash, pos = START, Position()
    trades = []
    start = 30  # eerste rij die de notebook na dropna() overhoudt (VOL-window 30)

    for j in range(start, len(df)):
        price = closes[j]
        d, pos = decide(closes[: j + 1], highs[: j + 1], lows[: j + 1], pos)

        if d["action"] == "EXIT":
            fill = price * (1 - SLIP)
            cash += pos.units * fill * (1 - FEE)
            pos = Position()
            trades.append(("EXIT", dates[j], price))
        elif d["action"] == "ENTER":
            invest = cash * d["fraction"]
            units = invest * (1 - FEE) / price
            cash -= invest
            pos = Position(in_position=True, units=units, entry_price=price,
                           stop=d["stop"], highest=price)
            trades.append(("ENTER", dates[j], price))

    return trades, cash + pos.units * closes[-1]


def test_bot_replays_backtest_exactly(btc_df):
    ref_trades, ref_final = reference_backtest(btc_df)
    bot_trades, bot_final = bot_replay(btc_df)

    print(f"\n  referentie: {len(ref_trades)} trade-events, eindwaarde EUR {ref_final:,.2f}")
    print(f"  bot-replay: {len(bot_trades)} trade-events, eindwaarde EUR {bot_final:,.2f}")

    assert len(ref_trades) > 20, "sanity: verwacht tientallen trade-events over 2018-2026"
    assert bot_trades == ref_trades, "trade-volgorde/datums/prijzen wijken af van de backtest"
    assert bot_final == pytest.approx(ref_final, rel=1e-12)
