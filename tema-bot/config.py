"""Centrale configuratie. Alles via .env zodat code en geheimen gescheiden blijven."""
import os
from dotenv import load_dotenv

# .env naast deze module laden (niet cwd), zodat het ook onder systemd/tests werkt.
_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, ".env"))

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
HIST_BARS   = int(os.getenv("HIST_BARS", "1200"))      # TEMA120-warmup: ewm is startpunt-
# afhankelijk; tests/test_parity.py meet: 400 bars -> $118 TEMA-fout, 1200 -> <$0.001.

# ---- Uitvoering ----
# paper = lokale simulatie met echte prijzen (geen orders naar OKX)
# demo  = OKX demo trading (x-simulated-trading, nep-geld, echte API)
# live  = echt geld (vereist ALLOW_LIVE=1)
MODE         = os.getenv("MODE", "paper").lower()
START_EQUITY = float(os.getenv("START_EQUITY", "1000"))
PAPER_FEE    = float(os.getenv("PAPER_FEE", "0.002"))      # 0,2% per kant — zoals backtest
PAPER_SLIP   = float(os.getenv("PAPER_SLIP", "0.001"))     # 0,1% slippage — zoals backtest
# NB: paper rekent slippage op BEIDE kanten; de backtest alleen op stop-exits.
# Paper is dus iets conservatiever dan de backtest — bewust zo gelaten.
ALLOW_LIVE   = os.getenv("ALLOW_LIVE", "0") == "1"          # veiligheidsslot
MAX_LIVE_EQUITY = float(os.getenv("MAX_LIVE_EQUITY", "100"))# harde cap op live-inzet

# ---- Telegram ----
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")    # van @BotFather
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")      # JOUW numerieke user-id (whitelist)

# ---- Paden ----
# Default naast deze module (niet cwd), zodat bot/tests/systemd dezelfde data zien.
DATA_DIR    = os.getenv("DATA_DIR", os.path.join(_HERE, "data"))
STATE_JSON  = os.path.join(DATA_DIR, "state.json")
TRADES_CSV  = os.path.join(DATA_DIR, "trades.csv")
STOP_FLAG   = os.path.join(DATA_DIR, "stop.flag")

os.makedirs(DATA_DIR, exist_ok=True)
