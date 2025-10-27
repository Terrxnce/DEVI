from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore


@dataclass
class MT5ConnectionInfo:
    broker: Optional[str] = None
    server: Optional[str] = None
    account: Optional[str] = None
    connected: bool = False


class MT5Connector:
    """No-op MT5 connector scaffold for Phase 1.5.
    Implements connect/fetch_history/disconnect with safe fallbacks.
    """

    def __init__(self) -> None:
        self.info = MT5ConnectionInfo()

    def connect(self) -> MT5ConnectionInfo:
        # No-op: pretend connected (for scaffolding)
        self.info.connected = True
        return self.info

    def fetch_history(self, symbol: str, timeframe: str, bars: int):
        """Return a DataFrame with UTC timestamps and OHLCV columns, or None if pandas missing."""
        if pd is None:
            return None
        # Empty placeholder frame with schema only
        return pd.DataFrame(columns=[
            "timestamp_utc", "open", "high", "low", "close", "volume"
        ])

    def disconnect(self) -> None:
        self.info.connected = False
