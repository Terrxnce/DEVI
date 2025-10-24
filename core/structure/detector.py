"""Base detector class for all market structure detectors."""

import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from hashlib import sha256

from ..models.structure import Structure, StructureType, StructureQuality, LifecycleState
from ..models.ohlcv import OHLCV

logger = logging.getLogger(__name__)


class DetectorStats:
    """Statistics for detector performance tracking."""
    
    def __init__(self):
        self.seen = 0  # Bars evaluated
        self.fired = 0  # Structures detected


class StructureDetector(ABC):
    """Abstract base class for all structure detectors."""
    
    def __init__(self, name: str, structure_type: StructureType, parameters: Dict[str, Any]):
        """
        Initialize detector.
        
        Args:
            name: Detector name (e.g., 'OrderBlockDetector')
            structure_type: Type of structure this detector finds
            parameters: Configuration parameters
        """
        self.name = name
        self.structure_type = structure_type
        self.parameters = parameters or {}
        self.enabled = self.parameters.get('enabled', True)
        self.stats = DetectorStats()  # Track performance
        
        # Validate parameters (subclass can override)
        self._validate_parameters()
        
        logger.info(f"Initialized {self.name}", extra={
            "structure_type": structure_type.value,
            "enabled": self.enabled
        })
    
    @abstractmethod
    def detect(self, data: OHLCV, session_id: str) -> List[Structure]:
        """
        Detect structures in OHLCV data.
        
        Args:
            data: OHLCV time series
            session_id: Session identifier
        
        Returns:
            List of detected Structure objects
        """
        pass
    
    def _validate_parameters(self) -> None:
        """
        Validate detector parameters.
        
        Subclasses should override to validate their specific parameters.
        Called during __init__(), so subclass attributes must be set BEFORE super().__init__().
        """
        pass
    
    def _generate_deterministic_id(self, symbol: str, bar_index: int, direction: str) -> str:
        """
        Generate deterministic structure ID.
        
        Args:
            symbol: Trading symbol
            bar_index: Bar index where structure was detected
            direction: 'bullish' or 'bearish'
        
        Returns:
            Deterministic ID (SHA256 hash, first 16 chars)
        """
        data = f"{symbol}_{bar_index}_{direction}_{self.structure_type.value}"
        return sha256(data.encode()).hexdigest()[:16]
    
    def _create_structure(
        self,
        symbol: str,
        timeframe: str,
        origin_index: int,
        start_bar,
        end_bar,
        high_price: Decimal,
        low_price: Decimal,
        direction: str,
        quality: StructureQuality,
        quality_score: Decimal,
        session_id: str,
        metadata: Dict[str, Any] = None
    ) -> Structure:
        """
        Create a Structure object with common fields.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe (e.g., 'M15')
            origin_index: Bar index where structure originated
            start_bar: Starting bar
            end_bar: Ending bar
            high_price: High price of structure
            low_price: Low price of structure
            direction: 'bullish' or 'bearish'
            quality: StructureQuality enum
            quality_score: Quality score (0-1)
            session_id: Session identifier
            metadata: Additional metadata
        
        Returns:
            Structure object
        """
        structure_id = self._generate_deterministic_id(symbol, origin_index, direction)
        
        return Structure(
            structure_id=structure_id,
            structure_type=self.structure_type,
            symbol=symbol,
            timeframe=timeframe,
            origin_index=origin_index,
            start_bar=start_bar,
            end_bar=end_bar,
            high_price=high_price,
            low_price=low_price,
            direction=direction,
            quality=quality,
            quality_score=quality_score,
            lifecycle=LifecycleState.UNFILLED,
            created_timestamp=datetime.now(timezone.utc),
            session_id=session_id,
            metadata=metadata or {}
        )
