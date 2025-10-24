"""
Trading decision models.
"""

from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, List


class DecisionType(Enum):
    """Types of trading decisions."""
    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"
    HOLD = "HOLD"


class DecisionStatus(Enum):
    """Status of a decision."""
    PENDING = "pending"
    VALIDATED = "validated"
    EXECUTED = "executed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Decision:
    """Trading decision (immutable)."""
    decision_type: DecisionType
    symbol: str
    timestamp: datetime
    session_id: str
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    position_size: Decimal
    risk_reward_ratio: Decimal
    structure_id: str
    confidence_score: Decimal
    reasoning: str
    status: DecisionStatus = DecisionStatus.PENDING
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            object.__setattr__(self, 'metadata', {})
        
        # Validate SL/TP logic
        if self.decision_type in [DecisionType.BUY, DecisionType.SELL]:
            if self.stop_loss <= 0 or self.take_profit <= 0:
                raise ValueError("SL and TP must be positive for BUY/SELL decisions")
            
            if self.decision_type == DecisionType.BUY:
                if self.stop_loss >= self.entry_price or self.take_profit <= self.entry_price:
                    raise ValueError("For BUY: SL < entry < TP")
            
            elif self.decision_type == DecisionType.SELL:
                if self.stop_loss <= self.entry_price or self.take_profit >= self.entry_price:
                    raise ValueError("For SELL: SL > entry > TP")
    
    @property
    def is_entry_decision(self) -> bool:
        """True if this is an entry decision (BUY/SELL)."""
        return self.decision_type in [DecisionType.BUY, DecisionType.SELL]
    
    @property
    def rr(self) -> Decimal:
        """Risk-reward ratio."""
        return self.risk_reward_ratio
