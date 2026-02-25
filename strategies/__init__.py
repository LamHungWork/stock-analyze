"""
strategies/ — Multi-strategy framework for VN30 Technical Analysis Tool.

Available strategies:
- BollingerStrategy : Bollinger Bands(20,2) mean-reversion
- BreakoutStrategy  : N-day Donchian breakout + volume confirmation
"""
from .bollinger_strategy import BollingerStrategy
from .breakout_strategy import BreakoutStrategy

ALL_STRATEGIES = [
    BollingerStrategy(),
    BreakoutStrategy(),
]

__all__ = [
    "BollingerStrategy",
    "BreakoutStrategy",
    "ALL_STRATEGIES",
]
