"""Structure detection manager - coordinates all detectors."""

import logging
from typing import List, Dict, Any
from ..models.structure import Structure
from ..models.ohlcv import OHLCV
from .order_block import OrderBlockDetector
from .fair_value_gap import FairValueGapDetector
from .break_of_structure import BreakOfStructureDetector
from .sweep import SweepDetector
from .rejection import UnifiedZoneRejectionDetector
from .engulfing import EngulfingDetector

logger = logging.getLogger(__name__)


class StructureManager:
    """Manages all structure detectors."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.detectors = []
        self._initialize_detectors()
    
    def _initialize_detectors(self):
        """Initialize all enabled detectors."""
        # Order Block detector
        ob_config = self.config.get('order_block', {})
        if ob_config.get('enabled', True):
            self.detectors.append(OrderBlockDetector(ob_config))
        
        # Fair Value Gap detector
        fvg_config = self.config.get('fair_value_gap', {})
        if fvg_config.get('enabled', True):
            self.detectors.append(FairValueGapDetector(fvg_config))
        
        # Break of Structure detector
        bos_config = self.config.get('break_of_structure', {})
        if bos_config.get('enabled', True):
            self.detectors.append(BreakOfStructureDetector(bos_config))
        
        # Sweep detector
        sweep_config = self.config.get('sweep', {})
        if sweep_config.get('enabled', True):
            self.detectors.append(SweepDetector(sweep_config))
        
        # Unified Zone Rejection detector
        uzr_config = self.config.get('unified_zone_rejection', {})
        if uzr_config.get('enabled', True):
            self.detectors.append(UnifiedZoneRejectionDetector(uzr_config))
        
        # Engulfing detector
        engulfing_config = self.config.get('engulfing', {})
        if engulfing_config.get('enabled', True):
            self.detectors.append(EngulfingDetector(engulfing_config))
        
        # Validate no duplicates
        names = [d.name for d in self.detectors]
        assert len(names) == len(set(names)), f"Duplicate detectors: {names}"
        logger.info(f"Initialized {len(self.detectors)} detectors: {names}")
    
    def detect_structures(self, data: OHLCV, session_id: str) -> List[Structure]:
        """Detect all structures in OHLCV data."""
        all_structures = []
        
        for detector in self.detectors:
            try:
                structures = detector.detect(data, session_id)
                all_structures.extend(structures)
            except Exception as e:
                logger.warning(f"Error in detector {detector.__class__.__name__}: {e}")
        
        return all_structures
    
    def get_detector_summary(self) -> dict:
        """Get summary of detector activity."""
        summary = {}
        for detector in self.detectors:
            detector_name = detector.__class__.__name__
            summary[detector_name] = {
                "class": detector_name,
                "enabled": getattr(detector, 'enabled', True),
                "seen": detector.stats.seen,
                "fired": detector.stats.fired
            }
        
        # Log summary
        for name, stats in summary.items():
            logger.info(f"detector_summary {name} seen={stats['seen']} fired={stats['fired']}")
        
        return summary
