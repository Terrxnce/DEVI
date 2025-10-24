"""
Unit tests for core models.
"""

import unittest
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from core.models.ohlcv import Bar, OHLCV
from core.models.decision import Decision, DecisionType, DecisionStatus
from core.models.structure import Structure, StructureType, StructureQuality
from core.models.session import Session, SessionType, SessionState


class TestBar(unittest.TestCase):
    """Test Bar model."""
    
    def test_bar_creation(self):
        """Test bar creation and validation."""
        timestamp = datetime.now(timezone.utc)
        bar = Bar(
            open=Decimal('1.1000'),
            high=Decimal('1.1010'),
            low=Decimal('1.0990'),
            close=Decimal('1.1005'),
            volume=Decimal('1000000'),
            timestamp=timestamp
        )
        
        self.assertEqual(bar.open, Decimal('1.1000'))
        self.assertTrue(bar.is_bullish)
        self.assertEqual(bar.body_size, Decimal('0.0005'))
    
    def test_bar_validation(self):
        """Test bar validation."""
        timestamp = datetime.now(timezone.utc)
        
        # Invalid high/low relationship
        with self.assertRaises(ValueError):
            Bar(
                open=Decimal('1.1000'),
                high=Decimal('1.0990'),  # High < open
                low=Decimal('1.1010'),   # Low > high
                close=Decimal('1.1005'),
                volume=Decimal('1000000'),
                timestamp=timestamp
            )


class TestOHLCV(unittest.TestCase):
    """Test OHLCV model."""
    
    def setUp(self):
        """Set up test data."""
        self.bars = []
        timestamp = datetime.now(timezone.utc)
        
        for i in range(5):
            bar = Bar(
                open=Decimal('1.1000') + Decimal(str(i * 0.0001)),
                high=Decimal('1.1010') + Decimal(str(i * 0.0001)),
                low=Decimal('1.0990') + Decimal(str(i * 0.0001)),
                close=Decimal('1.1005') + Decimal(str(i * 0.0001)),
                volume=Decimal('1000000'),
                timestamp=timestamp + timedelta(minutes=15 * i)
            )
            self.bars.append(bar)
    
    def test_ohlcv_creation(self):
        """Test OHLCV creation."""
        ohlcv = OHLCV(
            symbol='EURUSD',
            bars=tuple(self.bars),
            timeframe='15m'
        )
        
        self.assertEqual(ohlcv.symbol, 'EURUSD')
        self.assertEqual(ohlcv.bar_count, 5)
        self.assertEqual(ohlcv.latest_bar, self.bars[-1])


class TestDecision(unittest.TestCase):
    """Test Decision model."""
    
    def test_decision_creation(self):
        """Test decision creation."""
        decision = Decision(
            decision_type=DecisionType.BUY,
            symbol='EURUSD',
            timestamp=datetime.now(timezone.utc),
            session_id='test_session',
            entry_price=Decimal('1.1000'),
            stop_loss=Decimal('1.0990'),
            take_profit=Decimal('1.1020'),
            position_size=Decimal('1000'),
            risk_reward_ratio=Decimal('2.0'),
            structure_id='test_structure',
            confidence_score=Decimal('0.8'),
            reasoning='Test decision',
            metadata={}
        )
        
        self.assertEqual(decision.decision_type, DecisionType.BUY)
        self.assertTrue(decision.is_entry_decision)
        self.assertTrue(decision.is_long)


class TestStructure(unittest.TestCase):
    """Test Structure model."""
    
    def test_structure_creation(self):
        """Test structure creation."""
        timestamp = datetime.now(timezone.utc)
        bar = Bar(
            open=Decimal('1.1000'),
            high=Decimal('1.1010'),
            low=Decimal('1.0990'),
            close=Decimal('1.1005'),
            volume=Decimal('1000000'),
            timestamp=timestamp
        )
        
        structure = Structure(
            structure_id='test_ob',
            structure_type=StructureType.ORDER_BLOCK,
            symbol='EURUSD',
            timeframe='15m',
            start_bar=bar,
            end_bar=bar,
            high_price=Decimal('1.1010'),
            low_price=Decimal('1.0990'),
            quality=StructureQuality.HIGH,
            quality_score=Decimal('0.8'),
            created_timestamp=timestamp,
            session_id='test_session'
        )
        
        self.assertEqual(structure.structure_type, StructureType.ORDER_BLOCK)
        self.assertEqual(structure.price_range, Decimal('0.0020'))


class TestSession(unittest.TestCase):
    """Test Session model."""
    
    def test_session_creation(self):
        """Test session creation."""
        start_time = datetime.now(timezone.utc)
        end_time = start_time + timedelta(hours=8)
        
        session = Session(
            session_id='test_session',
            session_type=SessionType.ASIA,
            symbol='EURUSD',
            start_time=start_time,
            end_time=end_time,
            state=SessionState.ACTIVE,
            symbol_list=['EURUSD', 'GBPUSD'],
            session_params={},
            created_timestamp=start_time,
            last_update_timestamp=start_time
        )
        
        self.assertEqual(session.session_type, SessionType.ASIA)
        self.assertTrue(session.is_active)
        self.assertEqual(session.duration_minutes, 480)


if __name__ == '__main__':
    unittest.main()

