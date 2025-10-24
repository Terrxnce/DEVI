"""
Session management models for intraday trading sessions.
"""

from decimal import Decimal
from datetime import datetime, time, timezone
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Optional


class SessionType(Enum):
    """Types of trading sessions."""
    ASIA = "ASIA"
    LONDON = "LONDON"
    NY_AM = "NY_AM"
    NY_PM = "NY_PM"


class SessionState(Enum):
    """States of a trading session."""
    IDLE = "IDLE"
    PREPARING = "PREPARING"
    ACTIVE = "ACTIVE"
    CLOSING = "CLOSING"
    ENDED = "ENDED"


@dataclass(frozen=True)
class Session:
    """Trading session - immutable and hashable."""
    session_id: str
    session_type: SessionType
    symbol: str
    start_time: datetime
    end_time: datetime
    state: SessionState = SessionState.IDLE
    symbol_list: List[str] = None
    session_params: Dict[str, Any] = None
    created_timestamp: datetime = None
    last_update_timestamp: datetime = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        
        if self.symbol_list is None:
            object.__setattr__(self, 'symbol_list', [self.symbol])
        if self.session_params is None:
            object.__setattr__(self, 'session_params', {})
        if self.metadata is None:
            object.__setattr__(self, 'metadata', {})
        if self.created_timestamp is None:
            object.__setattr__(self, 'created_timestamp', datetime.now(timezone.utc))
        if self.last_update_timestamp is None:
            object.__setattr__(self, 'last_update_timestamp', datetime.now(timezone.utc))
