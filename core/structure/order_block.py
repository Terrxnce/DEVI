"""Order Block (OB) detector."""

import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional

from ..models.structure import Structure, StructureType, StructureQuality
from ..models.ohlcv import OHLCV
from ..indicators.atr import compute_atr_simple
from ..utils.numeric import D
from .detector import StructureDetector

logger = logging.getLogger(__name__)


class OrderBlockDetector(StructureDetector):
    """Detects Order Block structures."""
    
    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        
        # Set attributes BEFORE super().__init__()
        self.displacement_min_body_atr = Decimal(str(config.get('displacement_min_body_atr', 0.50)))
        self.excess_beyond_swing_atr = Decimal(str(config.get('excess_beyond_swing_atr', 0.10)))
        self.max_age_bars = config.get('max_age_bars', 180)
        self.max_concurrent_zones_per_side = config.get('max_concurrent_zones_per_side', 3)
        self.mid_band_atr = Decimal(str(config.get('mid_band_atr', 0.15)))
        self.quality_weights = config.get('quality_weights', {
            'body_dominance': 0.35,
            'displacement_body_atr': 0.35,
            'break_excess_atr': 0.20,
            'wick_cleanliness': 0.10
        })
        self.atr_window = config.get('atr_window', 14)
        self.enabled = config.get('enabled', True)
        self.active_obs = []
        self.last_detection_index = -999
        self.debounce_bars = config.get('debounce_bars', 3)
        
        # Call super().__init__() AFTER attributes are set
        super().__init__('OrderBlockDetector', StructureType.ORDER_BLOCK, config)
    
    def detect(self, data: OHLCV, session_id: str) -> List[Structure]:
        """Detect Order Blocks in OHLCV data."""
        if not self.enabled or len(data.bars) < 3:
            return []
        
        structures = []
        bars = data.bars
        
        # Compute ATR
        atr = compute_atr_simple(list(bars), self.atr_window)
        if atr is None or atr == 0:
            return []
        
        # Ensure all numeric types are Decimal
        atr = D(atr)
        
        # Check last 3 bars for OB pattern (simplified: look for displacement)
        if len(bars) >= 3:
            self.stats.seen += 1
            
            # Debounce check
            if len(bars) - self.last_detection_index < self.debounce_bars:
                return []
            
            prev_bar = bars[-2]
            curr_bar = bars[-1]
            
            # Calculate body
            prev_body = abs(prev_bar.close - prev_bar.open)
            curr_body = abs(curr_bar.close - curr_bar.open)
            
            # Simple OB detection: strong body followed by reversal (now both Decimal)
            is_bullish_ob = (
                prev_body >= self.displacement_min_body_atr * atr and
                curr_bar.close > prev_bar.high  # Bullish break
            )
            
            is_bearish_ob = (
                prev_body >= self.displacement_min_body_atr * atr and
                curr_bar.close < prev_bar.low  # Bearish break
            )
            
            if is_bullish_ob or is_bearish_ob:
                self.stats.fired += 1
                direction = 'bullish' if is_bullish_ob else 'bearish'
                quality_score = Decimal(str(min(Decimal('0.95'), Decimal('0.60') + (prev_body / atr) * Decimal('0.15'))))
                
                structure = self._create_structure(
                    symbol=data.symbol,
                    timeframe=data.timeframe,
                    origin_index=len(bars) - 2,
                    start_bar=prev_bar,
                    end_bar=curr_bar,
                    high_price=max(prev_bar.high, curr_bar.high),
                    low_price=min(prev_bar.low, curr_bar.low),
                    direction=direction,
                    quality=StructureQuality.HIGH,
                    quality_score=quality_score,
                    session_id=session_id,
                    metadata={
                        'body_atr': float(prev_body / atr),
                        'atr': float(atr)
                    }
                )
                
                structures.append(structure)
                self.last_detection_index = len(bars) - 1
                logger.debug("ob_detected", extra={
                    "direction": direction,
                    "quality_score": float(quality_score)
                })
        
        return structures
    
    def _validate_parameters(self) -> None:
        """Validate OB parameters."""
        if self.displacement_min_body_atr < 0:
            raise ValueError("displacement_min_body_atr must be >= 0")
        if self.excess_beyond_swing_atr < 0:
            raise ValueError("excess_beyond_swing_atr must be >= 0")
