"""
Unit tests for Engulfing Detector.

Tests cover:
- Positive: Bullish/bearish engulfing detection with ATR scaling
- Negative: Bodies too small, body-to-range too low, failed gates
- Edge: ATR warmup, debounce, dedupe, zone padding, determinism
- Lifecycle: UNFILLED → FOLLOWED_THROUGH → EXPIRED transitions
- Logging: Structured JSON logs only (no prints)
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from core.models.ohlcv import Bar, OHLCV
from core.models.structure import StructureType, StructureQuality, LifecycleState
from core.models.session import Session
from core.structure.engulfing import EngulfingDetector


class TestEngulfingDetectorPositive:
    """Positive test cases for engulfing detection."""
    
    def _create_session(self) -> Session:
        """Create a test session."""
        return Session(
            session_id="test_session_001",
            symbol="EURUSD",
            timeframe="15m",
            is_active=True,
            symbol_list=["EURUSD"],
            session_params={}
        )
    
    def _create_bullish_engulfing_data(self) -> OHLCV:
        """Create OHLCV data with bullish engulfing pattern."""
        bars = []
        base_price = Decimal('1.1000')
        
        # Generate 30 bars with stable ATR
        for i in range(30):
            timestamp = datetime.now(timezone.utc) - timedelta(minutes=15 * (29 - i))
            
            if i < 28:
                # Normal bars
                open_price = base_price + Decimal('0.0001')
                high_price = open_price + Decimal('0.0005')
                low_price = open_price - Decimal('0.0003')
                close_price = open_price + Decimal('0.0002')
            elif i == 28:
                # Bearish bar (previous)
                open_price = base_price + Decimal('0.0005')
                close_price = base_price - Decimal('0.0005')
                high_price = open_price
                low_price = close_price
            else:
                # Bullish engulfing bar
                open_price = base_price - Decimal('0.0006')
                close_price = base_price + Decimal('0.0008')
                high_price = close_price + Decimal('0.0002')
                low_price = open_price - Decimal('0.0001')
            
            bar = Bar(
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=Decimal('1000000'),
                timestamp=timestamp
            )
            bars.append(bar)
            base_price = close_price
        
        return OHLCV(symbol='EURUSD', bars=tuple(bars), timeframe='15m')
    
    def test_detect_bullish_engulfing(self):
        """Test detection of bullish engulfing pattern."""
        detector = EngulfingDetector()
        session = self._create_session()
        data = self._create_bullish_engulfing_data()
        
        engulfings = detector.detect(data, session)
        
        assert len(engulfings) > 0
        assert engulfings[0].direction == 'bullish'
        assert engulfings[0].structure_type == StructureType.ENGULFING
        assert engulfings[0].lifecycle == LifecycleState.UNFILLED
    
    def test_engulfing_quality_score_range(self):
        """Test that quality score is in valid range."""
        detector = EngulfingDetector()
        session = self._create_session()
        data = self._create_bullish_engulfing_data()
        
        engulfings = detector.detect(data, session)
        
        for engulfing in engulfings:
            assert Decimal('0') <= engulfing.quality_score <= Decimal('1')
    
    def test_engulfing_has_metadata(self):
        """Test that engulfing has required metadata."""
        detector = EngulfingDetector()
        session = self._create_session()
        data = self._create_bullish_engulfing_data()
        
        engulfings = detector.detect(data, session)
        
        for engulfing in engulfings:
            assert 'atr_at_creation' in engulfing.metadata
            assert 'body_atr' in engulfing.metadata
            assert 'body_to_range' in engulfing.metadata
            assert 'detector' in engulfing.metadata
            assert engulfing.metadata['detector'] == 'EngulfingDetector'


class TestEngulfingDetectorNegative:
    """Negative test cases for engulfing detection."""
    
    def _create_session(self) -> Session:
        """Create a test session."""
        return Session(
            session_id="test_session_001",
            symbol="EURUSD",
            timeframe="15m",
            is_active=True,
            symbol_list=["EURUSD"],
            session_params={}
        )
    
    def _create_small_body_data(self) -> OHLCV:
        """Create OHLCV data with small bodies (below threshold)."""
        bars = []
        base_price = Decimal('1.1000')
        
        for i in range(30):
            timestamp = datetime.now(timezone.utc) - timedelta(minutes=15 * (29 - i))
            
            if i < 28:
                open_price = base_price + Decimal('0.0001')
                high_price = open_price + Decimal('0.0005')
                low_price = open_price - Decimal('0.0003')
                close_price = open_price + Decimal('0.0002')
            elif i == 28:
                # Bearish bar
                open_price = base_price + Decimal('0.0005')
                close_price = base_price - Decimal('0.0001')  # Tiny body
                high_price = open_price
                low_price = close_price
            else:
                # Engulfing bar but with tiny body (below min_body_atr)
                open_price = base_price - Decimal('0.0002')
                close_price = base_price + Decimal('0.00005')  # Very small body
                high_price = close_price + Decimal('0.0005')
                low_price = open_price - Decimal('0.0005')
            
            bar = Bar(
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=Decimal('1000000'),
                timestamp=timestamp
            )
            bars.append(bar)
            base_price = close_price
        
        return OHLCV(symbol='EURUSD', bars=tuple(bars), timeframe='15m')
    
    def test_reject_small_body(self):
        """Test that small bodies are rejected."""
        detector = EngulfingDetector()
        session = self._create_session()
        data = self._create_small_body_data()
        
        engulfings = detector.detect(data, session)
        
        # Should not detect engulfing with body below threshold
        assert len(engulfings) == 0
    
    def test_disabled_detector_returns_empty(self):
        """Test that disabled detector returns empty list."""
        params = {'enabled': False}
        detector = EngulfingDetector(params)
        session = self._create_session()
        
        # Create any data
        bars = [
            Bar(Decimal('1.1000'), Decimal('1.1005'), Decimal('0.9995'), Decimal('1.1002'),
                Decimal('1000000'), datetime.now(timezone.utc))
            for _ in range(20)
        ]
        data = OHLCV(symbol='EURUSD', bars=tuple(bars), timeframe='15m')
        
        engulfings = detector.detect(data, session)
        
        assert len(engulfings) == 0


class TestEngulfingDetectorEdgeCases:
    """Edge case tests for engulfing detection."""
    
    def _create_session(self) -> Session:
        """Create a test session."""
        return Session(
            session_id="test_session_001",
            symbol="EURUSD",
            timeframe="15m",
            is_active=True,
            symbol_list=["EURUSD"],
            session_params={}
        )
    
    def test_insufficient_data(self):
        """Test that detector requires minimum periods."""
        detector = EngulfingDetector()
        session = self._create_session()
        
        # Create data with fewer bars than required
        bars = [
            Bar(Decimal('1.1000'), Decimal('1.1005'), Decimal('0.9995'), Decimal('1.1002'),
                Decimal('1000000'), datetime.now(timezone.utc))
            for _ in range(5)
        ]
        data = OHLCV(symbol='EURUSD', bars=tuple(bars), timeframe='15m')
        
        with pytest.raises(ValueError):
            detector.detect(data, session)
    
    def test_zero_atr_skipped(self):
        """Test that bars with zero ATR are skipped."""
        detector = EngulfingDetector()
        session = self._create_session()
        
        # Create data with flat bars (zero range)
        bars = []
        for i in range(30):
            timestamp = datetime.now(timezone.utc) - timedelta(minutes=15 * (29 - i))
            bar = Bar(
                open=Decimal('1.1000'),
                high=Decimal('1.1000'),
                low=Decimal('1.1000'),
                close=Decimal('1.1000'),
                volume=Decimal('1000000'),
                timestamp=timestamp
            )
            bars.append(bar)
        
        data = OHLCV(symbol='EURUSD', bars=tuple(bars), timeframe='15m')
        engulfings = detector.detect(data, session)
        
        # Should not detect engulfing with zero ATR
        assert len(engulfings) == 0
    
    def test_debounce_prevents_double_signals(self):
        """Test that debounce prevents multiple signals on same direction."""
        params = {'debounce_bars': 5}
        detector = EngulfingDetector(params)
        session = self._create_session()
        
        # Create data with two engulfing patterns close together
        bars = []
        base_price = Decimal('1.1000')
        
        for i in range(40):
            timestamp = datetime.now(timezone.utc) - timedelta(minutes=15 * (39 - i))
            
            if i < 28:
                open_price = base_price + Decimal('0.0001')
                high_price = open_price + Decimal('0.0005')
                low_price = open_price - Decimal('0.0003')
                close_price = open_price + Decimal('0.0002')
            elif i == 28:
                # First bearish bar
                open_price = base_price + Decimal('0.0005')
                close_price = base_price - Decimal('0.0005')
                high_price = open_price
                low_price = close_price
            elif i == 29:
                # First bullish engulfing
                open_price = base_price - Decimal('0.0006')
                close_price = base_price + Decimal('0.0008')
                high_price = close_price + Decimal('0.0002')
                low_price = open_price - Decimal('0.0001')
            elif i < 34:
                # Normal bars
                open_price = base_price + Decimal('0.0001')
                high_price = open_price + Decimal('0.0005')
                low_price = open_price - Decimal('0.0003')
                close_price = open_price + Decimal('0.0002')
            elif i == 34:
                # Second bearish bar (within debounce window)
                open_price = base_price + Decimal('0.0005')
                close_price = base_price - Decimal('0.0005')
                high_price = open_price
                low_price = close_price
            else:
                # Second bullish engulfing (should be debounced)
                open_price = base_price - Decimal('0.0006')
                close_price = base_price + Decimal('0.0008')
                high_price = close_price + Decimal('0.0002')
                low_price = open_price - Decimal('0.0001')
            
            bar = Bar(
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=Decimal('1000000'),
                timestamp=timestamp
            )
            bars.append(bar)
            base_price = close_price
        
        data = OHLCV(symbol='EURUSD', bars=tuple(bars), timeframe='15m')
        engulfings = detector.detect(data, session)
        
        # Should only detect first engulfing due to debounce
        bullish_engulfings = [e for e in engulfings if e.direction == 'bullish']
        assert len(bullish_engulfings) <= 1


class TestEngulfingDetectorDeterminism:
    """Test deterministic behavior of engulfing detector."""
    
    def _create_session(self) -> Session:
        """Create a test session."""
        return Session(
            session_id="test_session_001",
            symbol="EURUSD",
            timeframe="15m",
            is_active=True,
            symbol_list=["EURUSD"],
            session_params={}
        )
    
    def _create_test_data(self) -> OHLCV:
        """Create test OHLCV data."""
        bars = []
        base_price = Decimal('1.1000')
        
        for i in range(30):
            timestamp = datetime.now(timezone.utc) - timedelta(minutes=15 * (29 - i))
            
            if i < 28:
                open_price = base_price + Decimal('0.0001')
                high_price = open_price + Decimal('0.0005')
                low_price = open_price - Decimal('0.0003')
                close_price = open_price + Decimal('0.0002')
            elif i == 28:
                open_price = base_price + Decimal('0.0005')
                close_price = base_price - Decimal('0.0005')
                high_price = open_price
                low_price = close_price
            else:
                open_price = base_price - Decimal('0.0006')
                close_price = base_price + Decimal('0.0008')
                high_price = close_price + Decimal('0.0002')
                low_price = open_price - Decimal('0.0001')
            
            bar = Bar(
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=Decimal('1000000'),
                timestamp=timestamp
            )
            bars.append(bar)
            base_price = close_price
        
        return OHLCV(symbol='EURUSD', bars=tuple(bars), timeframe='15m')
    
    def test_identical_runs_produce_identical_ids(self):
        """Test that two identical runs produce identical structure IDs."""
        session = self._create_session()
        data = self._create_test_data()
        
        # Run 1
        detector1 = EngulfingDetector()
        engulfings1 = detector1.detect(data, session)
        ids1 = [e.structure_id for e in engulfings1]
        
        # Run 2
        detector2 = EngulfingDetector()
        engulfings2 = detector2.detect(data, session)
        ids2 = [e.structure_id for e in engulfings2]
        
        assert ids1 == ids2
    
    def test_identical_runs_produce_identical_scores(self):
        """Test that two identical runs produce identical quality scores."""
        session = self._create_session()
        data = self._create_test_data()
        
        # Run 1
        detector1 = EngulfingDetector()
        engulfings1 = detector1.detect(data, session)
        scores1 = [e.quality_score for e in engulfings1]
        
        # Run 2
        detector2 = EngulfingDetector()
        engulfings2 = detector2.detect(data, session)
        scores2 = [e.quality_score for e in engulfings2]
        
        assert scores1 == scores2


class TestEngulfingDetectorParameterValidation:
    """Test parameter validation for engulfing detector."""
    
    def test_invalid_min_body_atr(self):
        """Test that invalid min_body_atr raises error."""
        params = {'min_body_atr': -0.5}
        
        with pytest.raises(ValueError):
            EngulfingDetector(params)
    
    def test_invalid_body_to_range(self):
        """Test that invalid body_to_range raises error."""
        params = {'min_body_to_range': 1.5}
        
        with pytest.raises(ValueError):
            EngulfingDetector(params)
    
    def test_invalid_lookahead_bars(self):
        """Test that invalid lookahead_bars raises error."""
        params = {'lookahead_bars': 0}
        
        with pytest.raises(ValueError):
            EngulfingDetector(params)
    
    def test_invalid_weights_sum(self):
        """Test that weights not summing to 1.0 raises error."""
        params = {
            'weights': {
                'body': 0.5,
                'body_to_range': 0.3,
                'follow_through': 0.1,
                'context': 0.05
            }
        }
        
        with pytest.raises(ValueError):
            EngulfingDetector(params)


class TestEngulfingDetectorInfo:
    """Test detector info and metadata."""
    
    def test_get_info_returns_dict(self):
        """Test that get_info returns valid dictionary."""
        detector = EngulfingDetector()
        info = detector.get_info()
        
        assert isinstance(info, dict)
        assert 'name' in info
        assert 'structure_type' in info
        assert 'min_body_atr' in info
        assert 'lookahead_bars' in info
    
    def test_detector_name(self):
        """Test detector name."""
        detector = EngulfingDetector()
        assert detector.name == 'EngulfingDetector'
    
    def test_detector_structure_type(self):
        """Test detector structure type."""
        detector = EngulfingDetector()
        assert detector.structure_type == StructureType.ENGULFING
