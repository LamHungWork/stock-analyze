"""
main.py — Entry point for VN30 Technical Analysis Tool.

Usage:
    python main.py

Flow:
    1. Setup logging (console + reports/run.log)
    2. Ensure reports/ directory exists
    3. Run backtest to validate prior predictions
    4. Loop VN30 symbols → fetch → analyze → predict → write report
    5. Print summary
"""
import logging
import os
import sys
import time
from datetime import date

from config import INTER_SYMBOL_DELAY_SECONDS, LOG_PATH, REPORTS_DIR, VN30_SYMBOLS
from data_fetcher import fetch_ohlcv
from technical_analysis import analyze
from predictor import predict
from report_generator import append_to_summary_csv, write_markdown_report
from backtest import run_backtest


# ── Logging setup ──────────────────────────────────────────────────────────────

def setup_logging() -> None:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, datefmt=datefmt, handlers=handlers)


# ── Per-symbol processing ──────────────────────────────────────────────────────

def process_symbol(symbol: str, run_date: date) -> bool:
    """
    Fetch data, run analysis + prediction, write report and CSV row.

    Returns True on success, False on any error.
    """
    logger = logging.getLogger(__name__)
    try:
        logger.info("Processing %s ...", symbol)
        df = fetch_ohlcv(symbol)
        analysis = analyze(df)
        prediction = predict(analysis)
        md_path = write_markdown_report(symbol, run_date, analysis, prediction)
        append_to_summary_csv(symbol, run_date, analysis, prediction)
        logger.info(
            "%s → %s | Close: %.0f | Target: %.0f | SL: %.0f | SR: %.1f%%",
            symbol,
            prediction["trend"],
            analysis["close"],
            prediction["target"],
            prediction["stoploss"],
            prediction["success_rate"],
        )
        return True
    except Exception as exc:
        logger.error("Failed to process %s: %s", symbol, exc, exc_info=True)
        return False


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    run_date = date.today()
    logger.info("=" * 60)
    logger.info("VN30 Technical Analysis — %s", run_date)
    logger.info("=" * 60)

    # Step 1: Validate prior predictions
    logger.info("Running backtest on prior predictions ...")
    bt_result = run_backtest()
    logger.info(
        "Backtest: %d updated, %d still pending, %d skipped.",
        bt_result["updated"],
        bt_result["pending"],
        bt_result["skipped"],
    )

    # Step 2: Process each VN30 symbol
    results = {}
    for i, symbol in enumerate(VN30_SYMBOLS):
        results[symbol] = process_symbol(symbol, run_date)
        # Respect VCI guest rate limit (20 req/min) between symbols
        if i < len(VN30_SYMBOLS) - 1:
            time.sleep(INTER_SYMBOL_DELAY_SECONDS)

    # Step 3: Print summary
    success = [s for s, ok in results.items() if ok]
    failed = [s for s, ok in results.items() if not ok]

    logger.info("-" * 60)
    logger.info("SUMMARY: %d/%d symbols processed successfully.", len(success), len(VN30_SYMBOLS))
    if failed:
        logger.warning("Failed symbols: %s", ", ".join(failed))
    logger.info("Reports saved to: %s", REPORTS_DIR)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
