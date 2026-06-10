# tema-bot — dagelijkse TEMA/CMO vol-target bot (BTC-USDT, OKX spot)

Een bot die **één keer per dag** een beslissing neemt over BTC: kopen, verkopen of niets doen.
Long-only, spot, geen hefboom. De regels zijn gevalideerd in een backtest en GELOCKT
(zie [`PROJECT_KNOWLEDGE`](PROJECT_KNOWLEDGE)).

## 1. Wat doet de strategie?

Elke dag, vlak na middernacht UTC (00:02), kijkt de bot naar de zojuist **gesloten** dagcandle:

- **Geen positie?** Koop als de koers boven de lange trendlijn ligt (`close > TEMA(120)`)
  **én** er momentum is (`CMO(14) > 10`).
  - Hoeveel? Vol-targeting: `inzet = 40% / jaarvolatiliteit`, begrensd tussen 10% en 100%
    van je equity. Rustige markt → grote inzet; wilde markt → kleine inzet.
    De inzet wordt **eenmalig** bij entry bepaald, daarna niet meer aangepast.
- **Wel een positie?** Verkoop als de koers de trailing stop raakt:
  `stop = hoogste close sinds entry − 3,5 × ATR(14)`. De stop schuift alleen **omhoog**.
- Anders: niets doen tot morgen.

## 2. Hoe werkt de code?

Eén dagelijkse run (`python bot.py once`) doorloopt deze pijplijn:

```
bot.py once
 ├─ 1. okx_client.candles()   haal 1200 gesloten dagcandles op (gepagineerd)
 ├─ 2. idempotentie-check     zelfde candle al verwerkt? -> stop (nooit 2x handelen)
 ├─ 3. strategy.decide()      pure logica: ENTER / EXIT / HOLD + reden
 │       └─ indicators.py     TEMA/CMO/ATR/vol — bit-voor-bit gelijk aan de backtest
 ├─ 4. kill-switch check      staat trading uit (/off)? -> entry onderdrukken
 ├─ 5. broker.buy/sell        paper: lokale simulatie | demo/live: echte OKX-order
 ├─ 6. storage                state.json bijwerken + trade in trades.csv loggen
 └─ 7. telegram_bot.notify()  melding bij elke trade, onderdrukte entry of fout
```

| bestand | rol |
|---|---|
| `config.py` | alle instellingen, gelezen uit `.env` |
| `indicators.py` | de vier formules — wijzig deze NOOIT (pariteit met backtest) |
| `strategy.py` | `decide()`: pure beslislogica, geen netwerk/IO |
| `okx_client.py` | OKX REST: candles, ticker, saldo, orders, fills |
| `broker.py` | `PaperBroker` (simulatie) / `OkxBroker` (demo & live) |
| `storage.py` | `data/state.json` (positie+equity), `data/trades.csv`, proces-lock |
| `bot.py` | de dagelijkse run (stappen hierboven) |
| `telegram_bot.py` | meldingen sturen + commando's ontvangen (alleen van jou) |
| `status_cli.py` | `python status_cli.py` = state + laatste trades in je terminal |
| `tests/` | 30 tests; `test_backtest_replay.py` bewijst: bot == backtest |
| `deploy/` | systemd-units + installatiescript voor de server |

**Drie modi** — zelfde logica, alleen de broker verschilt (`MODE` in `.env`):

| MODE | wat gebeurt er | risico |
|---|---|---|
| `paper` | simulatie met echte OKX-prijzen, er gaat NIETS naar de exchange | nul |
| `demo` | echte API-calls naar OKX **demo** (nep-geld) | nul |
| `live` | echt geld; werkt alleen met `ALLOW_LIVE=1` én onder `MAX_LIVE_EQUITY` | echt |

**State**: `data/state.json` onthoudt positie, stop, equity en de laatst verwerkte candle.
Crasht de server? Geen probleem — morgen draait de timer opnieuw en gaat de bot verder
waar hij was. `data/trades.csv` is het logboek (opent direct in Excel).

## 3. Stap voor stap draaien

### Stap 0 — eenmalige setup (op je eigen pc)

```powershell
# Windows (PowerShell), vanuit de map tema-bot:
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env
```
```bash
# Linux/Mac:
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
```

`.env` staat in `.gitignore` — je geheimen komen nooit op GitHub.

### Stap 1 — bewijs dat alles klopt (tests)

```powershell
.venv\Scripts\python -m pytest tests/ -v        # Windows
# .venv/bin/python -m pytest tests/ -v          # Linux/Mac
```
Verwacht: **30 passed**. Dit bewijst o.a. dat de indicatoren exact de backtest reproduceren.

### Stap 2 — paper mode (nul risico, begin hier)

`MODE=paper` staat al goed in `.env`. Draai:

```powershell
.venv\Scripts\python bot.py once     # één beslissing op de laatste gesloten candle
.venv\Scripts\python status_cli.py   # bekijk state + trades
```

Draai je `bot.py once` direct nog een keer, dan zie je `[SKIP] candle ... al verwerkt` —
de bot handelt nooit twee keer op dezelfde dag.

### Stap 3 — Telegram aansluiten (~5 minuten)

1. Open Telegram → **@BotFather** → `/newbot` → kies een naam.
   Kopieer de token naar `.env`: `TELEGRAM_BOT_TOKEN=123456:ABC...`
2. Vraag **@userinfobot** naar je **numerieke** user-id → `TELEGRAM_CHAT_ID=123456789`
3. Stuur eenmalig `/start` naar je nieuwe bot (anders mag hij jou niet berichten).
4. Test: `python telegram_bot.py test` → je krijgt een testbericht op je telefoon.
5. Start de listener: `python telegram_bot.py` en stuur `/status` vanaf je telefoon.

| commando | effect |
|---|---|
| `/status` | modus, positie, stop, equity, trading aan/uit |
| `/trades` | laatste 10 trades |
| `/equity` | actuele equity (live prijs) |
| `/off` | geen **nieuwe** entries; open positie houdt haar trailing stop |
| `/on` | trading weer aan |
| `/stop` | **paniekknop**: verkoop open positie NU + trading uit |

Alleen jouw user-id wordt geaccepteerd; al het andere wordt genegeerd en gelogd.
De bot meldt zelf elke trade (actie, prijs, units, inzet, stop, reden, equity) en elke fout.

### Stap 4 — OKX demo (echte API, nep-geld)

1. OKX → profiel → **Demo Trading** → maak demo-API-keys.
   Geef ze alleen **trade**-rechten (geen withdraw) en beperk op IP.
2. In `.env`: vul `OKX_API_KEY/SECRET/PASSPHRASE` in en zet `MODE=demo`.
3. `python bot.py once` — orders gaan nu echt naar OKX demo.
4. **Laat dit weken draaien** en vergelijk de Telegram-meldingen met wat je verwacht.
   De orderafhandeling (fills, fees, afronding) is unit-getest maar moet zich hier
   in de praktijk bewijzen.

### Stap 5 — op de server (Hetzner CX23, Ubuntu)

```bash
# als root op de verse server:
wget https://raw.githubusercontent.com/Mievki/Claudebot/master/tema-bot/deploy/install.sh
sudo bash install.sh
nano /opt/tema-bot/tema-bot/.env           # MODE, OKX-keys, TELEGRAM_*
systemctl start tema-telegram.service      # commando-listener (24/7)
systemctl start tema-bot.service           # eenmalige testrun, meteen
```

Daarna draait alles vanzelf:
- `tema-bot.timer` start de trade-job **elke dag om 00:02 UTC** (gemiste run wordt
  na een reboot ingehaald).
- `tema-telegram.service` luistert 24/7 naar je commando's (herstart zichzelf).

Handige checks:
```bash
systemctl list-timers tema-bot.timer       # wanneer is de volgende run?
journalctl -u tema-bot -n 50               # logs van de trade-job
journalctl -u tema-telegram -f             # live logs van de listener
```
Updaten na een nieuwe git-push: `sudo bash /opt/tema-bot/tema-bot/deploy/install.sh`.

### Stap 6 — live (pas als demo wekenlang klopt)

In `.env`: `MODE=live`, `ALLOW_LIVE=1`, en houd `MAX_LIVE_EQUITY` laag (50–100 USDT).
Begin minimaal. Ken de risico's: de bootstrap-analyse geeft een 5%-worst-case drawdown
van **−78%** (`PROJECT_KNOWLEDGE` §5) — zet alleen geld in waarvan een verlies een
tegenvaller is, geen ramp.

## 4. Veiligheid (samengevat)

- `.env` in `.gitignore`; op de server `chmod 600`. Geheimen nooit in git.
- API-keys: alleen trade-rechten, **nooit** withdraw, IP-beperkt.
- Live is dubbel vergrendeld: `ALLOW_LIVE=1` vereist + harde equity-cap.
- systemd draait als aparte gebruiker zonder login-shell; alleen `data/` is schrijfbaar.
- Telegram: hard gewhitelist op jouw numerieke user-id.
- Idempotent per candle; fouten gaan naar Telegram én de systemd-journal.

## 5. Iets aanpassen?

- **Strategie-parameters zijn gelockt.** Een wijziging = een andere (niet-gevalideerde)
  strategie; doe dat alleen bewust en draai daarna `pytest tests/`.
- Andere coin (bv. ETH): tweede instantie met eigen `.env` (`INST_ID=ETH-USDT`) en
  eigen `DATA_DIR`. Parameters zijn op BTC én ETH gevalideerd.
- Dependency-upgrade: eerst `pytest tests/` — de pariteitstests bewaken de formules.
