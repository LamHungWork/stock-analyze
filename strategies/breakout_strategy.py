"""
strategies/breakout_strategy.py — N-day Donchian breakout + volume confirmation.

Signal logic:
  Tang  : close >= max(high, N ngày trước) + volume >= SMA20×1.5 + SMA20 rising
  Giam  : close <= min(low,  N ngày trước) + volume >= SMA20×1.5 + SMA20 falling
  Di_Ngang: không đủ điều kiện

Target / Stoploss:
  Tang  : target = entry × 1.07 (+7%), stoploss = entry × 0.97 (-3%)
  Giam  : target = entry × 0.93 (-7%), stoploss = entry × 1.03 (+3%)
  R:R   : 7/3 ≈ 2.3
"""
import pandas as pd

from strategies.base import BaseStrategy
from predictor import recommend_t_plus


class BreakoutStrategy(BaseStrategy):
    name = "Breakout"

    N_PERIOD  = 20     # lookback window (ngày) cho breakout level
    VOL_RATIO = 1.5    # volume tối thiểu = SMA20 × 1.5
    TP_PCT    = 0.07   # take profit 7%
    SL_PCT    = 0.03   # stop loss 3%

    def generate_signal(self, df: pd.DataFrame) -> dict:
        df = df.copy()

        # 1. Guard
        if len(df) < self.N_PERIOD + 5:
            return self._neutral_signal(float(df["close"].iloc[-1]))

        close  = df["close"]
        high   = df["high"]
        low    = df["low"]
        volume = df["volume"]
        entry  = float(close.iloc[-1])

        # 2. Breakout levels (exclude current bar to avoid trivial self-match)
        resistance = float(high.iloc[-(self.N_PERIOD + 1):-1].max())
        support    = float(low.iloc[-(self.N_PERIOD + 1):-1].min())

        # 3. Volume filter
        vol_sma = float(volume.rolling(20).mean().iloc[-1])
        cur_vol = float(volume.iloc[-1])
        if pd.isna(vol_sma) or vol_sma <= 0:
            return self._neutral_signal(entry)
        vol_ok = cur_vol >= vol_sma * self.VOL_RATIO

        # 4. Trend filter (SMA20 slope over last 5 bars)
        sma20      = close.rolling(20).mean()
        sma20_now  = float(sma20.iloc[-1])
        sma20_prev = float(sma20.iloc[-6])
        if pd.isna(sma20_now) or pd.isna(sma20_prev):
            return self._neutral_signal(entry)
        trend_up   = sma20_now > sma20_prev
        trend_down = sma20_now < sma20_prev

        # 5. Breakout conditions
        tang_signal = (entry >= resistance) and vol_ok and trend_up
        giam_signal = (entry <= support)    and vol_ok and trend_down

        # 6. Build result
        rr_ratio     = round(self.TP_PCT / self.SL_PCT, 2)  # 7/3 ≈ 2.33
        volume_spike = cur_vol >= vol_sma * 1.2
        t_plus       = recommend_t_plus(rr_ratio, volume_spike)

        if tang_signal:
            target   = round(entry * (1 + self.TP_PCT), 2)
            stoploss = round(entry * (1 - self.SL_PCT), 2)
            reason   = (
                f"Giá ({entry:,.0f}) phá vỡ vùng kháng cự {self.N_PERIOD} ngày ({resistance:,.0f}). "
                f"Khối lượng ({cur_vol:,.0f} = {cur_vol / vol_sma:.1f}× SMA20) xác nhận dòng tiền vào. "
                f"SMA20 hướng lên ({sma20_prev:,.0f} → {sma20_now:,.0f}). "
                f"Kỳ vọng tăng {self.TP_PCT:.0%} về ({target:,.0f})."
            )
            return {
                "trend":    "Tang",
                "target":   target,
                "stoploss": stoploss,
                "rr_ratio": rr_ratio,
                "t_plus":   t_plus,
                "reason":   reason,
            }

        if giam_signal:
            target   = round(entry * (1 - self.TP_PCT), 2)
            stoploss = round(entry * (1 + self.SL_PCT), 2)
            reason   = (
                f"Giá ({entry:,.0f}) phá vỡ vùng hỗ trợ {self.N_PERIOD} ngày ({support:,.0f}). "
                f"Khối lượng ({cur_vol:,.0f} = {cur_vol / vol_sma:.1f}× SMA20) xác nhận dòng tiền ra. "
                f"SMA20 hướng xuống ({sma20_prev:,.0f} → {sma20_now:,.0f}). "
                f"Kỳ vọng giảm {self.TP_PCT:.0%} về ({target:,.0f})."
            )
            return {
                "trend":    "Giam",
                "target":   target,
                "stoploss": stoploss,
                "rr_ratio": rr_ratio,
                "t_plus":   t_plus,
                "reason":   reason,
            }

        return self._neutral_signal(entry)

    def _neutral_signal(self, entry: float) -> dict:
        target   = round(entry * (1 + self.TP_PCT), 2)
        stoploss = round(entry * (1 - self.SL_PCT), 2)
        return {
            "trend":    "Di_Ngang",
            "target":   target,
            "stoploss": stoploss,
            "rr_ratio": round(self.TP_PCT / self.SL_PCT, 2),
            "t_plus":   5,
            "reason":   "Không có breakout xác nhận: giá chưa phá vỡ vùng kháng cự/hỗ trợ 20 ngày với volume đủ mạnh.",
        }
