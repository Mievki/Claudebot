"""Test-setup: maak de tema-bot modules importeerbaar en wijs naar de backtest-CSV."""
import os
import sys

import pandas as pd
import pytest

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(BOT_DIR)
BTC_CSV = os.path.join(REPO_DIR, "tradingbot2026", "btc_1d.csv")

sys.path.insert(0, BOT_DIR)


@pytest.fixture(scope="session")
def btc_df():
    """Zelfde laad-volgorde als de backtest-notebook (sort op datum)."""
    df = pd.read_csv(BTC_CSV)
    df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    df = df.sort_values("date").reset_index(drop=True)
    return df
