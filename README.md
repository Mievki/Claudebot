# Claudebot — TEMA/CMO daily crypto trading

Twee delen:

| map | wat |
|---|---|
| [`tema-bot/`](tema-bot/) | **De productie-bot**: dagelijkse BTC-USDT spot op OKX, long-only, geen hefboom. Paper / demo / live via `.env`, Telegram-meldingen + commando's, systemd-deploy. Zie [`tema-bot/README.md`](tema-bot/README.md). |
| [`tradingbot2026/`](tradingbot2026/) | **Het onderzoek**: backtest-notebooks, validatie (robuustheid, train/test, bootstrap, cross-asset) en de historische data. `TEMA_CMO_BTC_voltarget.ipynb` is de canonieke backtest. |

De strategie-parameters zijn gevalideerd en GELOCKT — zie [`tema-bot/PROJECT_KNOWLEDGE`](tema-bot/PROJECT_KNOWLEDGE).
De indicator-formules in de bot zijn **bewezen bit-voor-bit identiek** aan de backtest
(`tema-bot/tests/`): de volledige backtest, afgespeeld door de live beslislogica, geeft
exact dezelfde 80 trade-events en eindwaarde.

Geheimen (`.env`) staan in `.gitignore` en komen nooit in deze repo.
