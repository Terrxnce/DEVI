"""
Average True Range (ATR) indicator.
"""

from decimal import Decimal
from typing import List, Optional
from ..models.ohlcv import Bar


def compute_atr_simple(bars: List[Bar], period: int = 14) -> Optional[Decimal]:
    """
    Compute ATR using simple method.
    
    Args:
        bars: List of Bar objects (must be sorted by timestamp, ascending)
        period: ATR period (default 14)
    
    Returns:
        ATR value or None if insufficient bars
    """
    if len(bars) < period + 1:
        return None
    
    # Calculate true ranges
    true_ranges = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        curr_high = bars[i].high
        curr_low = bars[i].low
        
        tr1 = curr_high - curr_low
        tr2 = abs(curr_high - prev_close)
        tr3 = abs(curr_low - prev_close)
        
        tr = max(tr1, tr2, tr3)
        true_ranges.append(tr)
    
    # Calculate ATR (simple moving average of true ranges)
    if len(true_ranges) < period:
        return None
    
    atr_sum = sum(true_ranges[-period:])
    atr = atr_sum / Decimal(period)
    
    return atr
