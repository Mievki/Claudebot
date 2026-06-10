# tema-bot — dagelijkse TEMA/CMO vol-target bot (BTC-USDT, OKX spot)

Draait de **gevalideerde** strategie: dagelijkse BTC-USDT spot, long-only, geen hefboom.

- **Entry** (alleen vanuit cash): `close > TEMA(120)` **en** `CMO(14) > 10`
- **Exit**: ATR-trailing stop — `hoogste close sinds entry − 3,5 × ATR(14)`, ratchet alleen omhoog
- **Sizing**: vol-targeting — `fractie = clip(0,40 / vol_30d_geannualiseerd, 0,10, 1,0)`, eenmalig bij entry
- Eén beslissing per dag, om 00:02 UTC, op de laatst **gesloten** daily candle

De parameters zijn GELOCKT en gevalideerd (zie `PROJECT_KNOWLEDGE`). De indicator-
formules zijn **bewezen bit-voor-bit identiek** aan de backtest: `tests/test_parity.py`
vergelijkt ze letterlijk met de notebook-formules op de echte backtest-data, en
`tests/test_backtest_replay.py` speelt de volledige backtest door `strategy.decide()`
af — identieke trades en eindwaarde.

## Architectuur

```
config.py        alle instellingen via .env (code en geheimen gescheiden)
indicators.py    TEMA/CMO/ATR/vol — EXACT gelijk aan de backtest (zie tests)
strategy.py      pure decide() -> ENTER/EXIT/HOLD, geen IO, unit-testbaar
okx_client.py    OKX REST (spot): candles (gepagineerd), ticker, balance, orders, fills
broker.py        PaperBroker (lokale simulatie) en OkxBroker (demo/live, echte fills)
storage.py       state.json + trades.csv + proces-lock
bot.py           orchestratie: `once` (systemd-timer) / `run` (loop) / `stop`
telegram_bot.py  meldingen + commando-listener (whitelist op jouw user-id)
status_cli.py    snel state + trades bekijken
tests/           pariteit, strategie, broker, telegram (30 tests)
deploy/          systemd-units + install.sh voor de server
```

Drie modi via `.env` — zelfde logica, alleen de broker verschilt:

| MODE | wat | risico |
|---|---|---|
| `paper` | lokale simulatie met echte OKX-prijzen, geen orders | nul |
| `demo` | OKX demo-API (`x-simulated-trading`), nep-geld | nul |
| `live` | echt geld — geblokkeerd tenzij `ALLOW_LIVE=1`, gecapt op `MAX_LIVE_EQUITY` | echt |

## Snelstart (paper, nul risico)

```bash
pip install -r requirements.txt
cp .env.example .env            # MODE=paper staat al goed
python bot.py once              # één beslissing op de laatste gesloten daily candle
python status_cli.py            # state + laatste trades
pytest tests/ -v                # bewijs dat alles klopt (30 tests)
```

## Telegram

1. Maak een bot via **@BotFather** (`/newbot`) → zet de token in `.env` als `TELEGRAM_BOT_TOKEN`.
2. Vraag je **numerieke** user-id op bij **@userinfobot** → `TELEGRAM_CHAT_ID`.
3. Stuur eenmalig `/start` naar je bot (anders mag hij jou niet berichten).
4. Test: `python telegram_bot.py test` → je krijgt een testbericht.
5. Listener starten: `python telegram_bot.py` (op de server: systemd, zie hieronder).

De bot meldt **elk trade-event** (actie, prijs, units, inzet, stop, reden, equity) en fouten.
Commando's — uitsluitend vanaf jouw user-id, al het andere wordt genegeerd en gelogd:

| commando | effect |
|---|---|
| `/status` | modus, positie, stop, equity, trading aan/uit |
| `/trades` | laatste 10 trades |
| `/equity` | actuele equity (mark-to-market) |
| `/off` | geen nieuwe entries; open positie behoudt trailing stop |
| `/on` | trading weer aan |
| `/stop` | **paniek**: verkoop open positie NU + trading uit |

## Naar OKX demo (stap 2)

1. OKX → Demo Trading → maak demo-API-keys (alleen **trade**-rechten, geen withdraw, IP-beperkt).
2. Vul `OKX_API_KEY/SECRET/PASSPHRASE` in `.env`, zet `MODE=demo`.
3. `python bot.py once` — orders gaan nu naar OKX demo (nep-geld). Weken laten draaien.

## Live (pas als demo wekenlang klopt)

`MODE=live`, `ALLOW_LIVE=1`, `MAX_LIVE_EQUITY` laag (50–100). Begin minimaal.
Ken de risico's: bootstrap 5%-worst-case drawdown is **−78%** (zie `PROJECT_KNOWLEDGE` §5).

## Deploy op een VPS (Hetzner CX23, Ubuntu)

```bash
# op de server, als root:
wget https://raw.githubusercontent.com/Mievki/Claudebot/master/tema-bot/deploy/install.sh
sudo bash install.sh
nano /opt/tema-bot/tema-bot/.env          # MODE, OKX-keys, TELEGRAM_*
systemctl start tema-telegram.service     # commando-listener (24/7)
systemctl start tema-bot.service          # eenmalige testrun
journalctl -u tema-bot -n 50              # logs
```

Daarna draait `tema-bot.timer` elke dag om **00:02 UTC** (`Persistent=true`: een gemiste
run wordt ingehaald na een reboot). De trade-job is een oneshot — crasht er iets, dan
meldt hij dat via Telegram en draait morgen gewoon weer. Idempotent op `last_bar_ts`:
nooit twee keer handelen op dezelfde candle.

Updaten: `sudo bash /opt/tema-bot/tema-bot/deploy/install.sh` (pull + pip + units).

## Veiligheid

- `.env` staat in `.gitignore` — geheimen komen nooit in git. `chmod 600` op de server.
- API-keys: alleen trade-rechten, **nooit** withdraw; beperk op het server-IP.
- `live` is dubbel vergrendeld: `ALLOW_LIVE=1` vereist én equity-cap `MAX_LIVE_EQUITY`.
- systemd-hardening: aparte systeemgebruiker, alleen `data/` schrijfbaar.
- Telegram-listener accepteert uitsluitend jouw numerieke user-id.
