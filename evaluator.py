"""
evaluator.py — Run all strategies on historical data, compare results, save CSVs.

Outputs:
  - SIMULATION_TRADES.csv     : every individual trade from all strategies
  - STRATEGY_COMPARISON.csv   : per-strategy summary ranking
"""
import logging
import os

import pandas as pd

from config import (
    REPORTS_DIR,
    SIMULATION_SHARES,
    SIMULATION_TRADES_CSV,
    STRATEGY_COMPARISON_CSV,
)
from simulator import run_simulation
from strategies import ALL_STRATEGIES

logger = logging.getLogger(__name__)


def evaluate_all_strategies(
    symbol: str,
    df: pd.DataFrame,
    shares: int = SIMULATION_SHARES,
) -> pd.DataFrame:
    """
    Run simulation for all strategies and produce comparison output.

    Parameters
    ----------
    symbol : ticker symbol
    df     : full OHLCV DataFrame
    shares : shares per trade

    Returns
    -------
    pd.DataFrame  — strategy comparison table (ranked by Total_PnL desc)
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)

    all_trades = []

    for strategy in ALL_STRATEGIES:
        logger.info("Simulating %s / %s ...", symbol, strategy.name)
        trades = run_simulation(symbol, df, strategy, shares)
        all_trades.extend(trades)

    if not all_trades:
        logger.warning("No trades generated for %s", symbol)
        return pd.DataFrame()

    trades_df = pd.DataFrame(all_trades)

    # ── Đánh dấu đúng/sai hướng: Tang đúng nếu giá thực tế tăng, Giam đúng nếu giá giảm ──
    trades_df["direction_correct"] = (
        ((trades_df["trend"] == "Tang") & (trades_df["exit_price"] > trades_df["entry_price"])) |
        ((trades_df["trend"] == "Giam") & (trades_df["exit_price"] < trades_df["entry_price"]))
    )

    # ── Save individual trades ────────────────────────────────────────────────
    trades_df.to_csv(SIMULATION_TRADES_CSV, index=False, encoding="utf-8")
    logger.info("Saved %d trades to %s", len(trades_df), SIMULATION_TRADES_CSV)

    # ── Per-strategy summary ──────────────────────────────────────────────────
    comparison = _build_comparison(trades_df)
    comparison.to_csv(STRATEGY_COMPARISON_CSV, index=False, encoding="utf-8")
    logger.info("Saved strategy comparison to %s", STRATEGY_COMPARISON_CSV)

    _print_ranking(comparison)

    return comparison


def _build_comparison(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-strategy stats from trades DataFrame."""
    rows = []

    for strategy_name, grp in trades_df.groupby("strategy"):
        grp = grp.copy()

        # P&L chỉ tính lệnh thực sự (Tang/Giam), bỏ Di_Ngang
        active = grp[grp["trend"] != "Di_Ngang"].copy()
        total = len(active)
        wins = (active["result"] == "Win").sum()
        losses = (active["result"] == "Loss").sum()
        win_rate = round(wins / total * 100, 1) if total > 0 else 0.0
        total_pnl = active["pnl"].sum()
        avg_pnl = round(active["pnl"].mean(), 0) if total > 0 else 0.0
        avg_return_pct = round(active["pnl_pct"].mean(), 2) if "pnl_pct" in active.columns and total > 0 else 0.0

        # Tổng vốn bỏ ra = Σ(entry_price × shares) cho từng lệnh Tang/Giam
        total_capital = (active["entry_price"] * active["shares"]).sum() if total > 0 else 0.0
        # Lợi nhuận % trên tổng vốn bỏ ra
        return_on_capital_pct = round(total_pnl / total_capital * 100, 2) if total_capital > 0 else 0.0

        # ── Directional accuracy (Tang/Giam only, loại Di_Ngang) ─────────────
        tang_grp = grp[grp["trend"] == "Tang"]
        giam_grp = grp[grp["trend"] == "Giam"]

        tang_n = len(tang_grp)
        tang_correct = int((tang_grp["exit_price"] > tang_grp["entry_price"]).sum())
        tang_acc = round(tang_correct / tang_n * 100, 1) if tang_n > 0 else 0.0

        giam_n = len(giam_grp)
        giam_correct = int((giam_grp["exit_price"] < giam_grp["entry_price"]).sum())
        giam_acc = round(giam_correct / giam_n * 100, 1) if giam_n > 0 else 0.0

        dir_total = tang_n + giam_n
        dir_correct = tang_correct + giam_correct
        dir_acc = round(dir_correct / dir_total * 100, 1) if dir_total > 0 else 0.0

        # Monthly breakdown
        grp["month"] = pd.to_datetime(grp["signal_date"].astype(str)).dt.to_period("M")
        monthly = grp.groupby("month")["pnl"].sum().to_dict()
        monthly_str = "; ".join(f"{k}: {v:+,.0f}" for k, v in sorted(monthly.items()))

        rows.append({
            "Strategy": strategy_name,
            "Total_Trades": total,
            "Win_Trades": wins,
            "Loss_Trades": losses,
            "Win_Rate_Pct": win_rate,
            "Total_Capital": int(total_capital),
            "Total_PnL": int(total_pnl),
            "Return_On_Capital_Pct": return_on_capital_pct,
            "Avg_Return_Pct": avg_return_pct,
            "Avg_PnL_Per_Trade": int(avg_pnl),
            "Dir_Accuracy_Pct": dir_acc,
            "Tang_Signals": tang_n,
            "Tang_Correct": tang_correct,
            "Tang_Acc_Pct": tang_acc,
            "Giam_Signals": giam_n,
            "Giam_Correct": giam_correct,
            "Giam_Acc_Pct": giam_acc,
            "Monthly_PnL": monthly_str,
        })

    comparison = pd.DataFrame(rows)
    comparison.sort_values("Return_On_Capital_Pct", ascending=False, inplace=True)
    comparison.reset_index(drop=True, inplace=True)
    comparison.insert(0, "Rank", range(1, len(comparison) + 1))
    return comparison


def _print_ranking(comparison: pd.DataFrame) -> None:
    """Print a formatted ranking table to console."""
    # ── Bảng 1: P&L ──────────────────────────────────────────────────────────
    print("\n" + "=" * 88)
    print("  STRATEGY RANKING (by Return on Capital %)")
    print("=" * 88)
    print(
        f"{'Rank':<5} {'Strategy':<15} {'Trades':<8} {'WinRate':<10} "
        f"{'Tổng vốn':>14} {'Lợi nhuận':>12} {'%/Vốn':>8} {'Avg/Trade':>10}"
    )
    print("-" * 88)
    for _, row in comparison.iterrows():
        print(
            f"{row['Rank']:<5} {row['Strategy']:<15} {row['Total_Trades']:<8} "
            f"{row['Win_Rate_Pct']:<10.1f} "
            f"{row['Total_Capital']:>14,.0f} "
            f"{row['Total_PnL']:>12,.0f} "
            f"{row['Return_On_Capital_Pct']:>7.2f}% "
            f"{row['Avg_Return_Pct']:>9.2f}%"
        )
    print("=" * 88)

    # ── Bảng 2: Directional Accuracy ─────────────────────────────────────────
    print("\n" + "=" * 78)
    print("  DIRECTIONAL ACCURACY — Tỷ lệ đoán đúng xu hướng (loại Di_Ngang)")
    print("=" * 78)
    print(
        f"{'Rank':<5} {'Strategy':<15} {'Overall':>9}"
        f"  {'Tang(đúng/tổng)':>16} {'Tang%':>7}"
        f"  {'Giam(đúng/tổng)':>16} {'Giam%':>7}"
    )
    print("-" * 78)

    # Rank by directional accuracy
    dir_sorted = comparison.sort_values("Dir_Accuracy_Pct", ascending=False).reset_index(drop=True)
    for rank, (_, row) in enumerate(dir_sorted.iterrows(), start=1):
        tang_str = f"{row['Tang_Correct']}/{row['Tang_Signals']}"
        giam_str = f"{row['Giam_Correct']}/{row['Giam_Signals']}"
        print(
            f"{rank:<5} {row['Strategy']:<15} {row['Dir_Accuracy_Pct']:>8.1f}%"
            f"  {tang_str:>16} {row['Tang_Acc_Pct']:>6.1f}%"
            f"  {giam_str:>16} {row['Giam_Acc_Pct']:>6.1f}%"
        )
    print("=" * 78 + "\n")


def load_monthly_summary(symbol: str, strategy_name: str) -> list[dict]:
    """
    Load monthly P&L summary from SIMULATION_TRADES_CSV for use in reports.

    Returns list of dicts: [{month, trades, wins, pnl}, ...]
    """
    if not os.path.isfile(SIMULATION_TRADES_CSV):
        return []

    try:
        df = pd.read_csv(SIMULATION_TRADES_CSV)
        mask = (df["symbol"] == symbol) & (df["strategy"] == strategy_name)
        grp = df[mask].copy()
        if grp.empty:
            return []

        grp["month"] = pd.to_datetime(grp["signal_date"].astype(str)).dt.to_period("M")

        rows = []
        for month, mdf in grp.groupby("month"):
            total = len(mdf)
            wins = (mdf["result"] == "Win").sum()
            pnl = mdf["pnl"].sum()
            rows.append({
                "month": str(month),
                "trades": total,
                "wins": wins,
                "pnl": int(pnl),
            })
        return sorted(rows, key=lambda r: r["month"])
    except Exception as exc:
        logger.warning("Failed to load monthly summary: %s", exc)
        return []
