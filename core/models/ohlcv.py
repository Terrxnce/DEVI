"""
OHLCV data models for price bars and time series.
"""

from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Bar:
    """Single OHLCV bar (immutable)."""
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    timestamp: datetime
    
    def __post_init__(self):
        if self.high < self.low:
            raise ValueError("High must be >= Low")
        if self.high < self.open or self.high < self.close:
            raise ValueError("High must be >= Open and Close")
        if self.low > self.open or self.low > self.close:
            raise ValueError("Low must be <= Open and Close")


@dataclass(frozen=True)
class OHLCV:
    """Time series of OHLCV bars."""
    symbol: str
    bars: Tuple[Bar, ...]
    timeframe: str
    
    @property
    def latest_bar(self) -> Bar:
        """Get the most recent bar."""
        return self.bars[-1] if self.bars else None
    
    @property
    def length(self) -> int:
        """Number of bars."""
        return len(self.bars)
