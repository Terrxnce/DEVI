"""Sweep detector."""

import logging
from decimal import Decimal
from typing import List, Dict, Any

from ..models.structure import Structure, StructureType, StructureQuality
from ..models.ohlcv import OHLCV
from ..indicators.atr import compute_atr_simple
from ..utils.numeric import D
from .detector import StructureDetector

logger = logging.getLogger(__name__)


class SweepDetector(StructureDetector):
    """Detects Sweep patterns."""
    
    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        
        # Set attributes BEFORE super().__init__()
        self.sweep_excess_atr = Decimal(str(config.get('sweep_excess_atr', 0.08)))
        self.close_back_inside_within = config.get('close_back_inside_within', 2)
        self.min_follow_through_atr = Decimal(str(config.get('min_follow_through_atr', 0.15)))
        self.follow_through_window = config.get('follow_through_window', 5)
        self.sweep_debounce_bars = config.get('sweep_debounce_bars', 6)
        self.max_age_bars = config.get('max_age_bars', 100)
        self.quality_weights = config.get('quality_weights', {
            'penetration_atr': 0.4,
            'rejection_body_atr': 0.3,
            'follow_through_atr': 0.2,
            'context_bonus': 0.1
        })
        self.context_bonus = config.get('context_bonus', {
            'at_zone_boundary': 0.05,
            'ema_aligned': 0.05
        })
        self.atr_window = config.get('atr_window', 14)
        self.enabled = config.get('enabled', True)
        self.last_detection_index = -999
        
        # Call super().__init__() AFTER attributes are set
        super().__init__('SweepDetector', StructureType.SWEEP, config)
    
    def detect(self, data: OHLCV, session_id: str) -> List[Structure]:
        """Detect Sweep patterns in OHLCV data."""
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
        
        # Debounce check
        if len(bars) - self.last_detection_index < self.sweep_debounce_bars:
            return []
        
        # Simple sweep detection: penetration beyond pivot then pullback
        if len(bars) >= 3:
            self.stats.seen += 1
            prev_bar = bars[-2]
            curr_bar = bars[-1]
            
            # Bullish sweep: low penetrates below prev low, then closes above
            bullish_sweep = (
                curr_bar.low < prev_bar.low and
                curr_bar.close > prev_bar.close
            )
            
            # Bearish sweep: high penetrates above prev high, then closes below
            bearish_sweep = (
                curr_bar.high > prev_bar.high and
                curr_bar.close < prev_bar.close
            )
            
            if bullish_sweep or bearish_sweep:
                self.stats.fired += 1
                direction = 'bullish' if bullish_sweep else 'bearish'
                quality_score = Decimal(str(min(Decimal('0.95'), Decimal('0.60'))))
                
                structure = self._create_structure(
                    symbol=data.symbol,
                    timeframe=data.timeframe,
                    origin_index=len(bars) - 1,
                    start_bar=prev_bar,
                    end_bar=curr_bar,
                    high_price=max(prev_bar.high, curr_bar.high),
                    low_price=min(prev_bar.low, curr_bar.low),
                    direction=direction,
                    quality=StructureQuality.MEDIUM,
                    quality_score=quality_score,
                    session_id=session_id,
                    metadata={'atr': float(atr)}
                )
                
                structures.append(structure)
                self.last_detection_index = len(bars) - 1
                
                logger.debug("sweep_detected", extra={
                    "direction": direction,
                    "quality_score": float(quality_score)
                })
        
        return structures
    
    def _validate_parameters(self) -> None:
        """Validate sweep parameters."""
        if self.sweep_excess_atr < 0:
            raise ValueError("sweep_excess_atr must be >= 0")
