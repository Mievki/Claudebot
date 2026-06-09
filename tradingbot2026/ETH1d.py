import ccxt
import pandas as pd
import os
import time

# --- LOCATIE BEPALEN ---
# Dit zorgt ervoor dat out_path naar de map van dit .py bestand wijst
script_dir = os.path.dirname(os.path.abspath(__file__))
out_path = os.path.join(script_dir, "eth_1d.csv")

# --- PARAMETERS ---
symbol = 'ETH/USDT'
timeframe = '1d'
start_date = "2018-01-01T00:00:00Z"

# Maak verbinding met Binance
exchange = ccxt.binance()

print(f"Data ophalen voor {symbol}...")
print(f"Bestand wordt opgeslagen in: {out_path}")

# Omrekenen van startdatum naar miliseconden
since = exchange.parse8601(start_date)
all_ohlcv = []

try:
    while since < exchange.milliseconds():
        # Haal batch op (max 1000 per keer)
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since, limit=1000)

        if not ohlcv:
            break

        # Update 'since' voor de volgende batch
        since = ohlcv[-1][0] + 86400000
        all_ohlcv.extend(ohlcv)

        print(f"Batch opgehaald tot: {exchange.iso8601(ohlcv[-1][0])}")

        # Rate limit pauze
        time.sleep(exchange.rateLimit / 1000)

    # 1. DataFrame bouwen
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

    # 2. Bewerkingen (UTC & Turnover)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df['turnover'] = df['close'] * df['volume']

    # 3. Opslaan in de juiste map
    df.to_csv(out_path, index=False)

    print("-" * 30)
    print(f"Klaar! {len(df)} rijen opgeslagen in dezelfde map als dit script.")

except Exception as e:
    print(f"Fout opgetreden: {e}")