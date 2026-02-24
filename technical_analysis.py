"""
technical_analysis.py — Compute SMA20, Volume SMA, Swing High/Low, Fibonacci levels.
"""
import logging
from datetime import date
from dateutil.relativedelta import relativedelta

import numpy as np
import pandas as pd

from config import (
    FIB_LEVELS,
    FIB_LOOKBACK_MONTHS,
    FIB_PROXIMITY_PCT,
    SMA_PERIOD,
    SWING_DETECTION_WINDOW,
    VOLUME_SPIKE_RATIO,
)

logger = logging.getLogger(__name__)


# ── Public API ─────────────────────────────────────────────────────────────────

def analyze(df: pd.DataFrame) -> dict:
    """
    Run full technical analysis on OHLCV DataFrame.

    Returns a dict with all computed fields needed by predictor & reporter.
    """
    df = df.copy()
    df = _compute_sma(df)
    df = _compute_volume_sma(df)

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last

    close = float(last["close"])
    prev_close = float(prev["close"])
    pct_change = round((close - prev_close) / prev_close * 100, 2) if prev_close else 0.0

    sma20 = float(last["SMA_20"]) if not pd.isna(last.get("SMA_20")) else None
    price_vs_sma = _price_vs_sma(close, sma20)

    volume = float(last["volume"])
    vol_sma = float(last["VOLUME_SMA_20"]) if not pd.isna(last.get("VOLUME_SMA_20")) else None
    volume_spike = bool(vol_sma and volume > vol_sma * VOLUME_SPIKE_RATIO)

    swing_high, swing_low, swing_high_idx, swing_low_idx = _detect_swing_high_low(df, close)
    fib_levels = _compute_fibonacci(swing_high, swing_low)

    nearest_support, nearest_resistance = _find_nearest_levels(close, fib_levels)
    price_at_fib_support = _check_proximity(close, nearest_support)
    price_at_fib_resistance = _check_proximity(close, nearest_resistance)

    return {
        # Price info
        "close": close,
        "pct_change": pct_change,
        # SMA
        "sma20": sma20,
        "price_vs_sma": price_vs_sma,
        # Volume
        "volume": volume,
        "volume_sma20": vol_sma,
        "volume_spike": volume_spike,
        # Swing points
        "swing_high": swing_high,
        "swing_low": swing_low,
        # Fibonacci
        "fib_levels": fib_levels,   # dict {level_float: price}
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "price_at_fib_support": price_at_fib_support,
        "price_at_fib_resistance": price_at_fib_resistance,
    }


# ── Internal computations ──────────────────────────────────────────────────────

def _compute_sma(df: pd.DataFrame) -> pd.DataFrame:
    """Append SMA_20 column using pandas_ta."""
    try:
        import pandas_ta as ta  # type: ignore
        df.ta.sma(length=SMA_PERIOD, close="close", append=True)
        # pandas_ta names the column SMA_{length}
        col = f"SMA_{SMA_PERIOD}"
        if col not in df.columns:
            # Sometimes pandas_ta uses different naming; search for it
            sma_cols = [c for c in df.columns if "SMA" in c.upper() and str(SMA_PERIOD) in c]
            if sma_cols:
                df.rename(columns={sma_cols[0]: col}, inplace=True)
    except Exception as exc:
        logger.warning("pandas_ta SMA failed, falling back to pandas rolling: %s", exc)
        df[f"SMA_{SMA_PERIOD}"] = df["close"].rolling(window=SMA_PERIOD).mean()
    return df


def _compute_volume_sma(df: pd.DataFrame) -> pd.DataFrame:
    """Append VOLUME_SMA_20 column."""
    try:
        import pandas_ta as ta  # type: ignore
        df["VOLUME_SMA_20"] = df.ta.sma(length=SMA_PERIOD, close="volume")
    except Exception as exc:
        logger.warning("pandas_ta Volume SMA failed, falling back to rolling: %s", exc)
        df["VOLUME_SMA_20"] = df["volume"].rolling(window=SMA_PERIOD).mean()
    return df


def _price_vs_sma(close: float, sma20) -> str:
    if sma20 is None:
        return "unknown"
    return "above" if close > sma20 else "below"


def _detect_swing_high_low(df: pd.DataFrame, close: float):
    """
    Detect the most meaningful swing high and swing low pair within FIB_LOOKBACK_MONTHS.

    Strategy:
    1. Filter to the last FIB_LOOKBACK_MONTHS months.
    2. Try W=SWING_DETECTION_WINDOW, then W=3, then rolling 60-bar max/min.
    3. Select trend-aware pair:
       - Uptrend (close > rolling mid): most recent swing low + highest swing high after it
       - Downtrend: most recent swing high + lowest swing low after it
    """
    cutoff = date.today() - relativedelta(months=FIB_LOOKBACK_MONTHS)
    sub = df[pd.to_datetime(df["date"]) >= pd.Timestamp(cutoff)].copy()

    if len(sub) < 10:
        sub = df.copy()  # not enough data, use all

    highs = sub["high"].values
    lows = sub["low"].values
    n = len(sub)

    for W in [SWING_DETECTION_WINDOW, 3]:
        sh_idx, sl_idx = _find_swings(highs, lows, n, W)
        if sh_idx and sl_idx:
            break
    else:
        sh_idx, sl_idx = None, None

    # Fallback: rolling max/min over last 60 bars
    if not sh_idx or not sl_idx:
        logger.debug("Swing detection fallback to rolling max/min")
        window = min(60, n)
        sh_price = float(sub["high"].rolling(window).max().iloc[-1])
        sl_price = float(sub["low"].rolling(window).min().iloc[-1])
        sh_i = int(sub["high"].values.argmax())
        sl_i = int(sub["low"].values.argmin())
        return sh_price, sl_price, sh_i, sl_i

    # Trend-aware pair selection
    mid = float(sub["close"].rolling(min(20, n)).mean().iloc[-1])
    uptrend = close >= mid

    if uptrend:
        # Most recent swing low, then highest swing high AFTER it
        latest_low_i = max(sl_idx)
        candidates_high = [i for i in sh_idx if i > latest_low_i]
        if not candidates_high:
            candidates_high = sh_idx
        best_high_i = max(candidates_high, key=lambda i: highs[i])
        sh_price = float(highs[best_high_i])
        sl_price = float(lows[latest_low_i])
    else:
        # Most recent swing high, then lowest swing low AFTER it
        latest_high_i = max(sh_idx)
        candidates_low = [i for i in sl_idx if i > latest_high_i]
        if not candidates_low:
            candidates_low = sl_idx
        best_low_i = min(candidates_low, key=lambda i: lows[i])
        sl_price = float(lows[best_low_i])
        sh_price = float(highs[latest_high_i])

    return sh_price, sl_price, None, None


def _find_swings(highs, lows, n: int, W: int):
    """Return lists of indices that are swing highs / swing lows with window W."""
    sh_idx = []
    sl_idx = []
    for i in range(W, n - W):
        window_h = highs[max(0, i - W): i + W + 1]
        window_l = lows[max(0, i - W): i + W + 1]
        if highs[i] == window_h.max():
            sh_idx.append(i)
        if lows[i] == window_l.min():
            sl_idx.append(i)
    return sh_idx, sl_idx


def _compute_fibonacci(swing_high: float, swing_low: float) -> dict:
    """
    Compute Fibonacci retracement price levels.
    fib[level] = swing_high - level * (swing_high - swing_low)
    """
    diff = swing_high - swing_low
    return {lvl: round(swing_high - lvl * diff, 2) for lvl in FIB_LEVELS}


def _find_nearest_levels(close: float, fib_levels: dict):
    """
    Find nearest support (fib price < close) and resistance (fib price > close).
    """
    prices = sorted(fib_levels.values())
    support = max((p for p in prices if p < close), default=min(prices))
    resistance = min((p for p in prices if p > close), default=max(prices))
    return support, resistance


def _check_proximity(close: float, level: float) -> bool:
    """Return True if close is within FIB_PROXIMITY_PCT of level."""
    if level == 0:
        return False
    return abs(close - level) / level <= FIB_PROXIMITY_PCT
