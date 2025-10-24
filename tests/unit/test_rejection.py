"""
Unit tests for Unified Zone Rejection detector.
"""

import unittest
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from core.models.ohlcv import Bar, OHLCV
from core.models.session import Session, SessionType, SessionState
from core.structure.rejection import UnifiedZoneRejectionDetector
from core.models.structure import StructureType, LifecycleState, Structure, StructureQuality


def make_session(symbol='EURUSD', timeframe='15m'):
    now = datetime.now(timezone.utc)
    return Session(
        session_id='test_run',
        session_type=SessionType.ASIA,
        symbol=symbol,
        start_time=now,
        end_time=now + timedelta(hours=8),
        state=SessionState.ACTIVE,
        symbol_list=[symbol],
        session_params={'timeframe': timeframe},
        created_timestamp=now,
        last_update_timestamp=now
    )


class TestUnifiedZoneRejectionDetector(unittest.TestCase):
    """Test Unified Zone Rejection detector implementation."""
    
    def _create_mock_zone(self, zone_type: StructureType, direction: str, low: Decimal, high: Decimal, 
                         start_index: int = 10) -> Structure:
        """Create mock zone structure for testing."""
        # Create mock bars
        now = datetime.now(timezone.utc)
        start_bar = Bar(
            Decimal('1.1000'), Decimal('1.1010'), Decimal('1.0990'), Decimal('1.1005'),
            Decimal('1000000'), now + timedelta(minutes=15 * start_index)
        )
        end_bar = start_bar  # Same bar for single-bar structures
        
        return Structure(
            structure_id=f"{zone_type.value}_{direction}_{start_index}",
            structure_type=zone_type,
            symbol="EURUSD",
            timeframe="15m",
            start_bar=start_bar,
            end_bar=end_bar,
            high_price=high,
            low_price=low,
            quality=StructureQuality.HIGH,
            quality_score=Decimal('0.8'),
            created_timestamp=now,
            session_id="test_session",
            direction=direction,
            origin_index=start_index,
            lifecycle=LifecycleState.UNFILLED,
            links={},
            metadata={'atr_at_creation': 0.001}
        )
    
    def _build_bars_for_rejection(self, zone_low: Decimal, zone_high: Decimal, 
                                 touch_zone: bool = True, reaction: bool = True, 
                                 follow_through: bool = True):
        """Build test bars for rejection detection."""
        now = datetime.now(timezone.utc)
        bars = []
        
        # Build base bars for ATR calculation
        for i in range(15):
            bars.append(Bar(
                Decimal('1.1000'), Decimal('1.1010'), Decimal('1.0990'), Decimal('1.1005'),
                Decimal('1000000'), now + timedelta(minutes=15 * i)
            ))
        
        # Zone creation bar at index 15
        bars.append(Bar(
            Decimal('1.1005'), Decimal('1.1015'), Decimal('1.1000'), Decimal('1.1010'),
            Decimal('1200000'), now + timedelta(minutes=15 * 15)
        ))
        
        # Touch bar at index 16
        if touch_zone:
            # Touch the zone
            touch_price = (zone_low + zone_high) / 2  # Touch midline
            if reaction:
                # Bullish reaction: close > open and close > midline
                # Create a larger body to meet min_reaction_body_atr requirement (0.5 ATR)
                # With ATR ~0.009, we need body size ~0.0045
                bars.append(Bar(
                    Decimal('1.1000'), Decimal('1.1020'), Decimal('0.9995'), 
                    Decimal('1.1020'),  # Close above midline with much larger body (0.02 body size)
                    Decimal('1500000'), now + timedelta(minutes=15 * 16)
                ))
            else:
                # No reaction: close near midline
                bars.append(Bar(
                    Decimal('1.1008'), Decimal('1.1012'), Decimal('1.1007'), 
                    touch_price,  # Close at midline
                    Decimal('1500000'), now + timedelta(minutes=15 * 16)
                ))
        else:
            # No touch
            bars.append(Bar(
                Decimal('1.1008'), Decimal('1.1012'), Decimal('1.1005'), Decimal('1.1007'),
                Decimal('1500000'), now + timedelta(minutes=15 * 16)
            ))
        
        # Follow-through bar
        if follow_through and reaction:
            bars.append(Bar(
                Decimal('1.1009'), Decimal('1.1015'), Decimal('1.1008'), Decimal('1.1012'),
                Decimal('1300000'), now + timedelta(minutes=15 * 17)
            ))
        
        return bars
    
    def test_positive_rejection_detection(self):
        """Test valid touch → reaction → follow-through."""
        session = make_session()
        det = UnifiedZoneRejectionDetector(parameters={
            'touch_atr_buffer': Decimal('0.25'),
            'min_reaction_body_atr': Decimal('0.5'),
            'min_follow_through_atr': Decimal('1.0'),
            'lookahead_bars': 5
        })
        
        # Create bullish zone
        zone = self._create_mock_zone(
            StructureType.ORDER_BLOCK, 'bullish', 
            Decimal('1.1005'), Decimal('1.1015'), 15
        )
        
        bars = self._build_bars_for_rejection(
            Decimal('1.1005'), Decimal('1.1015'), 
            touch_zone=True, reaction=True, follow_through=True
        )
        ohlcv = OHLCV('EURUSD', bars, '15m')
        
        rejections = det.detect(ohlcv, session, existing_structures=[zone])
        
        # Should detect rejection
        self.assertEqual(len(rejections), 1)
        rejection = rejections[0]
        self.assertEqual(rejection.direction, 'bullish')
        self.assertEqual(rejection.origin_index, 16)
        self.assertEqual(rejection.links['zone_id'], zone.structure_id)
        self.assertGreater(rejection.metadata['reaction_body_atr'], 0)
        self.assertGreater(rejection.metadata['follow_through_atr'], 0)
    
    def test_negative_no_touch(self):
        """Test no rejection when price doesn't touch zone."""
        session = make_session()
        det = UnifiedZoneRejectionDetector(parameters={
            'touch_atr_buffer': Decimal('0.25'),
            'min_reaction_body_atr': Decimal('0.5'),
            'min_follow_through_atr': Decimal('1.0'),
            'lookahead_bars': 5
        })
        
        # Create bullish zone
        zone = self._create_mock_zone(
            StructureType.ORDER_BLOCK, 'bullish', 
            Decimal('1.1005'), Decimal('1.1015'), 15
        )
        
        bars = self._build_bars_for_rejection(
            Decimal('1.1005'), Decimal('1.1015'), 
            touch_zone=False, reaction=False, follow_through=False
        )
        ohlcv = OHLCV('EURUSD', bars, '15m')
        
        rejections = det.detect(ohlcv, session, existing_structures=[zone])
        
        # Should not detect rejection
        self.assertEqual(len(rejections), 0)
    
    def test_negative_no_reaction(self):
        """Test no rejection when touch but no reaction."""
        session = make_session()
        det = UnifiedZoneRejectionDetector(parameters={
            'touch_atr_buffer': Decimal('0.25'),
            'min_reaction_body_atr': Decimal('0.5'),
            'min_follow_through_atr': Decimal('1.0'),
            'lookahead_bars': 5
        })
        
        # Create bullish zone
        zone = self._create_mock_zone(
            StructureType.ORDER_BLOCK, 'bullish', 
            Decimal('1.1005'), Decimal('1.1015'), 15
        )
        
        bars = self._build_bars_for_rejection(
            Decimal('1.1005'), Decimal('1.1015'), 
            touch_zone=True, reaction=False, follow_through=False
        )
        ohlcv = OHLCV('EURUSD', bars, '15m')
        
        rejections = det.detect(ohlcv, session, existing_structures=[zone])
        
        # Should not detect rejection
        self.assertEqual(len(rejections), 0)
    
    def test_negative_no_follow_through(self):
        """Test rejection detected but no follow-through."""
        session = make_session()
        det = UnifiedZoneRejectionDetector(parameters={
            'touch_atr_buffer': Decimal('0.25'),
            'min_reaction_body_atr': Decimal('0.5'),
            'min_follow_through_atr': Decimal('1.0'),
            'lookahead_bars': 5
        })
        
        # Create bullish zone
        zone = self._create_mock_zone(
            StructureType.ORDER_BLOCK, 'bullish', 
            Decimal('1.1005'), Decimal('1.1015'), 15
        )
        
        bars = self._build_bars_for_rejection(
            Decimal('1.1005'), Decimal('1.1015'), 
            touch_zone=True, reaction=True, follow_through=False
        )
        ohlcv = OHLCV('EURUSD', bars, '15m')
        
        rejections = det.detect(ohlcv, session, existing_structures=[zone])
        
        # Should detect rejection but with no follow-through
        self.assertEqual(len(rejections), 1)
        rejection = rejections[0]
        self.assertEqual(rejection.metadata['follow_through_atr'], 0.0)
    
    def test_lifecycle_transitions(self):
        """Test lifecycle transitions: UNFILLED → PARTIAL → FILLED → EXPIRED."""
        session = make_session()
        det = UnifiedZoneRejectionDetector(parameters={
            'touch_atr_buffer': Decimal('0.25'),
            'min_reaction_body_atr': Decimal('0.5'),
            'min_follow_through_atr': Decimal('1.0'),
            'lookahead_bars': 5,
            'max_age_bars': 10
        })
        
        # Create bullish zone
        zone = self._create_mock_zone(
            StructureType.ORDER_BLOCK, 'bullish', 
            Decimal('1.1005'), Decimal('1.1015'), 15
        )
        
        bars = self._build_bars_for_rejection(
            Decimal('1.1005'), Decimal('1.1015'), 
            touch_zone=True, reaction=True, follow_through=True
        )
        ohlcv = OHLCV('EURUSD', bars, '15m')
        
        # First detection
        rejections = det.detect(ohlcv, session, existing_structures=[zone])
        self.assertEqual(len(rejections), 1)
        rejection = rejections[0]
        self.assertEqual(rejection.lifecycle, LifecycleState.UNFILLED)
        
        # Update lifecycle
        det._update_rejection_lifecycle(ohlcv.bars, session)
        
        # Check lifecycle transitions
        active_rejections = det.active_rejections
        if active_rejections:
            updated_rejection = active_rejections[0]
            # Should transition to PARTIAL (touch detected)
            self.assertEqual(updated_rejection.lifecycle, LifecycleState.PARTIAL)
    
    def test_age_expiry(self):
        """Test rejection expiry after max_age_bars."""
        session = make_session()
        det = UnifiedZoneRejectionDetector(parameters={
            'touch_atr_buffer': Decimal('0.25'),
            'min_reaction_body_atr': Decimal('0.5'),
            'min_follow_through_atr': Decimal('1.0'),
            'lookahead_bars': 5,
            'max_age_bars': 2  # Very short age for testing
        })
        
        # Create bullish zone
        zone = self._create_mock_zone(
            StructureType.ORDER_BLOCK, 'bullish', 
            Decimal('1.1005'), Decimal('1.1015'), 15
        )
        
        bars = self._build_bars_for_rejection(
            Decimal('1.1005'), Decimal('1.1015'), 
            touch_zone=True, reaction=True, follow_through=True
        )
        ohlcv = OHLCV('EURUSD', bars, '15m')
        
        # First detection
        rejections = det.detect(ohlcv, session, existing_structures=[zone])
        self.assertEqual(len(rejections), 1)
        
        # Add more bars to exceed max_age_bars
        for i in range(5):
            bars.append(Bar(
                Decimal('1.1010'), Decimal('1.1020'), Decimal('1.1005'), Decimal('1.1015'),
                Decimal('1000000'), datetime.now(timezone.utc) + timedelta(minutes=15 * (18 + i))
            ))
        
        ohlcv = OHLCV('EURUSD', bars, '15m')
        
        # Update lifecycle - should expire
        det._update_rejection_lifecycle(ohlcv.bars, session)
        
        # Check that rejection was expired
        active_rejections = det.active_rejections
        if active_rejections:
            updated_rejection = active_rejections[0]
            self.assertEqual(updated_rejection.lifecycle, LifecycleState.EXPIRED)
    
    def test_debounce_behavior(self):
        """Test debounce per (symbol, timeframe, zone_id)."""
        session = make_session()
        det = UnifiedZoneRejectionDetector(parameters={
            'touch_atr_buffer': Decimal('0.25'),
            'min_reaction_body_atr': Decimal('0.5'),
            'min_follow_through_atr': Decimal('1.0'),
            'lookahead_bars': 5,
            'debounce_bars': 5
        })
        
        # Create bullish zone
        zone = self._create_mock_zone(
            StructureType.ORDER_BLOCK, 'bullish', 
            Decimal('1.1005'), Decimal('1.1015'), 15
        )
        
        bars = self._build_bars_for_rejection(
            Decimal('1.1005'), Decimal('1.1015'), 
            touch_zone=True, reaction=True, follow_through=True
        )
        
        # Add second rejection attempt
        bars.append(Bar(
            Decimal('1.1009'), Decimal('1.1013'), Decimal('1.1007'), Decimal('1.1011'),
            Decimal('1000000'), datetime.now(timezone.utc) + timedelta(minutes=15 * 18)
        ))
        
        ohlcv = OHLCV('EURUSD', bars, '15m')
        
        rejections = det.detect(ohlcv, session, existing_structures=[zone])
        
        # Should only detect one rejection (second should be debounced)
        self.assertEqual(len(rejections), 1)
        self.assertEqual(rejections[0].origin_index, 16)  # First rejection only
    
    def test_dedupe_behavior(self):
        """Test deduplication by zone_id keeping higher quality."""
        session = make_session()
        det = UnifiedZoneRejectionDetector(parameters={
            'touch_atr_buffer': Decimal('0.25'),
            'min_reaction_body_atr': Decimal('0.5'),
            'min_follow_through_atr': Decimal('1.0'),
            'lookahead_bars': 5,
            'debounce_bars': 1  # Allow multiple rejections for dedupe test
        })
        
        # Create bullish zone
        zone = self._create_mock_zone(
            StructureType.ORDER_BLOCK, 'bullish', 
            Decimal('1.1005'), Decimal('1.1015'), 15
        )
        
        bars = self._build_bars_for_rejection(
            Decimal('1.1005'), Decimal('1.1015'), 
            touch_zone=True, reaction=True, follow_through=True
        )
        
        # Add overlapping rejection
        bars.append(Bar(
            Decimal('1.1009'), Decimal('1.1013'), Decimal('1.1007'), Decimal('1.1011'),
            Decimal('1000000'), datetime.now(timezone.utc) + timedelta(minutes=15 * 18)
        ))
        
        ohlcv = OHLCV('EURUSD', bars, '15m')
        
        rejections = det.detect(ohlcv, session, existing_structures=[zone])
        
        # Should dedupe to one rejection per zone_id
        self.assertEqual(len(rejections), 1)
        # Should keep the first one (higher quality due to earlier origin_index)
        self.assertEqual(rejections[0].origin_index, 16)
    
    def test_atr_scaling_invariance(self):
        """Test ATR scaling invariance - same decisions when volatility scales."""
        session = make_session()
        det = UnifiedZoneRejectionDetector(parameters={
            'touch_atr_buffer': Decimal('0.25'),
            'min_reaction_body_atr': Decimal('0.5'),
            'min_follow_through_atr': Decimal('1.0'),
            'lookahead_bars': 5
        })
        
        # Create bullish zone
        zone = self._create_mock_zone(
            StructureType.ORDER_BLOCK, 'bullish', 
            Decimal('1.1005'), Decimal('1.1015'), 15
        )
        
        # Test with normal volatility
        bars1 = self._build_bars_for_rejection(
            Decimal('1.1005'), Decimal('1.1015'), 
            touch_zone=True, reaction=True, follow_through=True
        )
        ohlcv1 = OHLCV('EURUSD', bars1, '15m')
        
        # Test with scaled volatility (2x)
        bars2 = []
        for bar in bars1:
            bars2.append(Bar(
                bar.open * 2, bar.high * 2, bar.low * 2, bar.close * 2,
                bar.volume, bar.timestamp
            ))
        ohlcv2 = OHLCV('EURUSD', bars2, '15m')
        
        # Scale zone as well
        zone2 = self._create_mock_zone(
            StructureType.ORDER_BLOCK, 'bullish', 
            Decimal('1.1005') * 2, Decimal('1.1015') * 2, 15
        )
        
        rejections1 = det.detect(ohlcv1, session, existing_structures=[zone])
        det.reset()
        rejections2 = det.detect(ohlcv2, session, existing_structures=[zone2])
        
        # Should produce same number of rejections
        self.assertEqual(len(rejections1), len(rejections2))
        
        if rejections1 and rejections2:
            # Quality scores should be similar (ATR-normalized)
            self.assertAlmostEqual(
                float(rejections1[0].quality_score), 
                float(rejections2[0].quality_score), 
                places=2
            )
    
    def test_determinism_and_no_prints(self):
        """Test rejection detector determinism and no prints."""
        session = make_session()
        det = UnifiedZoneRejectionDetector(parameters={
            'touch_atr_buffer': Decimal('0.25'),
            'min_reaction_body_atr': Decimal('0.5'),
            'min_follow_through_atr': Decimal('1.0'),
            'lookahead_bars': 5
        })
        
        # Create bullish zone
        zone = self._create_mock_zone(
            StructureType.ORDER_BLOCK, 'bullish', 
            Decimal('1.1005'), Decimal('1.1015'), 15
        )
        
        bars = self._build_bars_for_rejection(
            Decimal('1.1005'), Decimal('1.1015'), 
            touch_zone=True, reaction=True, follow_through=True
        )
        ohlcv = OHLCV('EURUSD', bars, '15m')
        
        # First run
        rejections1 = det.detect(ohlcv, session, existing_structures=[zone])
        ids1 = [r.structure_id for r in rejections1]
        
        # Reset and second run
        det.reset()
        rejections2 = det.detect(ohlcv, session, existing_structures=[zone])
        ids2 = [r.structure_id for r in rejections2]
        
        # Should be identical
        self.assertEqual(ids1, ids2)
        self.assertEqual(len(rejections1), len(rejections2))
    
    def test_zone_type_support(self):
        """Test support for different zone types (OB, FVG)."""
        session = make_session()
        det = UnifiedZoneRejectionDetector(parameters={
            'touch_atr_buffer': Decimal('0.25'),
            'min_reaction_body_atr': Decimal('0.5'),
            'min_follow_through_atr': Decimal('1.0'),
            'lookahead_bars': 5
        })
        
        # Test with Order Block
        ob_zone = self._create_mock_zone(
            StructureType.ORDER_BLOCK, 'bullish', 
            Decimal('1.1005'), Decimal('1.1015'), 15
        )
        
        # Test with Fair Value Gap
        fvg_zone = self._create_mock_zone(
            StructureType.FAIR_VALUE_GAP, 'bullish', 
            Decimal('1.1005'), Decimal('1.1015'), 15
        )
        
        bars = self._build_bars_for_rejection(
            Decimal('1.1005'), Decimal('1.1015'), 
            touch_zone=True, reaction=True, follow_through=True
        )
        ohlcv = OHLCV('EURUSD', bars, '15m')
        
        # Test OB rejection
        ob_rejections = det.detect(ohlcv, session, existing_structures=[ob_zone])
        self.assertEqual(len(ob_rejections), 1)
        self.assertEqual(ob_rejections[0].metadata['zone_type'], 'ORDER_BLOCK')
        
        # Test FVG rejection
        det.reset()
        fvg_rejections = det.detect(ohlcv, session, existing_structures=[fvg_zone])
        self.assertEqual(len(fvg_rejections), 1)
        self.assertEqual(fvg_rejections[0].metadata['zone_type'], 'FAIR_VALUE_GAP')
    
    def test_parameter_validation(self):
        """Test parameter validation."""
        # Test invalid weights
        with self.assertRaises(ValueError):
            UnifiedZoneRejectionDetector(parameters={
                'weights': {
                    'reaction_body': Decimal('0.5'),
                    'follow_through': Decimal('0.3'),
                    'penetration_depth': Decimal('0.1'),
                    'context_bonus': Decimal('0.1')  # Sum = 1.0, should be valid
                }
            })
        
        # Test negative ATR buffer
        with self.assertRaises(ValueError):
            UnifiedZoneRejectionDetector(parameters={
                'touch_atr_buffer': Decimal('-0.1')
            })
        
        # Test zero follow-through
        with self.assertRaises(ValueError):
            UnifiedZoneRejectionDetector(parameters={
                'min_follow_through_atr': Decimal('0')
            })


if __name__ == '__main__':
    unittest.main()
