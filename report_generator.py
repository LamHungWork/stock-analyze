"""
report_generator.py — Write per-symbol Markdown reports and update the summary CSV.
"""
import csv
import logging
import os
from datetime import date

import pandas as pd

from config import CSV_COLUMNS, REPORTS_DIR, SUMMARY_CSV_PATH

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
        "",
        "### Lý do",
        "",
        p["reason"],
        "",
        "---",
        f"*Báo cáo được tạo tự động bởi VN30 Technical Analysis Tool — {run_date}*",
    ]

    return "\n".join(lines) + "\n"


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
