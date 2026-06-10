"""Unit-tests voor OkxBroker-orderafhandeling met een nep-OKX-module:
fills-aggregatie, fee-administratie (BTC-fee bij koop, USDT-fee bij verkoop),
lotSz-afronding en de minSz-guard. Geen netwerk nodig."""
import pytest

from broker import OkxBroker, PaperBroker


class FakeOkx:
    """Minimale nabootsing van okx_client voor BTC-USDT."""
    def __init__(self):
        self.placed = []
        self.fills_rows = []
        self.balances = {"USDT": 1000.0, "BTC": 0.5}

    def balance(self, ccy):
        return [{"details": [{"ccy": ccy, "availBal": str(self.balances.get(ccy, 0.0))}]}]

    def instrument(self, inst_id):
        return {"instId": inst_id, "lotSz": "0.00000001", "minSz": "0.00001"}

    def place_spot_market(self, inst_id, side, sz, tgt_ccy):
        self.placed.append((side, sz, tgt_ccy))
        return "ORD123"

    def order_detail(self, inst_id, ord_id):
        return {"ordId": ord_id, "state": "filled"}

    def fills(self, inst_id, ord_id):
        return self.fills_rows


@pytest.fixture
def okx_broker():
    b = OkxBroker()           # MODE=paper in tests -> geen live-gate
    b.okx = FakeOkx()
    return b


def test_buy_returns_net_units_and_usdt_fee(okx_broker):
    # 2 partial fills; koop-fee negatief in BTC -> netto units = bruto + fee
    okx_broker.okx.fills_rows = [
        {"fillSz": "0.006", "fillPx": "60000", "fee": "-0.000012", "feeCcy": "BTC"},
        {"fillSz": "0.004", "fillPx": "60100", "fee": "-0.000008", "feeCcy": "BTC"},
    ]
    units, avg, fee_usdt = okx_broker.buy(601.0, 60000.0)
    assert units == pytest.approx(0.010 - 0.000020)
    assert avg == pytest.approx((0.006 * 60000 + 0.004 * 60100) / 0.010)
    assert fee_usdt == pytest.approx(0.000020 * avg)
    assert okx_broker.okx.placed == [("buy", 601.0, "quote_ccy")]


def test_sell_all_rounds_down_to_lot_and_reports_usdt_fee(okx_broker):
    okx_broker.okx.balances["BTC"] = 0.123456789123   # meer decimalen dan lotSz
    okx_broker.okx.fills_rows = [
        {"fillSz": "0.12345678", "fillPx": "60000", "fee": "-14.81", "feeCcy": "USDT"},
    ]
    units, avg, fee_usdt = okx_broker.sell_all(60000.0)
    side, sz, tgt = okx_broker.okx.placed[0]
    assert side == "sell" and tgt == "base_ccy"
    assert sz == pytest.approx(0.12345678)            # afgerond NAAR BENEDEN op lotSz
    assert units == pytest.approx(0.12345678)
    assert fee_usdt == pytest.approx(14.81)


def test_sell_all_refuses_below_min_size(okx_broker):
    okx_broker.okx.balances["BTC"] = 0.000004          # onder minSz 0.00001
    with pytest.raises(RuntimeError, match="minSz"):
        okx_broker.sell_all(60000.0)
    assert okx_broker.okx.placed == []                 # er is GEEN order geplaatst


def test_order_rejection_raises():
    import okx_client
    # sCode != 0 betekent geweigerd; place_spot_market moet dat hard maken
    class R:
        @staticmethod
        def fake_request(method, path, params=None, data=None, private=False):
            return [{"sCode": "51008", "sMsg": "Insufficient balance", "ordId": ""}]
    orig = okx_client._request
    okx_client._request = R.fake_request
    try:
        with pytest.raises(RuntimeError, match="geweigerd"):
            okx_client.place_spot_market("BTC-USDT", "buy", 100, "quote_ccy")
    finally:
        okx_client._request = orig


def test_paper_roundtrip_conserves_value_minus_costs():
    # sanity op PaperBroker: koop+verkoop op gelijke prijs verliest precies fees+slip
    b = PaperBroker.__new__(PaperBroker)
    b.cash, b.units = 1000.0, 0.0
    price = 50000.0
    b.buy(1000.0, price)
    b.sell_all(price)
    assert b.units == 0.0
    assert b.cash < 1000.0                             # kosten zijn betaald
    assert b.cash == pytest.approx(1000.0 * (1 - 0.002) / (1 + 0.001) * (1 - 0.001) * (1 - 0.002))
