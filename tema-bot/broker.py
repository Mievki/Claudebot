"""Broker-abstractie: dezelfde bot-logica werkt op paper/demo/live.
   Alleen de uitvoering verschilt. Dit is de kern van een nette structuur."""
import time
from decimal import Decimal

import config as C
import storage as S

class PaperBroker:
    """Lokale simulatie met ECHTE prijzen. Verstuurt niets naar OKX. Nul risico."""
    def __init__(self):
        st = S.load_state()
        self.cash  = float(st.get("cash", C.START_EQUITY))
        self.units = float(st.get("units", 0.0))

    def equity(self, price):
        return self.cash + self.units * price

    def buy(self, usdt_amount, price):
        fill = price * (1 + C.PAPER_SLIP)
        fee = usdt_amount * C.PAPER_FEE
        units = (usdt_amount - fee) / fill
        self.cash -= usdt_amount
        self.units += units
        return units, fill, fee

    def sell_all(self, price):
        fill = price * (1 - C.PAPER_SLIP)
        gross = self.units * fill
        fee = gross * C.PAPER_FEE
        self.cash += gross - fee
        units = self.units; self.units = 0.0
        return units, fill, fee

    def persist_extra(self, st):
        st["cash"] = self.cash; st["units"] = self.units
        return st


class OkxBroker:
    """Echte (of demo) orders via OKX spot. Leest saldo van de exchange en haalt
       na elke order de ECHTE fill op (units/prijs/fee) via het fills-endpoint.
       LET OP: test eerst uitgebreid op MODE=demo voordat je live gaat."""
    def __init__(self):
        import okx_client as okx
        self.okx = okx
        if C.MODE == "live" and not C.ALLOW_LIVE:
            raise SystemExit("LIVE geblokkeerd. Zet ALLOW_LIVE=1 in .env als je dit echt wilt.")
        self.base_ccy, self.quote_ccy = C.INST_ID.split("-")
        self._inst = None

    # ---- saldo ----
    def _bal(self, ccy):
        for acct in self.okx.balance(ccy):
            for d in acct.get("details", []):
                if d.get("ccy") == ccy:
                    return float(d.get("availBal", 0))
        return 0.0

    def _usdt(self): return self._bal(self.quote_ccy)
    def _btc(self):  return self._bal(self.base_ccy)

    def equity(self, price):
        return self._usdt() + self._btc() * price

    # ---- instrument-specs en afronding ----
    def _instrument(self):
        if self._inst is None:
            self._inst = self.okx.instrument(C.INST_ID)
            if not self._inst:
                raise RuntimeError(f"Instrument {C.INST_ID} niet gevonden")
        return self._inst

    def _round_lot(self, qty):
        """Rond een basis-ccy hoeveelheid NAAR BENEDEN af op lotSz (nooit te veel verkopen)."""
        lot = Decimal(self._instrument().get("lotSz", "0.00000001"))
        return float((Decimal(str(qty)) // lot) * lot)

    # ---- order-afhandeling ----
    def _await_fill(self, ord_id, timeout=30.0):
        t0 = time.time()
        while True:
            od = self.okx.order_detail(C.INST_ID, ord_id)
            state = od.get("state")
            if state == "filled":
                return od
            if state == "canceled":
                raise RuntimeError(f"Order {ord_id} geannuleerd: {od.get('cancelSource', '?')}")
            if time.time() - t0 > timeout:
                raise RuntimeError(f"Order {ord_id} niet gevuld binnen {timeout}s (state={state})")
            time.sleep(1.0)

    def _fill_summary(self, ord_id):
        """(bruto units, gewogen gem. prijs, fee_base, fee_quote) uit de echte fills.
           fillSz is altijd basis-ccy; fee is negatief, in feeCcy."""
        rows = []
        for _ in range(5):                      # fills kunnen kort na 'filled' nalopen
            rows = self.okx.fills(C.INST_ID, ord_id)
            if rows:
                break
            time.sleep(1.0)
        if not rows:
            raise RuntimeError(f"Geen fills gevonden voor order {ord_id}")
        units = sum(float(r["fillSz"]) for r in rows)
        avg = sum(float(r["fillPx"]) * float(r["fillSz"]) for r in rows) / units
        fee_base  = sum(float(r["fee"]) for r in rows if r.get("feeCcy") == self.base_ccy)
        fee_quote = sum(float(r["fee"]) for r in rows if r.get("feeCcy") == self.quote_ccy)
        return units, avg, fee_base, fee_quote

    # ---- broker-API ----
    def buy(self, usdt_amount, price):
        if C.MODE == "live" and self.equity(price) > C.MAX_LIVE_EQUITY:
            raise SystemExit(f"Equity boven MAX_LIVE_EQUITY={C.MAX_LIVE_EQUITY}; veiligheidsstop.")
        ord_id = self.okx.place_spot_market(C.INST_ID, "buy", round(usdt_amount, 2), "quote_ccy")
        self._await_fill(ord_id)
        units, avg, fee_base, fee_quote = self._fill_summary(ord_id)
        # koop-fee wordt in basis-ccy (BTC) ingehouden: netto ontvangen = bruto + fee (fee<0)
        net_units = units + fee_base
        fee_usdt = -fee_base * avg + -fee_quote
        return net_units, avg, fee_usdt

    def sell_all(self, price):
        btc = self._round_lot(self._btc())
        min_sz = float(self._instrument().get("minSz", "0"))
        if btc < min_sz:
            raise RuntimeError(f"Saldo {btc} {self.base_ccy} onder minSz {min_sz}; "
                               "niets te verkopen (positie-administratie controleren!)")
        ord_id = self.okx.place_spot_market(C.INST_ID, "sell", btc, "base_ccy")
        self._await_fill(ord_id)
        units, avg, fee_base, fee_quote = self._fill_summary(ord_id)
        fee_usdt = -fee_base * avg + -fee_quote   # verkoop-fee komt in USDT binnen (fee<0)
        return units, avg, fee_usdt

    def persist_extra(self, st):
        return st


def make_broker():
    return PaperBroker() if C.MODE == "paper" else OkxBroker()
