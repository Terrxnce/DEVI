"""
Base indicator classes.
"""

from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Any, Dict


@dataclass(frozen=True)
class IndicatorValue:
    """Single indicator value with metadata."""
    value: Decimal
    timestamp: datetime
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            object.__setattr__(self, 'metadata', {})


