"""
strategies/base.py — Abstract base class for all trading strategies.
"""
from abc import ABC, abstractmethod

import pandas as pd


class BaseStrategy(ABC):
    """
    Abstract strategy interface.

    All strategies must implement generate_signal(df) which takes the full
    OHLCV history up to and including the current analysis day (no lookahead).
    """

    name: str = "BaseStrategy"

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame) -> dict:
        """
        Generate a trading signal from historical OHLCV data.

        Parameters
        ----------
        df : pd.DataFrame
            OHLCV DataFrame with columns: date, open, high, low, close, volume.
            Contains data up to and including the current day only (no lookahead).

        Returns
        -------
        dict with keys:
            trend      : "Tang" | "Giam" | "Di_Ngang"
            target     : float — price target
            stoploss   : float — stop-loss price
            rr_ratio   : float
            t_plus     : int (3-5) — recommended holding days
            reason     : str — Vietnamese explanation
        """
