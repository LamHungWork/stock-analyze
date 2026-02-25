"""
report_generator.py — Write per-symbol Markdown reports and update the summary CSV.
"""
import csv
import logging
import os
from datetime import date, timedelta

import pandas as pd

from config import CSV_COLUMNS, REPORTS_DIR, SUMMARY_CSV_PATH, SIMULATION_SYMBOL

logger = logging.getLogger(__name__)


# ── Markdown report ────────────────────────────────────────────────────────────

def write_markdown_report(
    symbol: str,
    run_date: date,
    analysis: dict,
    prediction: dict,
) -> str:
    """
    Write a Markdown report to reports/[SYMBOL]/[YYYY-MM-DD].md

    Returns the file path written.
    """
    symbol_dir = os.path.join(REPORTS_DIR, symbol)
    os.makedirs(symbol_dir, exist_ok=True)
    filepath = os.path.join(symbol_dir, f"{run_date}.md")

    content = _build_markdown(symbol, run_date, analysis, prediction)
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(content)

    logger.debug("Markdown written: %s", filepath)
    return filepath


def _build_markdown(
    symbol: str,
    run_date: date,
    a: dict,
    p: dict,
) -> str:
    """Build the Markdown string for a single stock report."""
    fib = a.get("fib_levels", {})

    trend_vn = {
        "Tang": "Tăng ↑",
        "Giam": "Giảm ↓",
        "Di_Ngang": "Đi Ngang →",
    }.get(p["trend"], p["trend"])

    lines = [
        f"# Báo Cáo Phân Tích Kỹ Thuật: {symbol}",
        f"**Ngày phân tích:** {run_date}",
        "",
        "---",
        "",
        "## 1. Thông Tin Chung",
        "",
        f"| Chỉ tiêu | Giá trị |",
        f"|:---------|:--------|",
        f"| Mã cổ phiếu | **{symbol}** |",
        f"| Giá đóng cửa | **{a['close']:,.0f}** |",
        f"| Thay đổi | {_fmt_pct(a['pct_change'])} |",
        f"| Khối lượng | {a['volume']:,.0f} |",
        "",
        "---",
        "",
        "## 2. Phân Tích SMA20",
        "",
        f"| Chỉ tiêu | Giá trị |",
        f"|:---------|:--------|",
        f"| SMA20 | {_fmt_price(a['sma20'])} |",
        f"| Vị thế giá | {'**Trên SMA20** ✅' if a['price_vs_sma'] == 'above' else '**Dưới SMA20** ⚠️'} |",
        f"| Volume SMA20 | {_fmt_price(a['volume_sma20'])} |",
        f"| Tín hiệu Volume | {'**Đột biến** 🔥' if a['volume_spike'] else 'Bình thường'} |",
        "",
        "---",
        "",
        "## 3. Phân Tích Fibonacci",
        "",
        f"**Swing High:** {a['swing_high']:,.0f} &nbsp;|&nbsp; "
        f"**Swing Low:** {a['swing_low']:,.0f}",
        "",
        "| Mức Fibonacci | Giá |",
        "|:-------------|----:|",
    ]

    # Fibonacci table rows
    for lvl in sorted(fib.keys()):
        tag = ""
        price = fib[lvl]
        if price == a.get("nearest_support") and a.get("price_at_fib_support"):
            tag = " ← **Hỗ trợ gần nhất** ✅"
        elif price == a.get("nearest_resistance") and a.get("price_at_fib_resistance"):
            tag = " ← **Kháng cự gần nhất** ⚠️"
        elif price == a.get("nearest_support"):
            tag = " ← Hỗ trợ gần nhất"
        elif price == a.get("nearest_resistance"):
            tag = " ← Kháng cự gần nhất"
        lines.append(f"| {lvl:.3f} | {price:,.0f}{tag} |")

    t_plus = p.get("t_plus", 5)
    shares = 100

    # Estimated T+1 open ≈ close × 1.001
    est_entry = round(a["close"] * 1.001, 0)
    est_tp_pnl = int(shares * abs(p["target"] - est_entry))
    est_sl_pnl = int(shares * abs(est_entry - p["stoploss"]))
    tp_sign = "+" if p["trend"] != "Giam" else "-"
    sl_sign = "-" if p["trend"] != "Giam" else "+"

    lines += [
        "",
        "---",
        "",
        "## 4. Dự Đoán",
        "",
        f"| Chỉ tiêu | Giá trị |",
        f"|:---------|:--------|",
        f"| Xu hướng | **{trend_vn}** |",
        f"| Giá dự báo (Target) | **{p['target']:,.0f}** |",
        f"| Cắt lỗ (Stoploss) | **{p['stoploss']:,.0f}** |",
        f"| Tỷ lệ R/R | {p['rr_ratio']:.2f} |",
        f"| Tỷ lệ thành công | **{p['success_rate']:.1f}%** |",
        f"| Khuyến nghị nắm giữ | **T+{t_plus}** |",
        "",
        "### Lý do",
        "",
        p["reason"],
        "",
        "---",
        "",
        "## 5. Mô Phỏng Giao Dịch (100 cổ phiếu)",
        "",
        f"| Chỉ tiêu | Giá trị |",
        f"|:---------|:--------|",
        f"| Giá vào lệnh dự kiến (T+1 open) | ~{est_entry:,.0f} đ (ước tính) |",
        f"| Khuyến nghị T+ | **T+{t_plus}** |",
        f"| Lãi nếu đạt Target | {tp_sign}{est_tp_pnl:,} đ |",
        f"| Lỗ nếu chạm Stoploss | {sl_sign}{est_sl_pnl:,} đ |",
    ]

    # Section 6 — Monthly summary (only if simulation data exists for this symbol)
    monthly_rows = _load_monthly_for_report(symbol)
    if monthly_rows:
        lines += [
            "",
            "---",
            "",
            f"## 6. Tổng Kết Tháng ({symbol} - Strategy: SMA+Fib)",
            "",
            "| Tháng | Số lệnh | Thắng | Lãi/Lỗ |",
            "|:------|--------:|------:|--------:|",
        ]
        for row in monthly_rows:
            win_pct = round(row["wins"] / row["trades"] * 100) if row["trades"] > 0 else 0
            pnl_str = f"{row['pnl']:+,.0f} đ"
            lines.append(
                f"| {row['month']} | {row['trades']} | "
                f"{row['wins']} ({win_pct}%) | {pnl_str} |"
            )

    lines += [
        "",
        "---",
        f"*Báo cáo được tạo tự động bởi VN30 Technical Analysis Tool — {run_date}*",
    ]

    return "\n".join(lines) + "\n"


def _load_monthly_for_report(symbol: str) -> list:
    """Load monthly simulation summary if available."""
    try:
        from evaluator import load_monthly_summary
        return load_monthly_summary(symbol, "SMA+Fib")
    except Exception:
        return []


# ── Summary CSV ────────────────────────────────────────────────────────────────

def append_to_summary_csv(
    symbol: str,
    run_date: date,
    analysis: dict,
    prediction: dict,
) -> None:
    """
    Append one row to SUMMARY_REPORT.csv.

    Creates the file with header if it does not exist.
    Skips if a row for (run_date, symbol) already exists.
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # Read existing rows to check for duplicate
    existing_rows = []
    file_exists = os.path.isfile(SUMMARY_CSV_PATH)

    if file_exists:
        with open(SUMMARY_CSV_PATH, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            existing_rows = list(reader)

        # Check duplicate
        for row in existing_rows:
            if row.get("Ngay") == str(run_date) and row.get("Ma") == symbol:
                logger.debug("CSV row already exists for %s %s, skipping.", run_date, symbol)
                return

    new_row = {
        "Ngay": str(run_date),
        "Ma": symbol,
        "Gia_Hien_Tai": analysis["close"],
        "Du_Doan": prediction["trend"],
        "Target": prediction["target"],
        "Stoploss": prediction["stoploss"],
        "RR_Ratio": prediction["rr_ratio"],
        "Ti_Le_Thanh_Cong": f"{prediction['success_rate']:.1f}%",
        "Ket_Qua": "",
    }

    write_header = not file_exists
    with open(SUMMARY_CSV_PATH, "a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(new_row)

    logger.debug("CSV appended: %s %s", run_date, symbol)


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _fmt_price(val) -> str:
    if val is None:
        return "N/A"
    return f"{float(val):,.0f}"


def _fmt_pct(val: float) -> str:
    sign = "+" if val >= 0 else ""
    color = "🟢" if val > 0 else ("🔴" if val < 0 else "⚪")
    return f"{color} {sign}{val:.2f}%"


# ── Daily report (Phase 2 format) ───────────────────────────────────────────────

def write_daily_report(
    symbol: str,
    run_date: date,
    df: pd.DataFrame,
    strategy_signals: dict,
    closed_today: list,
    open_positions: list,
) -> str:
    """
    Write reports/[SYMBOL]/[YYYY-MM-DD].md in the new daily format.

    Parameters
    ----------
    symbol           : stock ticker
    run_date         : analysis date (today)
    df               : full OHLCV DataFrame up to run_date
    strategy_signals : {strategy_name: signal_dict}
    closed_today     : list of position dicts closed today
    open_positions   : list of position dicts still pending/open

    Returns the file path written.
    """
    symbol_dir = os.path.join(REPORTS_DIR, symbol)
    os.makedirs(symbol_dir, exist_ok=True)
    filepath = os.path.join(symbol_dir, f"{run_date}.md")

    content = _build_daily_markdown(symbol, run_date, df, strategy_signals, closed_today, open_positions)
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(content)

    logger.debug("Daily report written: %s", filepath)
    return filepath


def _build_daily_markdown(
    symbol: str,
    run_date: date,
    df: pd.DataFrame,
    strategy_signals: dict,
    closed_today: list,
    open_positions: list,
) -> str:
    # ── Header data ──────────────────────────────────────────────────────────────
    last_row = df.iloc[-1]
    close = float(last_row["close"])
    volume = float(last_row.get("volume", 0))

    if len(df) >= 2:
        prev_close = float(df.iloc[-2]["close"])
        pct_change = (close - prev_close) / prev_close * 100 if prev_close > 0 else 0.0
    else:
        pct_change = 0.0

    pct_sign = "+" if pct_change >= 0 else ""
    pct_color = "🟢" if pct_change > 0 else ("🔴" if pct_change < 0 else "⚪")

    lines = [
        f"# {symbol} — Báo cáo ngày {run_date}",
        "",
        f"**Giá đóng cửa:** {close:,.0f}   "
        f"**Thay đổi:** {pct_color} {pct_sign}{pct_change:.2f}%   "
        f"**Volume:** {volume:,.0f}",
        "",
        "---",
        "",
        "## 1. Phân Tích Chiến Lược Hôm Nay",
        "",
    ]

    _TREND_LABEL = {
        "Tang": "Tăng ↑",
        "Giam": "Giảm ↓",
        "Di_Ngang": "Đi Ngang →",
    }

    for strategy_name, sig in strategy_signals.items():
        trend_vn = _TREND_LABEL.get(sig.get("trend", "Di_Ngang"), sig.get("trend", ""))
        target = sig.get("target", 0)
        stoploss = sig.get("stoploss", 0)
        rr = sig.get("rr_ratio", 0)
        reason = sig.get("reason", "")
        lines += [
            f"### {strategy_name}",
            f"- **Tín hiệu:** {trend_vn}",
            f"- **Target:** {target:,.0f}   **Stoploss:** {stoploss:,.0f}   **R:R:** {rr:.2f}",
            f"- **Lý do:** {reason}",
            "",
        ]

    lines += ["---", ""]

    # ── Section 2: Closed positions ───────────────────────────────────────────────
    if closed_today:
        lines += [
            "## 2. Kết Quả Lệnh Đóng Hôm Nay",
            "",
            "| Chiến lược | Xu hướng | Ngày vào | Giá vào | Target | Stoploss | Kết quả | Lời/Lỗ (%) | Lý do |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for pos in closed_today:
            trend_vn = _TREND_LABEL.get(pos.get("trend", ""), pos.get("trend", ""))
            entry_date = pos.get("entry_date", "")
            entry_price = pos.get("entry_price")
            ep_str = f"{float(entry_price):,.0f}" if entry_price is not None and _is_number(entry_price) else "N/A"
            target_val = pos.get("target")
            t_str = f"{float(target_val):,.0f}" if target_val is not None and _is_number(target_val) else "N/A"
            sl_val = pos.get("stoploss")
            sl_str = f"{float(sl_val):,.0f}" if sl_val is not None and _is_number(sl_val) else "N/A"
            pnl = pos.get("pnl_pct")
            pnl_str = f"{float(pnl):+.2f}%" if pnl is not None and _is_number(pnl) else "N/A"
            exit_reason = pos.get("exit_reason", "")
            if exit_reason == "TP":
                result_str = "✅ TP"
            elif exit_reason == "SL":
                result_str = "❌ SL"
            else:
                result_str = "⏰ Hết hạn"
            lines.append(
                f"| {pos.get('strategy', '')} | {trend_vn} | {entry_date} | "
                f"{ep_str} | {t_str} | {sl_str} | {result_str} | {pnl_str} | {exit_reason} |"
            )
        lines += ["", "---", ""]

    # ── Section 3: Open positions ─────────────────────────────────────────────────
    if open_positions:
        lines += [
            "## 3. Vị Thế Đang Mở",
            "",
            "| Chiến lược | Xu hướng | Ngày vào | Giá vào | Target | Stoploss | Hạn chót |",
            "|---|---|---|---|---|---|---|",
        ]
        for pos in open_positions:
            trend_vn = _TREND_LABEL.get(pos.get("trend", ""), pos.get("trend", ""))
            entry_date = pos.get("entry_date", "")
            entry_price = pos.get("entry_price")
            ep_str = f"{float(entry_price):,.0f}" if entry_price is not None and _is_number(entry_price) else "pending"
            target_val = pos.get("target")
            t_str = f"{float(target_val):,.0f}" if target_val is not None and _is_number(target_val) else "N/A"
            sl_val = pos.get("stoploss")
            sl_str = f"{float(sl_val):,.0f}" if sl_val is not None and _is_number(sl_val) else "N/A"
            expire = pos.get("expected_exit_date", "")
            lines.append(
                f"| {pos.get('strategy', '')} | {trend_vn} | {entry_date} | "
                f"{ep_str} | {t_str} | {sl_str} | {expire} |"
            )
        lines += ["", "---", ""]

    # ── Section 4: Recommendations for tomorrow ───────────────────────────────────
    action_signals = {
        name: sig for name, sig in strategy_signals.items()
        if sig.get("trend") in ("Tang", "Giam")
    }
    if action_signals:
        next_date = _next_trading_date(run_date)
        lines += [
            "## 4. Khuyến Nghị Ngày Mai",
            "",
            f"> Dựa trên tín hiệu ngày {run_date}, khuyến nghị vào lệnh ngày {next_date}:",
            "",
            "| Chiến lược | Xu hướng | Giá vào dự kiến | Target | Stoploss | R:R | T+ |",
            "|---|---|---|---|---|---|---|",
        ]
        for strategy_name, sig in action_signals.items():
            trend = sig["trend"]
            trend_vn = _TREND_LABEL.get(trend, trend)
            t_plus = int(sig.get("t_plus", 5))
            target = sig["target"]
            stoploss = sig["stoploss"]
            rr = sig.get("rr_ratio", 0)
            if trend == "Tang":
                recommended_entry = round(close * 1.001, 2)
            else:
                recommended_entry = round(close * 0.999, 2)
            expected_exit = _add_trading_days(next_date, t_plus)
            lines.append(
                f"| {strategy_name} | {trend_vn} | {recommended_entry:,.0f} | "
                f"{target:,.0f} | {stoploss:,.0f} | {rr:.2f} | T+{t_plus} |"
            )

        # Action block for each signal
        lines.append("")
        for strategy_name, sig in action_signals.items():
            trend = sig["trend"]
            t_plus = int(sig.get("t_plus", 5))
            if trend == "Tang":
                recommended_entry = round(close * 1.001, 2)
            else:
                recommended_entry = round(close * 0.999, 2)
            expected_exit = _add_trading_days(next_date, t_plus)
            lines += [
                f"**{strategy_name} — Hành động:**",
                f"- Vào lệnh tại **giá mở cửa** ngày {next_date} (≈ {recommended_entry:,.0f})",
                f"- Đặt lệnh chốt lời tại **{sig['target']:,.0f}**",
                f"- Đặt cắt lỗ tại **{sig['stoploss']:,.0f}**",
                f"- Dự kiến nắm giữ **T+{t_plus}** (đến {expected_exit})",
                "",
            ]

        lines += ["---", ""]

    lines.append(
        f"*Báo cáo được tạo tự động bởi VN30 Technical Analysis Tool — {run_date}*"
    )
    return "\n".join(lines) + "\n"


# ── Daily report helpers ─────────────────────────────────────────────────────────

def _next_trading_date(d: date) -> date:
    """Return the next trading day after `d` (skips weekends)."""
    nd = d + timedelta(days=1)
    while nd.weekday() >= 5:
        nd += timedelta(days=1)
    return nd


def _add_trading_days(d: date, n: int) -> date:
    """Add `n` trading days to date `d`."""
    current = d
    for _ in range(n):
        current = _next_trading_date(current)
    return current


def _is_number(val) -> bool:
    """Return True if val is a finite number (not NaN, not None)."""
    try:
        f = float(val)
        import math
        return not math.isnan(f)
    except (TypeError, ValueError):
        return False
