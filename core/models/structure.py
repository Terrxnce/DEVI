"""Market structure models (Order Blocks, Fair Value Gaps, etc.)."""

from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional
from .ohlcv import Bar


class StructureType(Enum):
    """Types of market structures."""
    ORDER_BLOCK = "order_block"
    FAIR_VALUE_GAP = "fair_value_gap"
    BREAK_OF_STRUCTURE = "break_of_structure"
    SWEEP = "sweep"
    REJECTION = "rejection"
    ENGULFING = "engulfing"


class StructureQuality(Enum):
    """Quality levels for structures."""
    PREMIUM = "premium"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LifecycleState(Enum):
    """Lifecycle states for structures."""
    UNFILLED = "unfilled"
    PARTIAL = "partial"
    FILLED = "filled"
    EXPIRED = "expired"
    FOLLOWED_THROUGH = "followed_through"


@dataclass(frozen=True)
class Structure:
    """Market structure (immutable)."""
    structure_id: str
    structure_type: StructureType
    symbol: str
    timeframe: str
    origin_index: int
    start_bar: Bar
    end_bar: Bar
    high_price: Decimal
    low_price: Decimal
    direction: str  # 'bullish' or 'bearish'
    quality: StructureQuality
    quality_score: Decimal
    lifecycle: LifecycleState
    created_timestamp: datetime
    session_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    links: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.end_bar.timestamp < self.start_bar.timestamp:
            raise ValueError("End bar must be >= start bar timestamp")
        
        if self.metadata is None:
            object.__setattr__(self, 'metadata', {})
        if self.links is None:
            object.__setattr__(self, 'links', {})
    
    @property
    def is_bullish(self) -> bool:
        """True if structure is bullish (supports upward movement)."""
        return self.direction == 'bullish'
    
    @property
    def is_bearish(self) -> bool:
        """True if structure is bearish (supports downward movement)."""
        return self.direction == 'bearish'
    
    @property
    def price_range(self) -> Decimal:
        """Price range of the structure."""
        return self.high_price - self.low_price
    
    @property
    def midpoint(self) -> Decimal:
        """Midpoint price of the structure."""
        return (self.high_price + self.low_price) / 2
