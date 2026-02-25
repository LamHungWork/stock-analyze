"""
daily_run.py — Chạy cuối ngày sau khi thị trường đóng cửa.

Flow cho mỗi mã:
  1. Fetch/update data hôm nay (data_manager)
  2. Update open positions: pending→open, open→check exit
  3. Run Bollinger + Breakout trên data hôm nay
  4. Nếu Tang/Giam → add signal as pending position
  5. Write daily markdown report

Usage:
  python3 daily_run.py                    # tất cả 30 mã VN30 (default)
  python3 daily_run.py --symbols HPG VIC  # test nhanh
"""
import argparse
import logging
import time
from datetime import date

import pandas as pd

from config import (
    VN30_SYMBOLS,
    SIMULATION_START_DATE,
    INTER_SYMBOL_DELAY_SECONDS,
    REPORTS_DIR,
    LOG_PATH,
)
import data_manager
import positions
import report_generator
from strategies import ALL_STRATEGIES

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    import os
    os.makedirs(REPORTS_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
        ],
    )


def parse_args() -> list | None:
    parser = argparse.ArgumentParser(description="VN30 Daily End-of-Day Runner")
    parser.add_argument(
        "--symbols",
        nargs="+",
        metavar="SYMBOL",
        help="Override symbol list (e.g. --symbols HPG VIC)",
    )
    args = parser.parse_args()
    return args.symbols or None


def main() -> None:
    setup_logging()
    today = date.today()
    logger.info("=== daily_run.py: %s ===", today)

    symbol_list = parse_args() or VN30_SYMBOLS

    all_closed_today: dict = {}
    all_signals: dict = {}

    for symbol in symbol_list:
        logger.info("--- Processing %s ---", symbol)

        # 1. Fetch / update data
        try:
            df = data_manager.download_and_save(symbol, start=SIMULATION_START_DATE)
        except Exception as exc:
            logger.error("%s: data fetch failed: %s", symbol, exc)
            continue

        if df is None or df.empty:
            logger.warning("%s: no data available, skipping.", symbol)
            continue

        # 2. Build today_bar (use last row if today's bar not yet available)
        today_rows = df[df["date"] == today]
        if today_rows.empty:
            last_row = df.iloc[-1]
            today_bar = {
                "open":  float(last_row["open"]),
                "high":  float(last_row["high"]),
                "low":   float(last_row["low"]),
                "close": float(last_row["close"]),
            }
            logger.warning(
                "%s: today (%s) not in data, using last available row (%s)",
                symbol, today, last_row["date"],
            )
        else:
            r = today_rows.iloc[0]
            today_bar = {
                "open":  float(r["open"]),
                "high":  float(r["high"]),
                "low":   float(r["low"]),
                "close": float(r["close"]),
            }

        # 3. Update existing positions (pending→open, open→check exit)
        try:
            closed_today = positions.update_positions(today, symbol, today_bar)
        except Exception as exc:
            logger.error("%s: position update failed: %s", symbol, exc)
            closed_today = []

        # 4. Generate signals from each strategy
        symbol_signals: dict = {}
        today_close = today_bar["close"]
        df_today = df[df["date"] <= today].copy()

        for strategy in ALL_STRATEGIES:
            try:
                sig = strategy.generate_signal(df_today)
                symbol_signals[strategy.name] = sig
                positions.add_signal(symbol, strategy.name, today, sig, today_close)
            except Exception as exc:
                logger.error(
                    "%s/%s: signal generation failed: %s", symbol, strategy.name, exc
                )

        # 5. Write daily markdown report
        open_pos = positions.get_open_positions(symbol)
        try:
            report_generator.write_daily_report(
                symbol=symbol,
                run_date=today,
                df=df_today,
                strategy_signals=symbol_signals,
                closed_today=closed_today,
                open_positions=open_pos,
            )
        except Exception as exc:
            logger.error("%s: report writing failed: %s", symbol, exc)

        all_closed_today[symbol] = closed_today
        all_signals[symbol] = symbol_signals

        time.sleep(INTER_SYMBOL_DELAY_SECONDS)

    # Flush all position changes to disk
    positions.save_positions()

    # Print console summary
    _print_summary(today, all_signals, all_closed_today)


def _print_summary(today: date, all_signals: dict, all_closed_today: dict) -> None:
    _TREND_LABEL = {
        "Tang":     "Tăng ↑",
        "Giam":     "Giảm ↓",
        "Di_Ngang": "Đi Ngang →",
    }

    tang_list: list[str] = []
    giam_list: list[str] = []

    for symbol, signals in all_signals.items():
        for strategy_name, sig in signals.items():
            t = sig.get("trend", "Di_Ngang")
            if t == "Tang":
                tang_list.append(f"{symbol}({strategy_name})")
            elif t == "Giam":
                giam_list.append(f"{symbol}({strategy_name})")

    print(f"\n{'='*60}")
    print(f"DAILY RUN SUMMARY — {today}")
    print(f"{'='*60}")

    print(f"\n[ Tín hiệu Tăng ({len(tang_list)}) ]")
    print("  " + (", ".join(tang_list) if tang_list else "(không có)"))

    print(f"\n[ Tín hiệu Giảm ({len(giam_list)}) ]")
    print("  " + (", ".join(giam_list) if giam_list else "(không có)"))

    total_closed = sum(len(v) for v in all_closed_today.values())
    if total_closed > 0:
        print(f"\n[ Lệnh đóng hôm nay ({total_closed}) ]")
        for symbol, closed in all_closed_today.items():
            for pos in closed:
                pnl = pos.get("pnl_pct")
                try:
                    pnl_str = f"{float(pnl):+.2f}%" if pnl is not None and not pd.isna(float(pnl)) else "N/A"
                except (TypeError, ValueError):
                    pnl_str = "N/A"
                trend_vn = _TREND_LABEL.get(pos.get("trend", ""), pos.get("trend", ""))
                print(
                    f"  {symbol}/{pos.get('strategy')} {trend_vn}"
                    f" → {pos.get('exit_reason')} {pnl_str}"
                )

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
