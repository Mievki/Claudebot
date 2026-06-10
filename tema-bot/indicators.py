"""Indicatoren die EXACT je backtest reproduceren (pandas, identieke formules).
   Wijk hier NIET van af: een andere CMO/ATR-formule = een andere strategie."""
import pandas as pd

def tema(close, length):
    s = pd.Series(close, dtype="float64")
    e1 = s.ewm(span=length, adjust=False).mean()
    e2 = e1.ewm(span=length, adjust=False).mean()
    e3 = e2.ewm(span=length, adjust=False).mean()
    return (3 * (e1 - e2) + e3).to_numpy()

def cmo(close, window):
    s = pd.Series(close, dtype="float64")
    d = s.diff()
    up = d.clip(lower=0).rolling(window).sum()
    dn = (-d.clip(upper=0)).rolling(window).sum()
    return (100 * (up - dn) / (up + dn)).to_numpy()

def atr(high, low, close, window=14):
    h = pd.Series(high, dtype="float64"); l = pd.Series(low, dtype="float64"); c = pd.Series(close, dtype="float64")
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    return tr.rolling(window).mean().to_numpy()

def realized_vol(close, window=30):
    """Dagelijkse gerealiseerde volatiliteit (std van dagrendementen)."""
    return pd.Series(close, dtype="float64").pct_change().rolling(window).std().to_numpy()
