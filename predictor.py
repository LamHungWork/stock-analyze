"""
predictor.py — Generate trading prediction from technical analysis result.
"""
import logging

logger = logging.getLogger(__name__)


def predict(analysis: dict) -> dict:
    """
    Derive trend, target, stoploss, R/R ratio, success rate, and reason.

    Parameters
    ----------
    analysis : dict
        Output of technical_analysis.analyze()

    Returns
    -------
    dict with keys:
        trend          : "Tang" | "Giam" | "Di_Ngang"
        target         : float
        stoploss       : float
        rr_ratio       : float
        success_rate   : float  (%)
        reason         : str (Vietnamese)
    """
    close = analysis["close"]
    price_vs_sma = analysis["price_vs_sma"]
    volume_spike = analysis["volume_spike"]
    price_at_fib_support = analysis["price_at_fib_support"]
    price_at_fib_resistance = analysis["price_at_fib_resistance"]
    fib_levels = analysis["fib_levels"]
    swing_low = analysis["swing_low"]
    swing_high = analysis["swing_high"]
    nearest_support = analysis["nearest_support"]
    nearest_resistance = analysis["nearest_resistance"]

    # ── Signal classification ─────────────────────────────────────────────────
    bullish = (
        price_vs_sma == "above"
        and volume_spike is True
        and price_at_fib_support is True
    )
    bearish = (
        price_vs_sma == "below"
        and price_at_fib_resistance is True
    )

    if bullish:
        trend = "Tang"
    elif bearish:
        trend = "Giam"
    else:
        trend = "Di_Ngang"

    # ── Target / Stoploss ─────────────────────────────────────────────────────
    if trend == "Tang":
        raw_target = fib_levels.get(0.236, close)
        target = raw_target if raw_target > close else fib_levels.get(0.0, close)
        stoploss = round(swing_low * (1 - 0.02), 2)

    elif trend == "Giam":
        raw_target = fib_levels.get(0.618, close)
        target = raw_target if raw_target < close else fib_levels.get(1.0, close)
        stoploss = round(swing_high * (1 + 0.02), 2)

    else:  # Di_Ngang
        target = nearest_resistance
        stoploss = nearest_support

    target = round(float(target), 2)
    stoploss = round(float(stoploss), 2)

    # ── R/R ratio and success rate ────────────────────────────────────────────
    reward = abs(target - close)
    risk = abs(close - stoploss)

    if risk > 0:
        rr_ratio = round(reward / risk, 2)
    else:
        rr_ratio = 0.0

    # Success rate = 1 - breakeven win rate  (derived from R/R)
    if rr_ratio > 0:
        success_rate = round((1 - 1 / (1 + rr_ratio)) * 100, 1)
    else:
        success_rate = 50.0

    # ── Vietnamese reason string ──────────────────────────────────────────────
    reason = _build_reason(
        trend, price_vs_sma, volume_spike,
        price_at_fib_support, price_at_fib_resistance,
        analysis.get("nearest_support"), analysis.get("nearest_resistance"),
        analysis.get("sma20"), close,
    )

    return {
        "trend": trend,
        "target": target,
        "stoploss": stoploss,
        "rr_ratio": rr_ratio,
        "success_rate": success_rate,
        "reason": reason,
    }


# ── Private helpers ────────────────────────────────────────────────────────────

def _build_reason(
    trend: str,
    price_vs_sma: str,
    volume_spike: bool,
    at_support: bool,
    at_resistance: bool,
    nearest_support,
    nearest_resistance,
    sma20,
    close: float,
) -> str:
    parts = []

    # SMA context
    if price_vs_sma == "above" and sma20:
        parts.append(
            f"Giá ({close:,.0f}) đang nằm TRÊN SMA20 ({sma20:,.0f}), "
            "cho thấy xu hướng tăng ngắn hạn."
        )
    elif price_vs_sma == "below" and sma20:
        parts.append(
            f"Giá ({close:,.0f}) đang nằm DƯỚI SMA20 ({sma20:,.0f}), "
            "cho thấy áp lực giảm."
        )

    # Volume context
    if volume_spike:
        parts.append(
            "Khối lượng giao dịch tăng đột biến (>1.2x trung bình 20 phiên), "
            "xác nhận động lực mua mạnh."
        )
    else:
        parts.append("Khối lượng giao dịch ở mức bình thường.")

    # Fibonacci context
    if trend == "Tang" and at_support and nearest_support:
        parts.append(
            f"Giá đang bật lại từ vùng hỗ trợ Fibonacci ({nearest_support:,.0f}), "
            "tạo cơ hội mua tốt."
        )
    elif trend == "Giam" and at_resistance and nearest_resistance:
        parts.append(
            f"Giá chạm kháng cự Fibonacci ({nearest_resistance:,.0f}) và có dấu hiệu quay đầu, "
            "áp lực bán tăng."
        )
    elif trend == "Di_Ngang":
        s = f"{nearest_support:,.0f}" if nearest_support else "N/A"
        r = f"{nearest_resistance:,.0f}" if nearest_resistance else "N/A"
        parts.append(
            f"Giá đang dao động trong vùng sideway giữa hỗ trợ {s} "
            f"và kháng cự {r}."
        )

    return " ".join(parts)
