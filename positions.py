"""
positions.py — Open/closed position tracker for daily_run.py.

OPEN_POSITIONS.csv schema:
  symbol, strategy, signal_date, trend,
  recommended_entry, target, stoploss, t_plus,
  entry_date, entry_price, expected_exit_date,
  exit_date, exit_price, exit_reason,
  pnl_pct, status

Status flow:
  signal_date D   → status="pending"  (chưa vào lệnh)
  entry_date  D+1 → status="open"     (điền entry_price = D+1 open)
  D+1 → D+t_plus  → check TP/SL mỗi ngày
  expired         → status="closed", exit_reason="T+ expire"
"""
import logging
import os
from datetime import date, timedelta
from typing import List

import pandas as pd

from config import OPEN_POSITIONS_CSV, REPORTS_DIR

logger = logging.getLogger(__name__)

# ── Column definitions ──────────────────────────────────────────────────────────

COLUMNS = [
    "symbol", "strategy", "signal_date", "trend",
    "recommended_entry", "target", "stoploss", "t_plus",
    "entry_date", "entry_price", "expected_exit_date",
    "exit_date", "exit_price", "exit_reason",
    "pnl_pct", "status",
]

_DATE_COLS = ["signal_date", "entry_date", "expected_exit_date", "exit_date"]
_FLOAT_COLS = ["recommended_entry", "target", "stoploss", "entry_price", "exit_price", "pnl_pct"]

# ── Module-level state ──────────────────────────────────────────────────────────

_df: pd.DataFrame | None = None


def _get_df() -> pd.DataFrame:
    """Return the in-memory positions DataFrame, loading from disk if needed."""
    global _df
    if _df is None:
        load_positions()
    return _df


# ── Public API ──────────────────────────────────────────────────────────────────

def load_positions() -> pd.DataFrame:
    """
    Load OPEN_POSITIONS.csv into memory.
    Returns an empty DataFrame if the file does not exist.
    """
    global _df
    os.makedirs(REPORTS_DIR, exist_ok=True)

    if not os.path.isfile(OPEN_POSITIONS_CSV):
        _df = pd.DataFrame(columns=COLUMNS)
        return _df

    try:
        df = pd.read_csv(OPEN_POSITIONS_CSV, dtype=str)

        # Parse date columns
        for col in _DATE_COLS:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

        # Parse numeric columns
        for col in _FLOAT_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "t_plus" in df.columns:
            df["t_plus"] = pd.to_numeric(df["t_plus"], errors="coerce").fillna(5).astype(int)

        # Ensure all expected columns exist
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = None

        _df = df[COLUMNS].copy()
        logger.info("Positions loaded: %d rows from %s", len(_df), OPEN_POSITIONS_CSV)
    except Exception as exc:
        logger.warning("Failed to load positions: %s", exc)
        _df = pd.DataFrame(columns=COLUMNS)

    return _df


def save_positions() -> None:
    """Flush the in-memory positions DataFrame to OPEN_POSITIONS.csv."""
    df = _get_df()
    os.makedirs(REPORTS_DIR, exist_ok=True)
    df.to_csv(OPEN_POSITIONS_CSV, index=False)
    logger.info("Positions saved: %d rows → %s", len(df), OPEN_POSITIONS_CSV)


def update_positions(today_date: date, symbol: str, today_bar: dict) -> List[dict]:
    """
    Update all pending/open positions for `symbol` using today's OHLCV bar.

    Steps for each matching position:
      1. pending → open : if entry_date == today, fill entry_price with today's open
      2. open → check exit : TP / SL / T+ expire using today's high/low/close

    Returns a list of position dicts that were closed today.
    """
    df = _get_df()
    closed: List[dict] = []

    mask = (df["symbol"] == symbol) & (df["status"].isin(["pending", "open"]))
    indices = df[mask].index.tolist()

    for idx in indices:
        # Step 1: pending → open
        if df.at[idx, "status"] == "pending":
            entry_date = _to_date(df.at[idx, "entry_date"])
            if entry_date == today_date:
                df.at[idx, "entry_price"] = today_bar["open"]
                df.at[idx, "status"] = "open"
                logger.info(
                    "%s/%s: pending → open at %.2f",
                    symbol, df.at[idx, "strategy"], today_bar["open"],
                )

        # Step 2: open → check exit
        if df.at[idx, "status"] != "open":
            continue

        trend = df.at[idx, "trend"]
        target = _safe_float(df.at[idx, "target"])
        stoploss = _safe_float(df.at[idx, "stoploss"])
        entry_price = _safe_float(df.at[idx, "entry_price"])
        expected_exit_date = _to_date(df.at[idx, "expected_exit_date"])

        exit_price: float | None = None
        exit_reason: str | None = None

        if trend == "Tang":
            if target is not None and today_bar["high"] >= target:
                exit_price, exit_reason = target, "TP"
            elif stoploss is not None and today_bar["low"] <= stoploss:
                exit_price, exit_reason = stoploss, "SL"
        elif trend == "Giam":
            if target is not None and today_bar["low"] <= target:
                exit_price, exit_reason = target, "TP"
            elif stoploss is not None and today_bar["high"] >= stoploss:
                exit_price, exit_reason = stoploss, "SL"

        # T+ expire (only if no TP/SL)
        if exit_price is None and expected_exit_date is not None:
            if today_date >= expected_exit_date:
                exit_price = today_bar["close"]
                exit_reason = "T+ expire"

        if exit_price is not None:
            df.at[idx, "exit_date"] = today_date
            df.at[idx, "exit_price"] = exit_price
            df.at[idx, "exit_reason"] = exit_reason

            if entry_price and entry_price > 0:
                if trend == "Tang":
                    pnl_pct = (exit_price - entry_price) / entry_price * 100
                else:  # Giam
                    pnl_pct = (entry_price - exit_price) / entry_price * 100
                df.at[idx, "pnl_pct"] = round(pnl_pct, 4)

            df.at[idx, "status"] = "closed"
            logger.info(
                "%s/%s: closed via %s at %.2f",
                symbol, df.at[idx, "strategy"], exit_reason, exit_price,
            )
            closed.append(df.loc[idx].to_dict())

    return closed


def add_signal(
    symbol: str,
    strategy_name: str,
    signal_date: date,
    signal: dict,
    today_close: float,
) -> None:
    """
    Add a new pending position from a strategy signal.

    Skips Di_Ngang signals and duplicate (symbol, strategy, signal_date) combos.
    """
    trend = signal.get("trend")
    if trend == "Di_Ngang":
        return

    df = _get_df()

    # Guard: no duplicate
    dup_mask = (
        (df["symbol"] == symbol) &
        (df["strategy"] == strategy_name) &
        (df["signal_date"].astype(str) == str(signal_date))
    )
    if dup_mask.any():
        logger.debug(
            "Duplicate signal skipped: %s/%s/%s", symbol, strategy_name, signal_date
        )
        return

    entry_date = next_trading_date(signal_date)
    t_plus = int(signal.get("t_plus", 5))
    expected_exit_date = _add_trading_days(entry_date, t_plus)

    if trend == "Tang":
        recommended_entry = round(today_close * 1.001, 2)
    else:  # Giam
        recommended_entry = round(today_close * 0.999, 2)

    new_row = {
        "symbol": symbol,
        "strategy": strategy_name,
        "signal_date": signal_date,
        "trend": trend,
        "recommended_entry": recommended_entry,
        "target": signal["target"],
        "stoploss": signal["stoploss"],
        "t_plus": t_plus,
        "entry_date": entry_date,
        "entry_price": None,
        "expected_exit_date": expected_exit_date,
        "exit_date": None,
        "exit_price": None,
        "exit_reason": None,
        "pnl_pct": None,
        "status": "pending",
    }

    global _df
    _df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    logger.info(
        "Signal added: %s/%s/%s trend=%s", symbol, strategy_name, signal_date, trend
    )


def get_open_positions(symbol: str) -> List[dict]:
    """Return all pending/open positions for `symbol`."""
    df = _get_df()
    mask = (df["symbol"] == symbol) & (df["status"].isin(["pending", "open"]))
    return df[mask].to_dict("records")


# ── Trading date helpers ────────────────────────────────────────────────────────

def next_trading_date(d: date) -> date:
    """Return the next trading day after `d` (skips weekends, no holiday calendar)."""
    nd = d + timedelta(days=1)
    while nd.weekday() >= 5:  # 5=Saturday, 6=Sunday
        nd += timedelta(days=1)
    return nd


def _add_trading_days(d: date, n: int) -> date:
    """Add `n` trading days to date `d`."""
    current = d
    for _ in range(n):
        current = next_trading_date(current)
    return current


# ── Private helpers ─────────────────────────────────────────────────────────────

def _to_date(val) -> date | None:
    """Safely convert a value to datetime.date, returning None on failure."""
    if val is None:
        return None
    try:
        if isinstance(val, date):
            return val
        return pd.to_datetime(val).date()
    except Exception:
        return None


def _safe_float(val) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if pd.isna(f) else f
    except Exception:
        return None
