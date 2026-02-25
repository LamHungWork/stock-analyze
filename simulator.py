"""
simulator.py — P&L simulation engine for backtesting trading strategies.

For each day d (from index 50 onward to allow sufficient lookback):
  1. signal = strategy.generate_signal(df[:d+1])  — no lookahead
  2. entry_price = df[d+1].open                    — enter at next day's open
  3. t_plus = signal['t_plus'] (3-5)
  4. Check df[d+1 → d+t_plus]:
       Tang : high >= target → TP; low <= stoploss → SL
       Giam : low <= target → TP; high >= stoploss → SL
  5. If neither hit by end of T+: exit at close of d+t_plus
  6. pnl = shares × (exit_price - entry_price)   if Tang
         = shares × (entry_price - exit_price)   if Giam
         = shares × (exit_price - entry_price)   if Di_Ngang (long bias)
"""
import logging
from typing import List

import pandas as pd

from config import SIMULATION_SHARES, T_PLUS_MIN, T_PLUS_MAX
from strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

# Minimum bars of history needed before generating the first signal
MIN_LOOKBACK = 60


def run_simulation(
    symbol: str,
    df: pd.DataFrame,
    strategy: BaseStrategy,
    shares: int = SIMULATION_SHARES,
) -> List[dict]:
    """
    Run a full historical simulation for a single strategy.

    Parameters
    ----------
    symbol   : ticker symbol (for labeling)
    df       : full OHLCV DataFrame, sorted ascending by date
    strategy : BaseStrategy instance
    shares   : number of shares per trade

    Returns
    -------
    List of trade dicts, one per signal day with a valid next-day entry.
    """
    df = df.reset_index(drop=True)
    n = len(df)
    trades = []

    for d in range(MIN_LOOKBACK, n - 1):  # need at least d+1 for entry
        # ── Generate signal using only data up to day d (inclusive) ──────────
        history = df.iloc[: d + 1].copy()
        try:
            signal = strategy.generate_signal(history)
        except Exception as exc:
            logger.debug("Signal error on day %d for %s/%s: %s", d, symbol, strategy.name, exc)
            continue

        trend = signal.get("trend", "Di_Ngang")
        target = signal.get("target")
        stoploss = signal.get("stoploss")
        t_plus = int(signal.get("t_plus", T_PLUS_MIN))
        t_plus = max(T_PLUS_MIN, min(T_PLUS_MAX, t_plus))

        if target is None or stoploss is None:
            continue

        # ── Entry: next day's open ────────────────────────────────────────────
        entry_idx = d + 1
        if entry_idx >= n:
            continue

        entry_row = df.iloc[entry_idx]
        entry_price = float(entry_row["open"])
        entry_date = entry_row["date"]

        if entry_price <= 0:
            continue

        # ── Exit: check T+1 through T+t_plus bars ────────────────────────────
        exit_price = None
        exit_reason = "T+ expire"
        exit_date = None

        for offset in range(1, t_plus + 1):
            check_idx = entry_idx + offset
            if check_idx >= n:
                break

            bar = df.iloc[check_idx]
            high = float(bar["high"])
            low = float(bar["low"])

            if trend == "Tang":
                if high >= target:
                    exit_price = target
                    exit_reason = "TP"
                    exit_date = bar["date"]
                    break
                if low <= stoploss:
                    exit_price = stoploss
                    exit_reason = "SL"
                    exit_date = bar["date"]
                    break
            elif trend == "Giam":
                if low <= target:
                    exit_price = target
                    exit_reason = "TP"
                    exit_date = bar["date"]
                    break
                if high >= stoploss:
                    exit_price = stoploss
                    exit_reason = "SL"
                    exit_date = bar["date"]
                    break
            else:  # Di_Ngang — long bias
                if high >= target:
                    exit_price = target
                    exit_reason = "TP"
                    exit_date = bar["date"]
                    break
                if low <= stoploss:
                    exit_price = stoploss
                    exit_reason = "SL"
                    exit_date = bar["date"]
                    break

        # ── If no TP/SL hit, exit at close of the last checked bar ───────────
        if exit_price is None:
            last_check_idx = min(entry_idx + t_plus, n - 1)
            last_bar = df.iloc[last_check_idx]
            exit_price = float(last_bar["close"])
            exit_date = last_bar["date"]

        # ── P&L calculation ───────────────────────────────────────────────────
        if trend == "Giam":
            pnl = shares * (entry_price - exit_price)
            pnl_pct = (entry_price - exit_price) / entry_price * 100
        else:
            pnl = shares * (exit_price - entry_price)
            pnl_pct = (exit_price - entry_price) / entry_price * 100

        result = "Win" if pnl > 0 else ("Loss" if pnl < 0 else "Breakeven")

        trades.append({
            "symbol": symbol,
            "strategy": strategy.name,
            "signal_date": df.iloc[d]["date"],
            "entry_date": entry_date,
            "exit_date": exit_date,
            "trend": trend,
            "entry_price": round(entry_price, 2),
            "target": round(float(target), 2),
            "stoploss": round(float(stoploss), 2),
            "t_plus": t_plus,
            "exit_price": round(exit_price, 2),
            "exit_reason": exit_reason,
            "shares": shares,
            "pnl": round(pnl, 0),
            "pnl_pct": round(pnl_pct, 2),
            "result": result,
        })

    logger.info(
        "%s/%s: %d trades simulated (Win: %d, Loss: %d)",
        symbol, strategy.name, len(trades),
        sum(1 for t in trades if t["result"] == "Win"),
        sum(1 for t in trades if t["result"] == "Loss"),
    )
    return trades
