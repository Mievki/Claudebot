"""Broker-abstractie: dezelfde bot-logica werkt op paper/demo/live.
   Alleen de uitvoering verschilt. Dit is de kern van een nette structuur."""
import math
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
    """Echte (of demo) orders via OKX spot. Leest saldo van de exchange.
       LET OP: test eerst uitgebreid op MODE=demo voordat je live gaat."""
    def __init__(self):
        import okx_client as okx
        self.okx = okx
        if C.MODE == "live" and not C.ALLOW_LIVE:
            raise SystemExit("LIVE geblokkeerd. Zet ALLOW_LIVE=1 in .env als je dit echt wilt.")

    def _usdt(self):
        for acct in self.okx.balance("USDT"):
            for d in acct.get("details", []):
                if d.get("ccy") == "USDT": return float(d.get("availBal", 0))
        return 0.0

    def _btc(self):
        for acct in self.okx.balance("BTC"):
            for d in acct.get("details", []):
                if d.get("ccy") == "BTC": return float(d.get("availBal", 0))
        return 0.0

    def equity(self, price):
        return self._usdt() + self._btc() * price

    def buy(self, usdt_amount, price):
        if C.MODE == "live" and self.equity(price) > C.MAX_LIVE_EQUITY:
            raise SystemExit(f"Equity boven MAX_LIVE_EQUITY={C.MAX_LIVE_EQUITY}; veiligheidsstop.")
        self.okx.place_spot_market(C.INST_ID, "buy", round(usdt_amount, 2), "quote_ccy")
        return None, price, usdt_amount * 0.001  # exacte fill via fills-history op te halen

    def sell_all(self, price):
        btc = self._btc()
        self.okx.place_spot_market(C.INST_ID, "sell", btc, "base_ccy")
        return btc, price, btc * price * 0.001

    def persist_extra(self, st):
        return st


def make_broker():
    return PaperBroker() if C.MODE == "paper" else OkxBroker()
