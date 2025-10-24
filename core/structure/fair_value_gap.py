"""Fair Value Gap (FVG) detector."""

import logging
from decimal import Decimal
from typing import List, Dict, Any

from ..models.structure import Structure, StructureType, StructureQuality
from ..models.ohlcv import OHLCV
from ..indicators.atr import compute_atr_simple
from ..utils.numeric import D
from .detector import StructureDetector

logger = logging.getLogger(__name__)


class FairValueGapDetector(StructureDetector):
    """Detects Fair Value Gap structures."""
    
    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        
        # Set attributes BEFORE super().__init__()
        self.min_gap_size = Decimal(str(config.get('min_gap_size', 0.0005)))
        self.max_gap_size = Decimal(str(config.get('max_gap_size', 0.02)))
        self.min_volume_ratio = Decimal(str(config.get('min_volume_ratio', 1.0)))
        self.min_gap_atr_multiplier = Decimal(str(config.get('min_gap_atr_multiplier', 0.15)))
        self.max_age_bars = config.get('max_age_bars', 150)
        self.max_concurrent_zones_per_side = config.get('max_concurrent_zones_per_side', 3)
        self.quality_thresholds = config.get('quality_thresholds', {
            'premium': Decimal('0.8'),
            'high': Decimal('0.6'),
            'medium': Decimal('0.4'),
            'low': Decimal('0.2')
        })
        self.atr_window = config.get('atr_window', 14)
        self.enabled = config.get('enabled', True)
        self.last_detection_index = -999
        self.debounce_bars = config.get('debounce_bars', 3)
        
        # Call super().__init__() AFTER attributes are set
        super().__init__('FairValueGapDetector', StructureType.FAIR_VALUE_GAP, config)
    
    def detect(self, data: OHLCV, session_id: str) -> List[Structure]:
        """Detect Fair Value Gaps in OHLCV data."""
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
        
        # Check for 3-bar FVG pattern
        if len(bars) >= 3:
            self.stats.seen += 1
            
            # Debounce check
            if len(bars) - self.last_detection_index < self.debounce_bars:
                return []
            
            bar1 = bars[-3]
            bar2 = bars[-2]
            bar3 = bars[-1]
            
            # Bullish FVG: bar1 high < bar3 low (gap between bar1 and bar3)
            bullish_gap = bar1.high < bar3.low
            gap_size_bullish = bar3.low - bar1.high if bullish_gap else Decimal(0)
            
            # Bearish FVG: bar1 low > bar3 high (gap between bar1 and bar3)
            bearish_gap = bar1.low > bar3.high
            gap_size_bearish = bar1.low - bar3.high if bearish_gap else Decimal(0)
            
            # Check if gap meets minimum size (now both are Decimal)
            min_gap_threshold = self.min_gap_atr_multiplier * atr
            
            if bullish_gap and gap_size_bullish >= min_gap_threshold:
                self.stats.fired += 1
                quality_score = Decimal(str(min(Decimal('0.95'), Decimal('0.60') + (gap_size_bullish / atr) * Decimal('0.15'))))
                
                structure = self._create_structure(
                    symbol=data.symbol,
                    timeframe=data.timeframe,
                    origin_index=len(bars) - 2,
                    start_bar=bar1,
                    end_bar=bar3,
                    high_price=bar1.high,
                    low_price=bar3.low,
                    direction='bullish',
                    quality=StructureQuality.HIGH,
                    quality_score=quality_score,
                    session_id=session_id,
                    metadata={
                        'gap_size': float(gap_size_bullish),
                        'gap_atr': float(gap_size_bullish / atr),
                        'atr': float(atr)
                    }
                )
                
                structures.append(structure)
                self.last_detection_index = len(bars) - 1
                
                logger.debug("fvg_detected", extra={
                    "direction": "bullish",
                    "gap_size": float(gap_size_bullish),
                    "quality_score": float(quality_score)
                })
            
            if bearish_gap and gap_size_bearish >= min_gap_threshold:
                self.stats.fired += 1
                quality_score = Decimal(str(min(Decimal('0.95'), Decimal('0.60') + (gap_size_bearish / atr) * Decimal('0.15'))))
                
                structure = self._create_structure(
                    symbol=data.symbol,
                    timeframe=data.timeframe,
                    origin_index=len(bars) - 2,
                    start_bar=bar1,
                    end_bar=bar3,
                    high_price=bar3.high,
                    low_price=bar1.low,
                    direction='bearish',
                    quality=StructureQuality.HIGH,
                    quality_score=quality_score,
                    session_id=session_id,
                    metadata={
                        'gap_size': float(gap_size_bearish),
                        'gap_atr': float(gap_size_bearish / atr),
                        'atr': float(atr)
                    }
                )
                
                structures.append(structure)
                self.last_detection_index = len(bars) - 1
                
                logger.debug("fvg_detected", extra={
                    "direction": "bearish",
                    "gap_size": float(gap_size_bearish),
                    "quality_score": float(quality_score)
                })
        
        return structures
    
    def _validate_parameters(self) -> None:
        """Validate FVG parameters."""
        if self.min_gap_size < 0:
            raise ValueError("min_gap_size must be >= 0")
        if self.max_gap_size < self.min_gap_size:
            raise ValueError("max_gap_size must be >= min_gap_size")
