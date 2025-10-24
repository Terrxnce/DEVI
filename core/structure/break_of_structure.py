"""Break of Structure (BOS) detector."""

import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional

from ..models.structure import Structure, StructureType, StructureQuality
from ..models.ohlcv import OHLCV
from ..indicators.atr import compute_atr_simple
from .detector import StructureDetector

logger = logging.getLogger(__name__)


class BreakOfStructureDetector(StructureDetector):
    """Detects Break of Structure patterns."""
    
    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        
        # Set attributes BEFORE super().__init__()
        self.min_break_strength = Decimal(str(config.get('min_break_strength', 0.0015)))
        self.pivot_window = config.get('pivot_window', 4)
        self.confirmation_periods = config.get('confirmation_periods', 1)
        self.debounce_bars = config.get('debounce_bars', 2)
        self.volume_confirmation = config.get('volume_confirmation', False)
        self.atr_window = config.get('atr_window', 14)
        self.enabled = config.get('enabled', True)
        self._last_bos_index = None
        self._last_bos_direction = None
        
        # Call super().__init__() AFTER attributes are set
        super().__init__('BreakOfStructureDetector', StructureType.BREAK_OF_STRUCTURE, config)
    
    def detect(self, data: OHLCV, session_id: str) -> List[Structure]:
        """Detect Break of Structure patterns in OHLCV data."""
        if not self.enabled or len(data.bars) < self.pivot_window + 2:
            return []
        
        structures = []
        bars = data.bars
        
        # Compute ATR
        atr = compute_atr_simple(list(bars), self.atr_window)
        if atr is None or atr == 0:
            return []
        
        # Find pivot high/low in pivot_window
        if len(bars) >= self.pivot_window + 1:
            pivot_bars = bars[-(self.pivot_window + 1):-1]
            
            pivot_high = max(b.high for b in pivot_bars)
            pivot_low = min(b.low for b in pivot_bars)
            
            curr_bar = bars[-1]
            
            # Bullish BOS: break above pivot high
            bullish_bos = curr_bar.close > pivot_high
            
            # Bearish BOS: break below pivot low
            bearish_bos = curr_bar.close < pivot_low
            
            # Debounce: don't detect same direction too frequently
            if bullish_bos and self._last_bos_direction == 'bullish':
                if len(bars) - self._last_bos_index < self.debounce_bars:
                    bullish_bos = False
            
            if bearish_bos and self._last_bos_direction == 'bearish':
                if len(bars) - self._last_bos_index < self.debounce_bars:
                    bearish_bos = False
            
            if bullish_bos or bearish_bos:
                direction = 'bullish' if bullish_bos else 'bearish'
                quality_score = Decimal(str(min(0.95, 0.65)))
                
                structure = self._create_structure(
                    symbol=data.symbol,
                    timeframe=data.timeframe,
                    origin_index=len(bars) - 1,
                    start_bar=bars[-(self.pivot_window + 1)],
                    end_bar=curr_bar,
                    high_price=pivot_high,
                    low_price=pivot_low,
                    direction=direction,
                    quality=StructureQuality.MEDIUM,
                    quality_score=quality_score,
                    session_id=session_id,
                    metadata={
                        'pivot_high': float(pivot_high),
                        'pivot_low': float(pivot_low),
                        'break_strength': float(abs(curr_bar.close - (pivot_high if bullish_bos else pivot_low)))
                    }
                )
                
                structures.append(structure)
                self._last_bos_index = len(bars) - 1
                self._last_bos_direction = direction
                
                logger.debug("bos_detected", extra={
                    "direction": direction,
                    "quality_score": float(quality_score)
                })
        
        return structures
    
    def _validate_parameters(self) -> None:
        """Validate BOS parameters."""
        if self.pivot_window < 2:
            raise ValueError("pivot_window must be >= 2")
        if self.min_break_strength < 0:
            raise ValueError("min_break_strength must be >= 0")
