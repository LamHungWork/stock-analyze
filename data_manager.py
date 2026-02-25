"""
data_manager.py — Download, store, and load historical OHLCV data.

Primary source : vnstock (VCI)
Fallback source: yfinance (.VN suffix)
"""
import logging
import os

import pandas as pd

from config import DATA_DIR, SIMULATION_START_DATE

logger = logging.getLogger(__name__)


def download_and_save(symbol: str, start: str = SIMULATION_START_DATE) -> pd.DataFrame:
    """
    Fetch OHLCV data from vnstock/yfinance and save to data/{symbol}.csv.

    If the local file already exists, load it and only append new trading days.
    Returns the full DataFrame.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    csv_path = os.path.join(DATA_DIR, f"{symbol}.csv")

    existing_df = None
    fetch_start = start

    if os.path.isfile(csv_path):
        try:
            existing_df = _read_csv(csv_path)
            if not existing_df.empty:
                last_date = existing_df["date"].max()
                # fetch only from the day after the last saved date
                next_day = pd.Timestamp(last_date) + pd.Timedelta(days=1)
                fetch_start = next_day.strftime("%Y-%m-%d")
                logger.info(
                    "%s: local data up to %s, fetching from %s",
                    symbol, last_date, fetch_start,
                )
        except Exception as exc:
            logger.warning("Failed to read existing CSV for %s: %s", symbol, exc)
            existing_df = None

    from datetime import date
    today_str = date.today().strftime("%Y-%m-%d")

    if fetch_start > today_str:
        logger.info("%s: already up-to-date, no new data to fetch.", symbol)
        return existing_df if existing_df is not None else pd.DataFrame()

    new_df = _fetch(symbol, fetch_start, today_str)

    if new_df is not None and not new_df.empty:
        if existing_df is not None and not existing_df.empty:
            # Remove any overlapping dates before concatenating
            new_dates = set(new_df["date"].astype(str))
            existing_df = existing_df[~existing_df["date"].astype(str).isin(new_dates)]
            combined = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined = new_df

        combined.sort_values("date", inplace=True)
        combined.reset_index(drop=True, inplace=True)
        combined.to_csv(csv_path, index=False)
        logger.info("%s: saved %d rows to %s", symbol, len(combined), csv_path)
        return combined
    else:
        logger.warning("%s: no new data fetched.", symbol)
        return existing_df if existing_df is not None else pd.DataFrame()


def load_local(symbol: str) -> pd.DataFrame:
    """
    Load data/{symbol}.csv and return a normalized DataFrame.
    Raises FileNotFoundError if the file does not exist.
    """
    csv_path = os.path.join(DATA_DIR, f"{symbol}.csv")
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(
            f"No local data file for {symbol}. "
            f"Run download_and_save('{symbol}') first."
        )
    df = _read_csv(csv_path)
    logger.info("%s: loaded %d rows from local cache.", symbol, len(df))
    return df


# ── Private helpers ─────────────────────────────────────────────────────────────

def _fetch(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Try vnstock first, fall back to yfinance."""
    try:
        df = _fetch_vnstock(symbol, start, end)
        if df is not None and not df.empty:
            logger.debug("vnstock OK for %s (%d rows)", symbol, len(df))
            return df
    except Exception as exc:
        logger.warning("vnstock failed for %s: %s", symbol, exc)

    try:
        df = _fetch_yfinance(symbol, start, end)
        if df is not None and not df.empty:
            logger.debug("yfinance OK for %s (%d rows)", symbol, len(df))
            return df
    except Exception as exc:
        logger.warning("yfinance failed for %s: %s", symbol, exc)

    return None


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
    df = df.reset_index()
    df.rename(columns={"Date": "time"}, inplace=True)
    return _normalize(df)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    if "time" in df.columns and "date" not in df.columns:
        df.rename(columns={"time": "date"}, inplace=True)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.date

    required = ["date", "open", "high", "low", "close", "volume"]
    available = [c for c in required if c in df.columns]
    df = df[available].copy()

    df.sort_values("date", ascending=True, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def _read_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df.sort_values("date", ascending=True, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df
