"""Minimale OKX REST-client voor SPOT. Hergebruikt het signing-/retry-/
   time-sync-patroon uit je oude bot, maar toegespitst op wat deze strategie nodig heeft.
   demo trading via x-simulated-trading header (SIMULATED=1)."""
import os, hmac, hashlib, base64, json, time
from datetime import datetime, timezone, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlencode
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

BASE_URL   = os.getenv("BASE_URL", "https://www.okx.com").rstrip("/")
API_KEY    = os.getenv("OKX_API_KEY", "")
API_SECRET = os.getenv("OKX_API_SECRET", "")
API_PASS   = os.getenv("OKX_API_PASSPHRASE", "")
SIMULATED  = os.getenv("MODE", "paper").lower() == "demo"   # demo => simulated header
TIMEOUT    = float(os.getenv("HTTP_TIMEOUT_SEC", "12"))

_session = requests.Session()
_retry = Retry(total=5, connect=5, read=5, backoff_factor=0.5,
               status_forcelist=(429, 500, 502, 503, 504),
               allowed_methods=["GET", "POST"])
_session.mount("https://", HTTPAdapter(max_retries=_retry))
_session.headers.update({"Content-Type": "application/json"})

_delta = 0.0; _last_sync = 0.0

def _iso():
    now = datetime.now(timezone.utc) + timedelta(seconds=_delta)
    return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")

def sync_time():
    global _delta
    try:
        r = _session.get(f"{BASE_URL}/api/v5/public/time", timeout=TIMEOUT); r.raise_for_status()
        _delta = int(r.json()["data"][0]["ts"]) / 1000.0 - time.time()
    except Exception:
        _delta = 0.0

def periodic_time_sync(interval=600.0):
    global _last_sync
    if time.time() - _last_sync >= interval:
        sync_time(); _last_sync = time.time()

def _sign(ts, method, path, body=""):
    msg = f"{ts}{method.upper()}{path}{body}"
    return base64.b64encode(hmac.new(API_SECRET.encode(), msg.encode(), hashlib.sha256).digest()).decode()

def _headers(ts, sign):
    h = {"OK-ACCESS-KEY": API_KEY, "OK-ACCESS-SIGN": sign, "OK-ACCESS-TIMESTAMP": ts,
         "OK-ACCESS-PASSPHRASE": API_PASS, "Content-Type": "application/json"}
    if SIMULATED: h["x-simulated-trading"] = "1"
    return h

def _request(method, path, params=None, data=None, private=False):
    url = f"{BASE_URL}{path}"
    q = f"?{urlencode(params, doseq=True)}" if params else ""
    body = json.dumps(data) if data else ""
    if private and not (API_KEY and API_SECRET and API_PASS):
        raise RuntimeError("Ontbrekende OKX API-credentials in .env")
    ts = _iso(); sign = _sign(ts, method, f"{path}{q}", body)
    headers = _headers(ts, sign) if private else ({"x-simulated-trading": "1"} if SIMULATED else {})
    if method == "GET":
        r = _session.get(url, headers=headers, params=params, timeout=TIMEOUT)
    else:
        r = _session.post(url, headers=headers, data=body, timeout=TIMEOUT)
    r.raise_for_status()
    j = r.json()
    if str(j.get("code")) not in ("0", "None", ""):
        raise RuntimeError(f"OKX error {j.get('code')}: {j.get('msg')}")
    return j.get("data", [])

# ---- Public ----
def candles(inst_id, bar="1Dutc", limit=300):
    """Geeft GESLOTEN candles, oud->nieuw, als lijst dicts [ts,o,h,l,c].
       Pagineert met `after` (= ouder dan ts): eerst /market/candles (max 300/pagina,
       bewaart ~1440 recente bars), daarna /market/history-candles (max 100/pagina).
       Nodig omdat TEMA(120) >= ~1200 bars warmup vereist (zie tests/test_parity.py)."""
    raw = []                       # nieuw -> oud, zoals OKX levert
    after = None
    for path, page_max in (("/api/v5/market/candles", 300),
                           ("/api/v5/market/history-candles", 100)):
        while len(raw) < limit + 1:                            # +1: nieuwste kan onbevestigd zijn
            params = {"instId": inst_id, "bar": bar, "limit": str(page_max)}
            if after is not None:
                params["after"] = str(after)
            page = _request("GET", path, params=params)
            if not page:
                break                                          # endpoint uitgeput -> volgende
            if raw and int(page[0][0]) >= int(raw[-1][0]):
                raise RuntimeError("OKX paginatie niet strikt aflopend; afgebroken")
            raw.extend(page)
            after = raw[-1][0]                                 # oudste ts tot nu toe
        if len(raw) >= limit + 1:
            break
    rows = [r for r in raw if len(r) < 9 or r[8] == "1"]       # alleen bevestigde bars
    rows = rows[:limit]                                        # nieuwste `limit` stuks
    rows = list(reversed(rows))                                # oud -> nieuw
    return [{"ts": int(r[0]), "o": float(r[1]), "h": float(r[2]),
             "l": float(r[3]), "c": float(r[4])} for r in rows]

def ticker(inst_id):
    d = _request("GET", "/api/v5/market/ticker", params={"instId": inst_id})
    return d[0] if d else {}

# ---- Private (account + orders) ----
def balance(ccy=None):
    params = {"ccy": ccy} if ccy else None
    return _request("GET", "/api/v5/account/balance", params=params, private=True)

def place_spot_market(inst_id, side, sz, tgt_ccy):
    """Market spot order. BUY: sz in USDT (tgt_ccy=quote_ccy). SELL: sz in BTC (tgt_ccy=base_ccy)."""
    data = {"instId": inst_id, "tdMode": "cash", "side": side,
            "ordType": "market", "sz": str(sz), "tgtCcy": tgt_ccy}
    return _request("POST", "/api/v5/trade/order", data=data, private=True)
