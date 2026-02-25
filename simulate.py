"""
simulate.py — CLI entry point for historical simulation.

Usage:
    python simulate.py                  # run HPG, all strategies
    python simulate.py --symbol VCB     # run một mã cụ thể
    python simulate.py --vn30           # run toàn bộ 30 mã VN30
    python simulate.py --start 2024-01-01
"""
import argparse
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    SIMULATION_SYMBOL,
    SIMULATION_START_DATE,
    SIMULATION_SHARES,
    REPORTS_DIR,
    DATA_DIR,
    VN30_SYMBOLS,
    INTER_SYMBOL_DELAY_SECONDS,
    SIMULATION_TRADES_CSV,
    STRATEGY_COMPARISON_CSV,
)
import data_manager
from evaluator import evaluate_all_strategies, _build_comparison, _print_ranking
from simulator import run_simulation
from strategies import ALL_STRATEGIES

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("simulate")


def main():
    parser = argparse.ArgumentParser(
        description="VN30 Multi-Strategy Historical P&L Simulation"
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Ticker symbol to simulate",
    )
    parser.add_argument(
        "--vn30",
        action="store_true",
        help="Run simulation for all 30 VN30 symbols",
    )
    parser.add_argument(
        "--start",
        default=SIMULATION_START_DATE,
        help=f"Start date YYYY-MM-DD (default: {SIMULATION_START_DATE})",
    )
    args = parser.parse_args()

    if args.vn30:
        _run_vn30(args.start)
    else:
        symbol = (args.symbol or SIMULATION_SYMBOL).upper()
        _run_single(symbol, args.start)


# ── Single symbol ─────────────────────────────────────────────────────────────

def _run_single(symbol: str, start: str):
    print(f"\n{'='*60}")
    print(f"  VN30 Multi-Strategy Simulation")
    print(f"  Symbol : {symbol}")
    print(f"  Start  : {start}")
    print(f"{'='*60}\n")

    df = _download(symbol, start)
    if df is None:
        sys.exit(1)

    os.makedirs(REPORTS_DIR, exist_ok=True)
    evaluate_all_strategies(symbol, df)

    print(f"\nOutput files:")
    print(f"  Trades     : {SIMULATION_TRADES_CSV}")
    print(f"  Comparison : {STRATEGY_COMPARISON_CSV}")
    print(f"  Data cache : {os.path.join(DATA_DIR, symbol + '.csv')}\n")


# ── All VN30 ──────────────────────────────────────────────────────────────────

def _run_vn30(start: str):
    print(f"\n{'='*60}")
    print(f"  VN30 Full Simulation — {len(VN30_SYMBOLS)} mã")
    print(f"  Start  : {start}")
    print(f"{'='*60}\n")

    os.makedirs(REPORTS_DIR, exist_ok=True)
    all_trades = []
    failed = []

    for i, symbol in enumerate(VN30_SYMBOLS, start=1):
        print(f"[{i:02d}/{len(VN30_SYMBOLS)}] {symbol} ...", end=" ", flush=True)

        df = _download(symbol, start)
        if df is None:
            print("SKIP (no data)")
            failed.append(symbol)
            continue

        trades = []
        for strategy in ALL_STRATEGIES:
            t = run_simulation(symbol, df, strategy, SIMULATION_SHARES)
            trades.extend(t)

        all_trades.extend(trades)
        wins = sum(1 for t in trades if t["result"] == "Win")
        print(f"{len(trades)} trades, {wins} wins")

        if i < len(VN30_SYMBOLS):
            time.sleep(INTER_SYMBOL_DELAY_SECONDS)

    if not all_trades:
        logger.error("Không có trade nào được tạo. Kiểm tra kết nối mạng.")
        sys.exit(1)

    trades_df = pd.DataFrame(all_trades)

    # direction_correct column
    trades_df["direction_correct"] = (
        ((trades_df["trend"] == "Tang") & (trades_df["exit_price"] > trades_df["entry_price"])) |
        ((trades_df["trend"] == "Giam") & (trades_df["exit_price"] < trades_df["entry_price"]))
    )

    trades_df.to_csv(SIMULATION_TRADES_CSV, index=False, encoding="utf-8")
    logger.info("Saved %d trades → %s", len(trades_df), SIMULATION_TRADES_CSV)

    # Per-symbol per-strategy comparison
    comparison = _build_vn30_comparison(trades_df)
    comparison.to_csv(STRATEGY_COMPARISON_CSV, index=False, encoding="utf-8")
    logger.info("Saved comparison → %s", STRATEGY_COMPARISON_CSV)

    _print_vn30_ranking(comparison)

    if failed:
        print(f"\nSkipped symbols (no data): {', '.join(failed)}")

    print(f"\nOutput files:")
    print(f"  Trades     : {SIMULATION_TRADES_CSV}")
    print(f"  Comparison : {STRATEGY_COMPARISON_CSV}\n")


def _build_vn30_comparison(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Per-symbol per-strategy aggregation."""
    rows = []
    for (symbol, strategy_name), grp in trades_df.groupby(["symbol", "strategy"]):
        grp = grp.copy()
        total = len(grp)
        wins = (grp["result"] == "Win").sum()
        win_rate = round(wins / total * 100, 1) if total > 0 else 0.0
        total_pnl = int(grp["pnl"].sum())

        tang_grp = grp[grp["trend"] == "Tang"]
        giam_grp = grp[grp["trend"] == "Giam"]

        tang_n = len(tang_grp)
        tang_correct = int((tang_grp["exit_price"] > tang_grp["entry_price"]).sum())
        tang_acc = round(tang_correct / tang_n * 100, 1) if tang_n > 0 else None

        giam_n = len(giam_grp)
        giam_correct = int((giam_grp["exit_price"] < giam_grp["entry_price"]).sum())
        giam_acc = round(giam_correct / giam_n * 100, 1) if giam_n > 0 else None

        dir_total = tang_n + giam_n
        dir_correct = tang_correct + giam_correct
        dir_acc = round(dir_correct / dir_total * 100, 1) if dir_total > 0 else None

        rows.append({
            "Symbol": symbol,
            "Strategy": strategy_name,
            "Total_Trades": total,
            "Win_Trades": int(wins),
            "Win_Rate_Pct": win_rate,
            "Total_PnL": total_pnl,
            "Dir_Accuracy_Pct": dir_acc,
            "Tang_Signals": tang_n,
            "Tang_Acc_Pct": tang_acc,
            "Giam_Signals": giam_n,
            "Giam_Acc_Pct": giam_acc,
        })

    df = pd.DataFrame(rows)
    df.sort_values(["Symbol", "Total_PnL"], ascending=[True, False], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def _print_vn30_ranking(comparison: pd.DataFrame):
    """Print per-strategy summary across all VN30 symbols."""
    print("\n" + "=" * 80)
    print("  VN30 FULL RESULTS — Tổng hợp theo Strategy (tất cả mã)")
    print("=" * 80)

    summary = (
        comparison.groupby("Strategy")
        .agg(
            Symbols=("Symbol", "nunique"),
            Total_Trades=("Total_Trades", "sum"),
            Win_Trades=("Win_Trades", "sum"),
            Total_PnL=("Total_PnL", "sum"),
        )
        .reset_index()
    )
    summary["Win_Rate_Pct"] = round(summary["Win_Trades"] / summary["Total_Trades"] * 100, 1)
    summary["Avg_PnL_Per_Symbol"] = (summary["Total_PnL"] / summary["Symbols"]).round(0).astype(int)
    summary.sort_values("Total_PnL", ascending=False, inplace=True)

    print(f"\n{'Strategy':<15} {'Symbols':<9} {'Trades':<9} {'WinRate':<10} {'Total PnL':>14} {'Avg/Symbol':>12}")
    print("-" * 72)
    for _, row in summary.iterrows():
        print(
            f"{row['Strategy']:<15} {row['Symbols']:<9} {row['Total_Trades']:<9} "
            f"{row['Win_Rate_Pct']:<10.1f} {row['Total_PnL']:>14,.0f} {row['Avg_PnL_Per_Symbol']:>12,.0f}"
        )
    print("=" * 80)

    # Top 10 symbol+strategy by PnL
    print("\n  TOP 10 — Symbol × Strategy (by P&L)")
    print("=" * 70)
    top = comparison.nlargest(10, "Total_PnL")[
        ["Symbol", "Strategy", "Win_Rate_Pct", "Total_PnL", "Dir_Accuracy_Pct",
         "Tang_Signals", "Tang_Acc_Pct", "Giam_Signals", "Giam_Acc_Pct"]
    ]
    print(f"{'Symbol':<8} {'Strategy':<15} {'WinRate':<9} {'PnL':>12} {'DirAcc':>9}  Tang(n/%)  Giam(n/%)")
    print("-" * 80)
    for _, row in top.iterrows():
        tang_str = f"{row['Tang_Signals']:.0f}/{row['Tang_Acc_Pct'] or 0:.0f}%"
        giam_str = f"{row['Giam_Signals']:.0f}/{row['Giam_Acc_Pct'] or 0:.0f}%"
        dir_str = f"{row['Dir_Accuracy_Pct'] or 0:.1f}%"
        print(
            f"{row['Symbol']:<8} {row['Strategy']:<15} {row['Win_Rate_Pct']:<9.1f} "
            f"{row['Total_PnL']:>12,.0f} {dir_str:>9}  {tang_str:<10} {giam_str}"
        )
    print("=" * 80 + "\n")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _download(symbol: str, start: str):
    try:
        df = data_manager.download_and_save(symbol, start=start)
        if df is None or df.empty:
            logger.warning("%s: no data returned", symbol)
            return None
        return df
    except Exception as exc:
        logger.warning("%s: download failed — %s", symbol, exc)
        return None


if __name__ == "__main__":
    main()
