"""Unified Zone Rejection (UZR) detector."""

import logging
from decimal import Decimal
from typing import List, Dict, Any

from ..models.structure import Structure, StructureType, StructureQuality
from ..models.ohlcv import OHLCV
from ..indicators.atr import compute_atr_simple
from ..utils.numeric import D
from .detector import StructureDetector

logger = logging.getLogger(__name__)


class UnifiedZoneRejectionDetector(StructureDetector):
    """Detects Unified Zone Rejection patterns."""
    
    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        
        # Set attributes BEFORE super().__init__()
        self.touch_atr_buffer = Decimal(str(config.get('touch_atr_buffer', 0.20)))
        self.midline_bias = Decimal(str(config.get('midline_bias', 0.10)))
        self.min_reaction_body_atr = Decimal(str(config.get('min_reaction_body_atr', 0.35)))
        self.min_follow_through_atr = Decimal(str(config.get('min_follow_through_atr', 0.50)))
        self.lookahead_bars = config.get('lookahead_bars', 6)
        self.max_age_bars = config.get('max_age_bars', 20)
        self.debounce_bars = config.get('debounce_bars', 2)
        self.weights = config.get('weights', {
            'reaction_body': 0.35,
            'follow_through': 0.35,
            'penetration_depth': 0.20,
            'context_bonus': 0.10
        })
        self.context = config.get('context', {
            'ema_slope_min': 0.001,
            'ema_align': 0.05,
            'bos_align_bonus': 0.05
        })
        self.atr_window = config.get('atr_window', 14)
        self.enabled = config.get('enabled', True)
        self.last_detection_index = -999
        
        # Call super().__init__() AFTER attributes are set
        super().__init__('UnifiedZoneRejectionDetector', StructureType.REJECTION, config)
    
    def detect(self, data: OHLCV, session_id: str) -> List[Structure]:
        """Detect Unified Zone Rejection patterns in OHLCV data."""
        if not self.enabled or len(data.bars) < self.lookahead_bars + 2:
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
        if len(bars) - self.last_detection_index < self.debounce_bars:
            return []
        
        # Look for rejection: touch zone, reaction body, follow-through
        if len(bars) >= 3:
            self.stats.seen += 1
            
            prev_bar = bars[-2]
            curr_bar = bars[-1]
            
            # Calculate reaction body
            reaction_body = abs(curr_bar.close - curr_bar.open)
            
            # Check if reaction body is significant (now both Decimal)
            if reaction_body >= self.min_reaction_body_atr * atr:
                # Check for follow-through in lookahead bars (if available)
                follow_through = Decimal(0)
                
                if len(bars) > self.lookahead_bars:
                    lookahead = bars[-self.lookahead_bars:]
                    # Bullish follow-through: close > open
                    bullish_ft = sum(1 for b in lookahead if b.close > b.open)
                    # Bearish follow-through: close < open
                    bearish_ft = sum(1 for b in lookahead if b.close < b.open)
                    
                    follow_through = Decimal(max(bullish_ft, bearish_ft)) / Decimal(len(lookahead))
                
                # Determine direction
                is_bullish = curr_bar.close > curr_bar.open
                is_bearish = curr_bar.close < curr_bar.open
                
                if (is_bullish or is_bearish) and follow_through >= Decimal('0.3'):
                    self.stats.fired += 1
                    direction = 'bullish' if is_bullish else 'bearish'
                    quality_score = Decimal(str(min(Decimal('0.95'), Decimal('0.60') + (reaction_body / atr) * Decimal('0.15'))))
                    
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
                        metadata={
                            'reaction_body_atr': float(reaction_body / atr),
                            'follow_through': float(follow_through),
                            'atr': float(atr)
                        }
                    )
                    
                    structures.append(structure)
                    self.last_detection_index = len(bars) - 1
                    
                    logger.debug("uzr_detected", extra={
                        "direction": direction,
                        "reaction_body_atr": float(reaction_body / atr),
                        "quality_score": float(quality_score)
                    })
        
        return structures
    
    def _validate_parameters(self) -> None:
        """Validate UZR parameters."""
        if self.touch_atr_buffer < 0:
            raise ValueError("touch_atr_buffer must be >= 0")
        if self.min_reaction_body_atr < 0:
            raise ValueError("min_reaction_body_atr must be >= 0")
