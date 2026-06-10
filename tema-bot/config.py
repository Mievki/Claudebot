"""Centrale configuratie. Alles via .env zodat code en geheimen gescheiden blijven."""
import os
from dotenv import load_dotenv
load_dotenv()

# ---- Strategie (MOET exact je gevalideerde backtest matchen) ----
INST_ID     = os.getenv("INST_ID", "BTC-USDT")   # SPOT pair, long-only
BAR         = os.getenv("BAR", "1Dutc")          # dagelijkse candle, UTC-close
TEMA_LEN    = int(os.getenv("TEMA_LEN", "120"))
CMO_WIN     = int(os.getenv("CMO_WIN", "14"))
CMO_TRIGGER = float(os.getenv("CMO_TRIGGER", "10"))
ATR_WIN     = int(os.getenv("ATR_WIN", "14"))
ATR_MULT    = float(os.getenv("ATR_MULT", "3.5"))
VOL_WIN     = int(os.getenv("VOL_WIN", "30"))
TARGET_VOL  = float(os.getenv("TARGET_VOL", "0.40"))   # vol-targeting niveau
F_MIN       = float(os.getenv("F_MIN", "0.10"))
F_MAX       = float(os.getenv("F_MAX", "1.0"))         # 1.0 = GEEN hefboom
HIST_BARS   = int(os.getenv("HIST_BARS", "400"))       # genoeg voor TEMA120-warmup

# ---- Uitvoering ----
# paper = lokale simulatie met echte prijzen (geen orders naar OKX)
# demo  = OKX demo trading (x-simulated-trading, nep-geld, echte API)
# live  = echt geld (vereist ALLOW_LIVE=1)
MODE         = os.getenv("MODE", "paper").lower()
START_EQUITY = float(os.getenv("START_EQUITY", "1000"))
PAPER_FEE    = float(os.getenv("PAPER_FEE", "0.001"))      # 0,1% per kant (paper)
PAPER_SLIP   = float(os.getenv("PAPER_SLIP", "0.0005"))    # 0,05% slippage (paper)
ALLOW_LIVE   = os.getenv("ALLOW_LIVE", "0") == "1"          # veiligheidsslot
MAX_LIVE_EQUITY = float(os.getenv("MAX_LIVE_EQUITY", "100"))# harde cap op live-inzet

# ---- Paden ----
DATA_DIR    = os.getenv("DATA_DIR", "./data")
STATE_JSON  = os.path.join(DATA_DIR, "state.json")
TRADES_CSV  = os.path.join(DATA_DIR, "trades.csv")
STOP_FLAG   = os.path.join(DATA_DIR, "stop.flag")

os.makedirs(DATA_DIR, exist_ok=True)
