"""
Engulfing pattern detector.
"""

import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from hashlib import sha256
import json

from ..models.structure import Structure, StructureType, StructureQuality, LifecycleState
from ..models.ohlcv import Bar, OHLCV
from ..indicators.atr import compute_atr_simple
from ..utils.numeric import D
from .detector import StructureDetector

logger = logging.getLogger(__name__)


class EngulfingDetector(StructureDetector):
    """Detects bullish and bearish engulfing patterns."""
    
    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        
        # Set attributes BEFORE super().__init__()
        self.min_body_atr = Decimal(str(config.get('min_body_atr', 0.6)))
        self.min_body_to_range = Decimal(str(config.get('min_body_to_range', 0.55)))
        self.atr_window = config.get('atr_window', 14)
        self.debounce_bars = config.get('debounce_bars', 3)
        self.lookahead_bars = config.get('lookahead_bars', 6)
        self.enabled = config.get('enabled', True)
        self.last_detection_index = -999
        
        # Call super().__init__() AFTER attributes are set
        super().__init__('EngulfingDetector', StructureType.ENGULFING, config)
    
    def detect(self, data: OHLCV, session_id: str) -> List[Structure]:
        """
        Detect engulfing patterns in OHLCV data.
        
        Args:
            data: OHLCV time series
            session_id: Session identifier
        
        Returns:
            List of detected Structure objects
        """
        if not self.enabled or len(data.bars) < 2:
            return []
        
        structures = []
        bars = data.bars
        
        # Compute ATR
        atr = compute_atr_simple(list(bars), self.atr_window)
        if atr is None or atr == 0:
            return []
        
        # Ensure all numeric types are Decimal
        atr = D(atr)
        
        # Check last bar for engulfing pattern
        if len(bars) >= 2:
            self.stats.seen += 1
            
            prev_bar = bars[-2]
            curr_bar = bars[-1]
            
            # Calculate bodies
            prev_body = abs(prev_bar.close - prev_bar.open)
            curr_body = abs(curr_bar.close - curr_bar.open)
            
            # Check if current bar engulfs previous bar (now both Decimal)
            min_body_threshold = self.min_body_atr * atr
            min_ratio_threshold = self.min_body_to_range
            
            bullish_engulf = (
                curr_bar.close > prev_bar.open and
                curr_bar.open < prev_bar.close and
                curr_body > prev_body and
                curr_body >= min_body_threshold and
                curr_body / (curr_bar.high - curr_bar.low) >= min_ratio_threshold
            )
            
            bearish_engulf = (
                curr_bar.close < prev_bar.open and
                curr_bar.open > prev_bar.close and
                curr_body > prev_body and
                curr_body >= min_body_threshold and
                curr_body / (curr_bar.high - curr_bar.low) >= min_ratio_threshold
            )
            
            # Debounce: don't detect too frequently
            if len(bars) - self.last_detection_index < self.debounce_bars:
                bullish_engulf = False
                bearish_engulf = False
            
            if bullish_engulf or bearish_engulf:
                self.stats.fired += 1
                direction = 'bullish' if bullish_engulf else 'bearish'
                quality_score = Decimal(str(min(Decimal('0.95'), Decimal('0.70') + (curr_body / atr) * Decimal('0.1'))))
                
                structure = self._create_structure(
                    symbol=data.symbol,
                    timeframe=data.timeframe,
                    origin_index=len(bars) - 1,
                    start_bar=prev_bar,
                    end_bar=curr_bar,
                    high_price=max(prev_bar.high, curr_bar.high),
                    low_price=min(prev_bar.low, curr_bar.low),
                    direction=direction,
                    quality=StructureQuality.HIGH,
                    quality_score=quality_score,
                    session_id=session_id,
                    metadata={
                        'prev_body': float(prev_body),
                        'curr_body': float(curr_body),
                        'atr': float(atr),
                        'body_to_range': float(curr_body / (curr_bar.high - curr_bar.low))
                    }
                )
                
                structures.append(structure)
                self.last_detection_index = len(bars) - 1
                
                logger.debug("engulfing_detected", extra={
                    "structure_id": structure.structure_id,
                    "direction": direction,
                    "quality_score": float(quality_score),
                    "bar_index": len(bars) - 1
                })
        
        return structures
    
    def _generate_id(self, symbol: str, bar_index: int, direction: str) -> str:
        """Generate deterministic structure ID."""
        data = f"{symbol}_{bar_index}_{direction}_engulfing"
        return sha256(data.encode()).hexdigest()[:16]
