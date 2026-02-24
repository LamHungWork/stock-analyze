"""
data_fetcher.py — Fetch OHLCV data for a VN30 symbol.

Primary source : vnstock (VCI)
Fallback source: yfinance (.VN suffix)
"""
import logging
from datetime import date, timedelta

import pandas as pd
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)


def fetch_ohlcv(symbol: str, months_back: int = 7) -> pd.DataFrame:
    """
    Fetch daily OHLCV data for *symbol* going back *months_back* months.

    Returns a DataFrame with columns:
        date (datetime.date), open, high, low, close, volume

    Raises RuntimeError if both sources fail.
    """
    end_date = date.today()
    start_date = end_date - relativedelta(months=months_back)

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # ── Primary: vnstock ──────────────────────────────────────────────────────
    try:
        df = _fetch_vnstock(symbol, start_str, end_str)
        if df is not None and not df.empty:
            logger.debug("vnstock OK for %s (%d rows)", symbol, len(df))
            return df
    except Exception as exc:
        logger.warning("vnstock failed for %s: %s", symbol, exc)

    # ── Fallback: yfinance ────────────────────────────────────────────────────
    try:
        df = _fetch_yfinance(symbol, start_str, end_str)
        if df is not None and not df.empty:
            logger.debug("yfinance OK for %s (%d rows)", symbol, len(df))
            return df
    except Exception as exc:
        logger.warning("yfinance failed for %s: %s", symbol, exc)

    raise RuntimeError(
        f"Both data sources failed for symbol '{symbol}'. "
        "Check network connectivity and symbol validity."
    )


# ── Private helpers ────────────────────────────────────────────────────────────

def _fetch_vnstock(symbol: str, start: str, end: str) -> pd.DataFrame:
    from vnstock import Vnstock  # type: ignore

    stock = Vnstock().stock(symbol=symbol, source="VCI")
    df = stock.quote.history(start=start, end=end, interval="1D")
    return _normalize(df)


def _fetch_yfinance(symbol: str, start: str, end: str) -> pd.DataFrame:
    import yfinance as yf  # type: ignore

    ticker = yf.Ticker(symbol + ".VN")
    df = ticker.history(start=start, end=end, interval="1d")
    if df.empty:
        return df
    # yfinance uses a DatetimeIndex; reset to column
    df = df.reset_index()
    df.rename(columns={"Date": "time"}, inplace=True)
    return _normalize(df)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Rename / lowercase columns and ensure *date* column is datetime.date, sorted asc."""
    if df is None or df.empty:
        return df

    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    # Rename 'time' → 'date' if present
    if "time" in df.columns and "date" not in df.columns:
        df.rename(columns={"time": "date"}, inplace=True)

    # Convert date column to datetime.date
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.date

    # Keep only required columns (ignore extras)
    required = ["date", "open", "high", "low", "close", "volume"]
    available = [c for c in required if c in df.columns]
    df = df[available].copy()

    df.sort_values("date", ascending=True, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df
