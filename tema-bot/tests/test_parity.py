"""PARITY: indicators.py moet bit-voor-bit gelijk zijn aan de backtest-notebook
(TEMA_CMO_BTC_voltarget.ipynb). De referentie-functies hieronder zijn LETTERLIJK
uit de notebook gekopieerd — wijzig ze nooit; bij een mismatch is indicators.py fout."""
import numpy as np
import pandas as pd

import indicators as ind

# ---------- referentie: VERBATIM uit TEMA_CMO_BTC_voltarget.ipynb, cel 1 ----------

def nb_tema(series, length):
    ema1 = series.ewm(span=length, adjust=False).mean()
    ema2 = ema1.ewm(span=length, adjust=False).mean()
    ema3 = ema2.ewm(span=length, adjust=False).mean()
    return 3*(ema1 - ema2) + ema3

def nb_cmo(series, window):
    delta = series.diff()
    up = delta.clip(lower=0).rolling(window).sum()
    down = (-delta.clip(upper=0)).rolling(window).sum()
    return 100*(up - down)/(up + down)

def nb_atr(df, window=14):
    high_low = df['high'] - df['low']
    high_cp  = (df['high'] - df['close'].shift(1)).abs()
    low_cp   = (df['low']  - df['close'].shift(1)).abs()
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    return tr.rolling(window).mean()

def nb_vol(df, window=30):
    return df['close'].pct_change().rolling(window).std()

# ---------- bit-voor-bit pariteit op de echte backtest-data ----------

def test_tema_parity(btc_df):
    ref = nb_tema(btc_df["close"], 120).to_numpy()
    got = ind.tema(btc_df["close"].to_numpy(), 120)
    np.testing.assert_array_equal(got, ref)

def test_cmo_parity(btc_df):
    ref = nb_cmo(btc_df["close"], 14).to_numpy()
    got = ind.cmo(btc_df["close"].to_numpy(), 14)
    np.testing.assert_array_equal(got, ref)

def test_atr_parity(btc_df):
    ref = nb_atr(btc_df, 14).to_numpy()
    got = ind.atr(btc_df["high"].to_numpy(), btc_df["low"].to_numpy(),
                  btc_df["close"].to_numpy(), 14)
    np.testing.assert_array_equal(got, ref)

def test_realized_vol_parity(btc_df):
    ref = nb_vol(btc_df, 30).to_numpy()
    got = ind.realized_vol(btc_df["close"].to_numpy(), 30)
    np.testing.assert_array_equal(got, ref)

# ---------- warmup-convergentie ----------
# ewm(adjust=False) hangt af van het startpunt van de reeks. De backtest rekent
# TEMA over de volledige historie; live haalt de bot maar HIST_BARS candles op.
# Deze test meet hoeveel bars nodig zijn zodat (a) de laatste TEMA-waarde < $0.01
# afwijkt en (b) het entry-signaal over het laatste jaar identiek is, en eist
# dat het geconfigureerde HIST_BARS daaraan voldoet.

def _signal(close_tail):
    s = pd.Series(close_tail).reset_index(drop=True)
    t = nb_tema(s, 120)
    c = nb_cmo(s, 14)
    return ((s > t) & (c > 10)).to_numpy()

def test_warmup_convergence(btc_df):
    import config as C
    close = btc_df["close"]
    full_tema = nb_tema(close, 120).to_numpy()
    full_sig = _signal(close.to_numpy())

    print("\n  N bars | laatste-TEMA fout ($) | signaal laatste 365d gelijk?")
    results = {}
    for n in (300, 500, 750, 1000, 1200, 1500):
        tail = close.to_numpy()[-n:]
        err = abs(nb_tema(pd.Series(tail), 120).to_numpy()[-1] - full_tema[-1])
        sig_ok = bool((_signal(tail)[-365:] == full_sig[-365:]).all()) if n >= 365 + 120 else None
        results[n] = (err, sig_ok)
        print(f"  {n:6d} | {err:21.6f} | {sig_ok}")

    n = C.HIST_BARS
    tail = close.to_numpy()[-n:]
    err = abs(nb_tema(pd.Series(tail), 120).to_numpy()[-1] - full_tema[-1])
    sig_ok = (_signal(tail)[-365:] == full_sig[-365:]).all()
    print(f"  -> geconfigureerd HIST_BARS={n}: fout ${err:.6f}, signaal-gelijk={bool(sig_ok)}")
    assert err < 0.01, f"HIST_BARS={n} te klein: laatste-TEMA fout ${err:.4f} >= $0.01"
    assert sig_ok, f"HIST_BARS={n} te klein: signaalverschil binnen laatste 365 dagen"
