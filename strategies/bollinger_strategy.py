"""
strategies/bollinger_strategy.py — Bollinger Bands(20,2) mean-reversion strategy.

Signal logic:
  Tang  : price bounces back above lower band after touching it (confirmed reversal)
  Giam  : price bounces back below upper band after touching it (confirmed reversal)
  Di_Ngang: no confirmed reversal

Anti-whipsaw filters:
  1. Confirmation bar  : prev bar intraday low/high touched band, current bar closed back inside
  2. Volume capitulation: volume at touch bar >= SMA20 (high volume = panic/climax reversal)
  3. Bandwidth minimum : (upper - lower) / middle > 3% (enough room for mean-reversion)
  4. SMA50 trend filter: Tang only when SMA50 rising; Giam only when SMA50 falling

Target:
  Tang/Giam : middle band (SMA20)
Stoploss:
  Tang  : lower_band × 0.985 (1.5% below current lower band)
  Giam  : upper_band × 1.015 (1.5% above current upper band)
"""
import pandas as pd

from strategies.base import BaseStrategy
from predictor import recommend_t_plus


class BollingerStrategy(BaseStrategy):
    name = "Bollinger"

    BB_PERIOD = 20
    BB_STD = 2

    def generate_signal(self, df: pd.DataFrame) -> dict:
        df = df.copy()
        close = df["close"]

        # Need 52 bars: max(BB_PERIOD+2=22, SMA50+2=52)
        if len(close) < 52:
            return self._neutral_signal(float(close.iloc[-1]))

        sma = close.rolling(window=self.BB_PERIOD).mean()
        std = close.rolling(window=self.BB_PERIOD).std()

        middle = float(sma.iloc[-1])
        upper  = float(sma.iloc[-1] + self.BB_STD * std.iloc[-1])
        lower  = float(sma.iloc[-1] - self.BB_STD * std.iloc[-1])
        entry  = float(close.iloc[-1])

        if pd.isna(middle) or pd.isna(upper) or pd.isna(lower):
            return self._neutral_signal(entry)

        # Filter 3: Bandwidth minimum — bands must be wide enough for mean-reversion
        bandwidth = (upper - lower) / middle if middle > 0 else 0.0
        if bandwidth < 0.03:
            return self._neutral_signal(entry)

        # Filter 4: SMA50 trend direction — only trade with the trend
        sma50      = close.rolling(50).mean()
        sma50_now  = float(sma50.iloc[-1])
        sma50_prev = float(sma50.iloc[-6])   # 5 bars ago (1 trading week)

        if pd.isna(sma50_now) or pd.isna(sma50_prev):
            return self._neutral_signal(entry)

        trend_up   = sma50_now >= sma50_prev  # SMA50 flat or rising  → allow Tang
        trend_down = sma50_now <= sma50_prev  # SMA50 flat or falling → allow Giam

        # Filter 1: Confirmation bar
        # prev bar (d-1) = touch bar (intraday low/high); current bar (d) = confirmation bar
        prev_low   = float(df["low"].iloc[-2])
        prev_high  = float(df["high"].iloc[-2])
        cur_close  = float(close.iloc[-1])

        prev_lower = float(sma.iloc[-2] - self.BB_STD * std.iloc[-2])
        prev_upper = float(sma.iloc[-2] + self.BB_STD * std.iloc[-2])

        if pd.isna(prev_lower) or pd.isna(prev_upper):
            return self._neutral_signal(entry)

        tang_confirmed = (prev_low <= prev_lower) and (cur_close > lower)
        giam_confirmed = (prev_high >= prev_upper) and (cur_close < upper)

        # Filter 2: Volume exhaustion at touch bar (prev bar)
        vol_ok = self._check_volume_exhaustion(df)

        tang_ok = tang_confirmed and trend_up   and vol_ok
        giam_ok = giam_confirmed and trend_down and vol_ok

        if tang_ok:
            trend    = "Tang"
            target   = round(middle, 2)
            stoploss = round(lower * 0.985, 2)
            reason   = (
                f"BB xác nhận hồi phục: giá intraday ({prev_low:,.0f}) chạm dải thấp "
                f"({prev_lower:,.0f}) rồi đóng cửa ({cur_close:,.0f}) trở lại bên trong. "
                f"Volume cao (panic/capitulation). Bandwidth {bandwidth:.1%}. "
                f"SMA50 hướng lên ({sma50_prev:,.0f} → {sma50_now:,.0f}). "
                f"Kỳ vọng hồi về dải giữa ({middle:,.0f})."
            )
        elif giam_ok:
            trend    = "Giam"
            target   = round(middle, 2)
            stoploss = round(upper * 1.015, 2)
            reason   = (
                f"BB xác nhận điều chỉnh: giá intraday ({prev_high:,.0f}) chạm dải cao "
                f"({prev_upper:,.0f}) rồi đóng cửa ({cur_close:,.0f}) trở lại bên trong. "
                f"Volume cao (panic/capitulation). Bandwidth {bandwidth:.1%}. "
                f"SMA50 hướng xuống ({sma50_prev:,.0f} → {sma50_now:,.0f}). "
                f"Kỳ vọng điều chỉnh về dải giữa ({middle:,.0f})."
            )
        else:
            return self._neutral_signal(entry)

        reward   = abs(target - entry)
        risk     = abs(entry - stoploss)
        rr_ratio = round(reward / risk, 2) if risk > 0 else 0.0
        volume_spike = self._check_volume_spike(df)
        t_plus   = recommend_t_plus(rr_ratio, volume_spike)

        return {
            "trend":    trend,
            "target":   target,
            "stoploss": stoploss,
            "rr_ratio": rr_ratio,
            "t_plus":   t_plus,
            "reason":   reason,
        }

    def _check_volume_exhaustion(self, df: pd.DataFrame) -> bool:
        """True if volume at touch bar (prev bar) is >= SMA20 (high volume = capitulation/climax)."""
        if "volume" not in df.columns or len(df) < 22:
            return True  # insufficient data → skip filter
        vol     = df["volume"]
        vol_sma = vol.rolling(20).mean().iloc[-2]  # SMA20 as of touch bar
        touch_vol = float(vol.iloc[-2])            # volume on touch bar
        if pd.isna(vol_sma) or float(vol_sma) <= 0:
            return True
        return touch_vol >= float(vol_sma) * 1.0

    def _check_volume_spike(self, df: pd.DataFrame) -> bool:
        if "volume" not in df.columns or len(df) < 20:
            return False
        vol = df["volume"]
        avg = vol.rolling(20).mean().iloc[-1]
        cur = vol.iloc[-1]
        return bool(avg > 0 and cur > avg * 1.2)

    def _neutral_signal(self, entry: float) -> dict:
        target   = round(entry * 1.02, 2)
        stoploss = round(entry * 0.99, 2)
        rr_ratio = round(
            abs(target - entry) / abs(entry - stoploss), 2
        ) if abs(entry - stoploss) > 0 else 0.0
        return {
            "trend":    "Di_Ngang",
            "target":   target,
            "stoploss": stoploss,
            "rr_ratio": rr_ratio,
            "t_plus":   5,
            "reason":   "Giá đang trong vùng giữa dải Bollinger, không có tín hiệu rõ ràng.",
        }
