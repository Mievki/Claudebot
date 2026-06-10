# TEMA daily vol-target bot (concept)

Draait de **gevalideerde** strategie: dagelijkse BTC-USDT spot, long-only, geen hefboom.
Regels: koop bij `close > TEMA(120)` en `CMO(14) > 10`; positiegrootte via vol-targeting
(40% / gerealiseerde vol, gecapt op 100%); ATR-trailing stop op 3,5x ATR.

## Bestanden
- `config.py`     — alle instellingen (via `.env`)
- `indicators.py` — TEMA/CMO/ATR/vol, **exact gelijk aan de backtest**
- `strategy.py`   — pure beslislogica (ENTER/EXIT/HOLD)
- `okx_client.py` — OKX REST (spot): candles, ticker, balance, order
- `broker.py`     — PaperBroker (simulatie) en OkxBroker (demo/live)
- `storage.py`    — state.json + trades.csv
- `bot.py`        — orchestratie (`once` / `run` / `stop`)
- `status_cli.py` — snel state + trades bekijken

## Snelstart (paper, nul risico)
```bash
pip install -r requirements.txt
cp .env.example .env          # MODE=paper staat al goed
python bot.py once            # één beslissing op de laatste gesloten daily candle
python status_cli.py          # bekijk state + trades
```

## Naar OKX demo (stap 2)
1. Maak in OKX demo-API-keys (alleen trade-rechten, geen withdraw).
2. Vul ze in `.env`, zet `MODE=demo`.
3. `python bot.py once` — nu gaan orders naar OKX demo (nep-geld).

## Live (pas als demo wekenlang klopt)
Zet `MODE=live`, `ALLOW_LIVE=1`, en houd `MAX_LIVE_EQUITY` laag. Start met een minibedrag.

## Altijd online
Aanrader voor een dag-strategie: kleine VPS + systemd-timer (zie `tema-bot.timer`),
draait `bot.py once` elke dag om 00:02 UTC. Crasht er iets, dan draait 'ie morgen gewoon weer.
Alternatief: `docker compose up -d` (loop-modus, `restart: unless-stopped`).
