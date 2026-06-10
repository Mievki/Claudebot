"""Pure beslislogica — geen exchange, geen IO. Daardoor los te testen en
   1-op-1 te vergelijken met de backtest. Identieke volgorde als de backtest:
   eerst exit-check tegen de stop van gisteren, daarna trailing bijwerken."""
import math
from dataclasses import dataclass, asdict
import indicators as ind
import config as C

@dataclass
class Position:
    in_position: bool = False
    units: float = 0.0          # aangehouden BTC
    entry_price: float = 0.0
    stop: float = 0.0
    highest: float = 0.0

    @staticmethod
    def from_dict(d):
        if not d: return Position()
        return Position(**{k: d.get(k, v) for k, v in asdict(Position()).items()})

def decide(closes, highs, lows, position: Position):
    """closes/highs/lows: arrays oud->nieuw, laatste = laatste GESLOTEN candle.
       Geeft (decision_dict, mogelijk bijgewerkte Position) terug."""
    price = float(closes[-1])
    tema  = float(ind.tema(closes, C.TEMA_LEN)[-1])
    cmo   = float(ind.cmo(closes, C.CMO_WIN)[-1])
    atr   = float(ind.atr(highs, lows, closes, C.ATR_WIN)[-1])
    vol   = float(ind.realized_vol(closes, C.VOL_WIN)[-1])

    info = {"price": price, "tema": tema, "cmo": cmo, "atr": atr, "vol": vol}

    if position.in_position:
        # 1) exit-check tegen de stop van gisteren (geen lookahead)
        if price <= position.stop:
            return {**info, "action": "EXIT", "reason": f"stop {position.stop:.0f} geraakt"}, position
        # 2) trailing stop bijwerken voor morgen
        if price > position.highest:
            position.highest = price
        cand = position.highest - C.ATR_MULT * atr
        if cand > position.stop:
            position.stop = cand
        return {**info, "action": "HOLD", "reason": f"in positie, stop={position.stop:.0f}"}, position

    # geen positie -> entry-check
    if price > tema and cmo > C.CMO_TRIGGER:
        vol_ann = vol * math.sqrt(365)
        frac = min(C.F_MAX, max(C.F_MIN, C.TARGET_VOL / vol_ann)) if vol_ann > 0 else C.F_MAX
        return {**info, "action": "ENTER", "fraction": frac,
                "stop": price - C.ATR_MULT * atr,
                "reason": f"close>{tema:.0f} & CMO {cmo:.0f}>{C.CMO_TRIGGER}, inzet {frac*100:.0f}%"}, position

    return {**info, "action": "HOLD", "reason": "geen signaal (cash)"}, position
