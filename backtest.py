"""
backtest.py — Validate prior predictions by checking if Target/Stoploss was hit.
"""
import csv
import logging
import os

import pandas as pd

from config import CSV_COLUMNS, SUMMARY_CSV_PATH
from data_fetcher import fetch_ohlcv

logger = logging.getLogger(__name__)


def run_backtest() -> dict:
    """
    Read SUMMARY_REPORT.csv, find rows where Ket_Qua is empty,
    fetch current price, and mark each as "Dung" or "Sai" if target/stoploss hit.

    Returns a summary dict: {"updated": int, "pending": int, "skipped": int}
    """
    if not os.path.isfile(SUMMARY_CSV_PATH):
        logger.info("No summary CSV found; skipping backtest.")
        return {"updated": 0, "pending": 0, "skipped": 0}

    rows = _read_csv()
    if not rows:
        return {"updated": 0, "pending": 0, "skipped": 0}

    pending_rows = [r for r in rows if not r.get("Ket_Qua", "").strip()]
    logger.info("Backtest: %d pending predictions to check.", len(pending_rows))

    updated = 0
    still_pending = 0
    skipped = 0

    # Fetch prices in bulk per symbol
    price_cache: dict[str, float] = {}

    for row in rows:
        ket_qua = row.get("Ket_Qua", "").strip()
        if ket_qua:
            continue  # already resolved

        symbol = row.get("Ma", "")
        du_doan = row.get("Du_Doan", "")
        try:
            target = float(row.get("Target", 0))
            stoploss = float(row.get("Stoploss", 0))
        except (ValueError, TypeError):
            skipped += 1
            continue

        # Fetch current price (cached per symbol)
        if symbol not in price_cache:
            try:
                df = fetch_ohlcv(symbol, months_back=1)
                price_cache[symbol] = float(df.iloc[-1]["close"])
            except Exception as exc:
                logger.warning("Backtest: cannot fetch price for %s: %s", symbol, exc)
                price_cache[symbol] = None

        current_price = price_cache[symbol]
        if current_price is None:
            skipped += 1
            continue

        result = _evaluate(du_doan, current_price, target, stoploss)
        if result:
            row["Ket_Qua"] = result
            updated += 1
            logger.debug(
                "Backtest: %s %s → %s (current=%.2f, target=%.2f, sl=%.2f)",
                row.get("Ngay"), symbol, result, current_price, target, stoploss,
            )
        else:
            still_pending += 1

    _write_csv(rows)
    logger.info(
        "Backtest complete: %d updated, %d still pending, %d skipped.",
        updated, still_pending, skipped,
    )
    return {"updated": updated, "pending": still_pending, "skipped": skipped}


# ── Private helpers ────────────────────────────────────────────────────────────

def _evaluate(du_doan: str, current: float, target: float, stoploss: float) -> str | None:
    """
    Return "Dung", "Sai", or None (not yet resolved).
    """
    if du_doan == "Tang":
        if current >= target:
            return "Dung"
        if current <= stoploss:
            return "Sai"

    elif du_doan == "Giam":
        if current <= target:
            return "Dung"
        if current >= stoploss:
            return "Sai"

    elif du_doan == "Di_Ngang":
        # Sideway: check if price broke out of range
        if current >= target:
            return "Dung"
        if current <= stoploss:
            return "Sai"

    return None  # neither target nor stoploss hit yet


def _read_csv() -> list[dict]:
    try:
        with open(SUMMARY_CSV_PATH, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            return list(reader)
    except Exception as exc:
        logger.error("Failed to read CSV: %s", exc)
        return []


def _write_csv(rows: list[dict]) -> None:
    try:
        with open(SUMMARY_CSV_PATH, "w", encoding="utf-8", newline="") as fh:
            # Use CSV_COLUMNS but also preserve any extra columns from existing file
            if rows:
                fieldnames = list(rows[0].keys())
                # Ensure all expected columns present
                for col in CSV_COLUMNS:
                    if col not in fieldnames:
                        fieldnames.append(col)
            else:
                fieldnames = CSV_COLUMNS

            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    except Exception as exc:
        logger.error("Failed to write CSV: %s", exc)
