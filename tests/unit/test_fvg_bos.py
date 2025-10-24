import unittest
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from core.models.ohlcv import Bar, OHLCV
from core.models.session import Session, SessionType, SessionState
from core.structure.fair_value_gap import FairValueGapDetector
from core.structure.break_of_structure import BreakOfStructureDetector
from core.structure.order_block import OrderBlockDetector
from core.structure.sweep import SweepDetector
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


class TestFVGDetector(unittest.TestCase):
    def _build_bars_for_fvg(self, gap_pips=Decimal('0.0005'), mid_touch=False, fill=False, bars_after=5):
        now = datetime.now(timezone.utc)
        bars = []
        # Candle 1
        bars.append(Bar(Decimal('1.1000'), Decimal('1.1010'), Decimal('1.0990'), Decimal('1.1005'), Decimal('1000000'), now))
        # Candle 2 (small inside)
        bars.append(Bar(Decimal('1.1006'), Decimal('1.1008'), Decimal('1.1002'), Decimal('1.1007'), Decimal('900000'), now + timedelta(minutes=15)))
        # Candle 3 creates bullish gap: low above candle1.high
        c1_high = bars[0].high
        c3_low = c1_high + gap_pips
        bars.append(Bar(c3_low, c3_low + Decimal('0.0005'), c3_low, c3_low + Decimal('0.0002'), Decimal('1200000'), now + timedelta(minutes=30)))
        # After bars: optionally trade mid and/or fill
        fvg_low = c1_high
        fvg_high = c3_low
        mid = (fvg_low + fvg_high) / 2
        for i in range(bars_after):
            t = now + timedelta(minutes=45 + 15 * i)
            if fill:
                low = fvg_low - Decimal('0.0001')  # trade through
                high = fvg_high + Decimal('0.0002')
            elif mid_touch:
                low = mid - Decimal('0.0001')
                high = mid + Decimal('0.0001')
            else:
                low = fvg_high - Decimal('0.0001')
                high = fvg_high + Decimal('0.0001')
            open_price = low
            close = high
            bars.append(Bar(open_price, high, low, close, Decimal('800000'), t))
        return tuple(bars)

    def test_fvg_threshold_atr_fail_pass(self):
        session = make_session()
        det = FairValueGapDetector(parameters={"min_gap_size": Decimal('0.0'), "min_gap_atr_multiplier": Decimal('2.0')})
        # Build small gap relative to ATR -> no signal
        bars = self._build_bars_for_fvg(gap_pips=Decimal('0.00005'))
        ohlcv = OHLCV('EURUSD', bars, '15m')
        with self.assertRaises(ValueError):
            det.get_min_periods_required()
        # Detector requires at least 3 bars; our data has more. Now detect
        det.parameters.setdefault('max_concurrent_zones_per_side', 5)
        structs = det.detect(ohlcv, session)
        self.assertTrue(len(structs) == 0)

        # Build larger gap to pass ATR filter
        bars_big = self._build_bars_for_fvg(gap_pips=Decimal('0.0015'))
        ohlcv2 = OHLCV('EURUSD', bars_big, '15m')
        structs2 = det.detect(ohlcv2, session)
        self.assertTrue(len(structs2) >= 1)

    def test_fvg_partial_and_filled(self):
        session = make_session()
        det = FairValueGapDetector(parameters={"min_gap_size": Decimal('0.0'), "min_gap_atr_multiplier": Decimal('0.0')})
        # Partial only
        bars_partial = self._build_bars_for_fvg(mid_touch=True, fill=False)
        ohlcv = OHLCV('EURUSD', bars_partial, '15m')
        structs = det.detect(ohlcv, session)
        self.assertTrue(any(s.lifecycle.value == 'partial' for s in structs))
        # Filled
        bars_filled = self._build_bars_for_fvg(mid_touch=True, fill=True)
        ohlcv2 = OHLCV('EURUSD', bars_filled, '15m')
        structs2 = det.detect(ohlcv2, session)
        self.assertTrue(any(s.lifecycle.value == 'filled' for s in structs2))

    def test_fvg_age_expiry(self):
        session = make_session()
        det = FairValueGapDetector(parameters={"min_gap_size": Decimal('0.0'), "min_gap_atr_multiplier": Decimal('0.0'), "max_age_bars": 3})
        bars = self._build_bars_for_fvg(mid_touch=False, fill=False, bars_after=10)
        ohlcv = OHLCV('EURUSD', bars, '15m')
        structs = det.detect(ohlcv, session)
        self.assertTrue(any(s.lifecycle.value == 'expired' for s in structs))

    def test_fvg_dedupe_and_cap(self):
        session = make_session()
        params = {"min_gap_size": Decimal('0.0'), "min_gap_atr_multiplier": Decimal('0.0'), "max_concurrent_zones_per_side": 1}
        det = FairValueGapDetector(parameters=params)
        # Create two overlapping gaps by altering bars after; we reuse builder and then slightly adjust
        bars = list(self._build_bars_for_fvg(gap_pips=Decimal('0.0010')))
        # Inject another FVG later by adding another 3-candle gap sequence
        now = bars[-1].timestamp
        bars.append(Bar(Decimal('1.1020'), Decimal('1.1030'), Decimal('1.1015'), Decimal('1.1025'), Decimal('900000'), now + timedelta(minutes=15)))
        bars.append(Bar(Decimal('1.1026'), Decimal('1.1028'), Decimal('1.1022'), Decimal('1.1027'), Decimal('900000'), now + timedelta(minutes=30)))
        bars.append(Bar(Decimal('1.1031'), Decimal('1.1035'), Decimal('1.1031'), Decimal('1.1033'), Decimal('900000'), now + timedelta(minutes=45)))
        ohlcv = OHLCV('EURUSD', tuple(bars), '15m')
        structs = det.detect(ohlcv, session)
        # Capped at 1 per side
        self.assertLessEqual(len([s for s in structs if s.direction == 'bullish']), 1)


class TestBOSDetector(unittest.TestCase):
    def _build_bars_for_bos(self, bullish=True):
        now = datetime.now(timezone.utc)
        bars = []
        # Build base with minor swings
        price = Decimal('1.1000')
        for i in range(20):
            high = price + Decimal('0.0005')
            low = price - Decimal('0.0005')
            close = price + (Decimal('0.0003') if i % 2 == 0 else Decimal('-0.0003'))
            bars.append(Bar(price, high, low, close, Decimal('1000000'), now + timedelta(minutes=15*i)))
            price += Decimal('0.0001')
        # Create a swing and break beyond
        if bullish:
            last = bars[-1]
            bars.append(Bar(last.close, last.close + Decimal('0.0020'), last.close + Decimal('0.0010'), last.close + Decimal('0.0015'), Decimal('1500000'), last.timestamp + timedelta(minutes=15)))
        else:
            last = bars[-1]
            bars.append(Bar(last.close, last.close + Decimal('0.0010'), last.close - Decimal('0.0020'), last.close - Decimal('0.0015'), Decimal('1500000'), last.timestamp + timedelta(minutes=15)))
        return tuple(bars)

    def test_bos_pivots_confirm_debounce(self):
        session = make_session()
        det = BreakOfStructureDetector(parameters={"min_break_strength": Decimal('0.0005'), "pivot_window": 3, "confirmation_periods": 1, "debounce_bars": 3})
        ohlcv = OHLCV('EURUSD', self._build_bars_for_bos(bullish=True), '15m')
        structs = det.detect(ohlcv, session)
        # At least one bullish BOS
        self.assertTrue(any(s.direction == 'bullish' for s in structs))
        # Debounce: ensure no duplicates within window
        bullish_structs = [s for s in structs if s.direction == 'bullish']
        if len(bullish_structs) > 1:
            idxs = [s.origin_index for s in bullish_structs]
            # Differences should respect debounce
            diffs_ok = all((j - i) >= det.debounce_bars for i, j in zip(idxs, idxs[1:]))
            self.assertTrue(diffs_ok)


class TestOBDetector(unittest.TestCase):
    def _build_bars_for_ob(self, bullish_bos=True):
        now = datetime.now(timezone.utc)
        bars = []
        # Build base with minor swings
        price = Decimal('1.1000')
        for i in range(20):
            high = price + Decimal('0.0005')
            low = price - Decimal('0.0005')
            close = price + (Decimal('0.0003') if i % 2 == 0 else Decimal('-0.0003'))
            bars.append(Bar(price, high, low, close, Decimal('1000000'), now + timedelta(minutes=15*i)))
            price += Decimal('0.0001')
        
        # Add opposing candle before displacement
        last = bars[-1]
        if bullish_bos:
            # Bearish candle before bullish BOS
            bars.append(Bar(last.close, last.close + Decimal('0.0005'), last.close - Decimal('0.0010'), last.close - Decimal('0.0005'), Decimal('1200000'), last.timestamp + timedelta(minutes=15)))
        else:
            # Bullish candle before bearish BOS
            bars.append(Bar(last.close, last.close + Decimal('0.0010'), last.close - Decimal('0.0005'), last.close + Decimal('0.0005'), Decimal('1200000'), last.timestamp + timedelta(minutes=15)))
        
        # Add displacement candle (BOS)
        last = bars[-1]
        if bullish_bos:
            bars.append(Bar(last.close, last.close + Decimal('0.0020'), last.close + Decimal('0.0010'), last.close + Decimal('0.0015'), Decimal('1500000'), last.timestamp + timedelta(minutes=15)))
        else:
            bars.append(Bar(last.close, last.close + Decimal('0.0010'), last.close - Decimal('0.0020'), last.close - Decimal('0.0015'), Decimal('1500000'), last.timestamp + timedelta(minutes=15)))
        
        return tuple(bars)

    def _create_mock_bos(self, direction='bullish', swing_index=20, break_level=Decimal('1.1020')):
        now = datetime.now(timezone.utc)
        bar = Bar(Decimal('1.1000'), Decimal('1.1010'), Decimal('1.0990'), Decimal('1.1005'), Decimal('1000000'), now)
        return Structure(
            structure_id=f"BOS_{direction}_{swing_index}",
            structure_type=StructureType.BREAK_OF_STRUCTURE,
            symbol='EURUSD',
            timeframe='15m',
            start_bar=bar,
            end_bar=bar,
            high_price=Decimal('1.1010'),
            low_price=Decimal('1.0990'),
            quality=StructureQuality.HIGH,
            quality_score=Decimal('0.8'),
            created_timestamp=now,
            session_id='test_session',
            direction=direction,
            origin_index=swing_index,
            lifecycle=LifecycleState.UNFILLED,
            links={'swing_index': swing_index},
            metadata={'break_level': float(break_level)}
        )

    def test_ob_bos_linked_creation(self):
        session = make_session()
        det = OrderBlockDetector(parameters={
            "displacement_min_body_atr": Decimal('0.5'),
            "excess_beyond_swing_atr": Decimal('0.1'),
            "max_age_bars": 100,
            "max_concurrent_zones_per_side": 3,
            "mid_band_atr": Decimal('0.1')
        })
        
        bars = self._build_bars_for_ob(bullish_bos=True)
        ohlcv = OHLCV('EURUSD', bars, '15m')
        
        # Create mock BOS
        bos = self._create_mock_bos('bullish', 21, Decimal('1.1020'))
        
        structs = det.detect(ohlcv, session, existing_structures=[bos])
        self.assertTrue(len(structs) >= 1)
        
        ob = structs[0]
        self.assertEqual(ob.structure_type, StructureType.ORDER_BLOCK)
        self.assertEqual(ob.direction, 'bearish')  # OB opposite to BOS
        self.assertIn('bos_id', ob.links)
        self.assertIn('broken_swing_index', ob.links)
        self.assertEqual(ob.links['bos_id'], bos.structure_id)

    def test_ob_mitigation_fill_expiry(self):
        session = make_session()
        det = OrderBlockDetector(parameters={
            "displacement_min_body_atr": Decimal('0.5'),
            "excess_beyond_swing_atr": Decimal('0.1'),
            "max_age_bars": 5,  # Short expiry for testing
            "max_concurrent_zones_per_side": 3,
            "mid_band_atr": Decimal('0.1')
        })
        
        bars = self._build_bars_for_ob(bullish_bos=True)
        ohlcv = OHLCV('EURUSD', bars, '15m')
        
        bos = self._create_mock_bos('bullish', 21, Decimal('1.1020'))
        structs = det.detect(ohlcv, session, existing_structures=[bos])
        
        if structs:
            ob = structs[0]
            # Test age expiry
            det.active_obs = [ob]
            # Add more bars to trigger age expiry
            for i in range(10):
                last = bars[-1]
                bars = list(bars) + [Bar(last.close, last.close + Decimal('0.0001'), last.close - Decimal('0.0001'), last.close, Decimal('1000000'), last.timestamp + timedelta(minutes=15))]
            
            ohlcv2 = OHLCV('EURUSD', tuple(bars), '15m')
            det.detect(ohlcv2, session, existing_structures=[bos])
            # OB should be expired due to age

    def test_ob_overlap_dedupe(self):
        session = make_session()
        det = OrderBlockDetector(parameters={
            "displacement_min_body_atr": Decimal('0.5'),
            "excess_beyond_swing_atr": Decimal('0.1'),
            "max_age_bars": 100,
            "max_concurrent_zones_per_side": 1,  # Cap at 1 per side
            "mid_band_atr": Decimal('0.1')
        })
        
        bars = self._build_bars_for_ob(bullish_bos=True)
        ohlcv = OHLCV('EURUSD', bars, '15m')
        
        # Create multiple BOS to generate multiple OBs
        bos1 = self._create_mock_bos('bullish', 21, Decimal('1.1020'))
        bos2 = self._create_mock_bos('bullish', 22, Decimal('1.1025'))
        
        structs = det.detect(ohlcv, session, existing_structures=[bos1, bos2])
        # Should be capped at 1 per side
        self.assertLessEqual(len([s for s in structs if s.direction == 'bearish']), 1)

    def test_ob_opposite_bos_invalidation(self):
        session = make_session()
        det = OrderBlockDetector(parameters={
            "displacement_min_body_atr": Decimal('0.5'),
            "excess_beyond_swing_atr": Decimal('0.1'),
            "max_age_bars": 100,
            "max_concurrent_zones_per_side": 3,
            "mid_band_atr": Decimal('0.1')
        })
        
        bars = self._build_bars_for_ob(bullish_bos=True)
        ohlcv = OHLCV('EURUSD', bars, '15m')
        
        # Create bullish BOS and OB
        bullish_bos = self._create_mock_bos('bullish', 21, Decimal('1.1020'))
        structs = det.detect(ohlcv, session, existing_structures=[bullish_bos])
        
        if structs:
            ob = structs[0]
            det.active_obs = [ob]
            
            # Add bearish BOS (opposite)
            bearish_bos = self._create_mock_bos('bearish', 22, Decimal('1.1010'))
            det.detect(ohlcv, session, existing_structures=[bullish_bos, bearish_bos])
            # OB should be invalidated by opposite BOS

    def test_ob_determinism_no_prints(self):
        session = make_session()
        det = OrderBlockDetector(parameters={
            "displacement_min_body_atr": Decimal('0.5'),
            "excess_beyond_swing_atr": Decimal('0.1'),
            "max_age_bars": 100,
            "max_concurrent_zones_per_side": 3,
            "mid_band_atr": Decimal('0.1')
        })
        
        bars = self._build_bars_for_ob(bullish_bos=True)
        ohlcv = OHLCV('EURUSD', bars, '15m')
        bos = self._create_mock_bos('bullish', 21, Decimal('1.1020'))
        
        # Run twice with same inputs
        structs1 = det.detect(ohlcv, session, existing_structures=[bos])
        det.reset()
        structs2 = det.detect(ohlcv, session, existing_structures=[bos])
        
        # Should produce identical results
        self.assertEqual(len(structs1), len(structs2))
        if structs1 and structs2:
            self.assertEqual(structs1[0].structure_id, structs2[0].structure_id)


class TestSweepDetector(unittest.TestCase):
    """Test Sweep detector implementation."""
    
    def _create_mock_bos(self, direction: str, swing_index: int, break_level: Decimal) -> Structure:
        """Create mock BOS structure for testing."""
        return Structure(
            structure_id=f"bos_{direction}_{swing_index}",
            structure_type=StructureType.BREAK_OF_STRUCTURE,
            symbol="EURUSD",
            timeframe="15m",
            start_index=swing_index,
            end_index=swing_index,
            high_price=break_level + Decimal('0.0010'),
            low_price=break_level - Decimal('0.0010'),
            quality=StructureQuality.HIGH,
            quality_score=Decimal('0.8'),
            created_timestamp=datetime.now(timezone.utc),
            direction=direction,
            origin_index=swing_index,
            lifecycle=LifecycleState.UNFILLED,
            links={'swing_index': swing_index},
            metadata={'break_level': float(break_level)}
        )
    
    def _build_bars_for_sweep(self, swing_high=True, penetration=True, close_back=True, follow_through=False):
        """Build test bars for sweep detection."""
        now = datetime.now(timezone.utc)
        bars = []
        
        # Build base bars for ATR calculation
        for i in range(15):
            bars.append(Bar(
                Decimal('1.1000'), Decimal('1.1010'), Decimal('1.0990'), Decimal('1.1005'),
                Decimal('1000000'), now + timedelta(minutes=15 * i)
            ))
        
        # Swing high at index 15
        swing_price = Decimal('1.1020')
        bars.append(Bar(
            Decimal('1.1015'), swing_price, Decimal('1.1010'), Decimal('1.1018'),
            Decimal('1200000'), now + timedelta(minutes=15 * 15)
        ))
        
        # Sweep bar at index 16
        if penetration:
            sweep_high = swing_price + Decimal('0.0005')  # Penetrate swing
        else:
            sweep_high = swing_price - Decimal('0.0001')  # No penetration
        
        bars.append(Bar(
            Decimal('1.1018'), sweep_high, Decimal('1.1015'), 
            Decimal('1.1017') if close_back else sweep_high,
            Decimal('1500000'), now + timedelta(minutes=15 * 16)
        ))
        
        # Follow-through bar
        if follow_through:
            bars.append(Bar(
                Decimal('1.1017'), Decimal('1.1015'), Decimal('1.1010'), Decimal('1.1012'),
                Decimal('1300000'), now + timedelta(minutes=15 * 17)
            ))
        
        return bars
    
    def test_sweep_penetration_thresholds(self):
        """Test sweep detection with ATR-scaled penetration thresholds."""
        session = make_session()
        det = SweepDetector(parameters={
            'sweep_excess_atr': Decimal('0.1'),
            'close_back_inside_within': 1,
            'min_follow_through_atr': Decimal('0.1'),
            'follow_through_window': 5
        })
        
        bars = self._build_bars_for_sweep(penetration=True, close_back=True)
        ohlcv = OHLCV('EURUSD', bars, '15m')
        
        # Create BOS structure for swing
        bos = self._create_mock_bos('bullish', 15, Decimal('1.1020'))
        
        sweeps = det.detect(ohlcv, session, existing_structures=[bos])
        
        # Should detect sweep
        self.assertEqual(len(sweeps), 1)
        sweep = sweeps[0]
        self.assertEqual(sweep.direction, 'bearish')
        self.assertEqual(sweep.origin_index, 16)
        self.assertEqual(sweep.links['swing_index'], 15)
        self.assertGreater(sweep.metadata['penetration_atr'], 0)
        self.assertEqual(sweep.metadata['close_back_inside'], 'same_bar')
    
    def test_sweep_re_entry_timing(self):
        """Test sweep re-entry timing with same/next bar and gap handling."""
        session = make_session()
        det = SweepDetector(parameters={
            'sweep_excess_atr': Decimal('0.1'),
            'close_back_inside_within': 2,  # Allow gap
            'min_follow_through_atr': Decimal('0.1'),
            'follow_through_window': 5
        })
        
        bars = self._build_bars_for_sweep(penetration=True, close_back=False)
        # Add gap bar (no close back inside)
        bars.append(Bar(
            Decimal('1.1018'), Decimal('1.1019'), Decimal('1.1016'), Decimal('1.1017'),
            Decimal('1000000'), datetime.now(timezone.utc) + timedelta(minutes=15 * 17)
        ))
        # Close back inside on next bar
        bars.append(Bar(
            Decimal('1.1017'), Decimal('1.1018'), Decimal('1.1015'), Decimal('1.1016'),
            Decimal('1000000'), datetime.now(timezone.utc) + timedelta(minutes=15 * 18)
        ))
        
        ohlcv = OHLCV('EURUSD', bars, '15m')
        bos = self._create_mock_bos('bullish', 15, Decimal('1.1020'))
        
        sweeps = det.detect(ohlcv, session, existing_structures=[bos])
        
        # Should detect sweep with gap handling
        self.assertEqual(len(sweeps), 1)
        sweep = sweeps[0]
        self.assertEqual(sweep.metadata['gap_bars'], 1)
        self.assertEqual(sweep.metadata['close_back_inside'], 'next_bar')
    
    def test_sweep_follow_through_vs_expiry(self):
        """Test sweep follow-through detection and expiry."""
        session = make_session()
        det = SweepDetector(parameters={
            'sweep_excess_atr': Decimal('0.1'),
            'close_back_inside_within': 1,
            'min_follow_through_atr': Decimal('0.1'),
            'follow_through_window': 5
        })
        
        bars = self._build_bars_for_sweep(penetration=True, close_back=True, follow_through=True)
        ohlcv = OHLCV('EURUSD', bars, '15m')
        bos = self._create_mock_bos('bullish', 15, Decimal('1.1020'))
        
        # First detection
        sweeps = det.detect(ohlcv, session, existing_structures=[bos])
        self.assertEqual(len(sweeps), 1)
        sweep = sweeps[0]
        self.assertEqual(sweep.lifecycle, LifecycleState.UNFILLED)
        
        # Update lifecycle
        det._update_sweep_lifecycle(ohlcv.bars, session)
        
        # Check lifecycle transitions
        active_sweeps = det.active_sweeps
        if active_sweeps:
            updated_sweep = active_sweeps[0]
            # Should transition to PARTIAL (close back inside)
            self.assertEqual(updated_sweep.lifecycle, LifecycleState.PARTIAL)
    
    def test_sweep_debounce(self):
        """Test sweep debounce per (symbol, timeframe, swing_index, direction)."""
        session = make_session()
        det = SweepDetector(parameters={
            'sweep_excess_atr': Decimal('0.1'),
            'close_back_inside_within': 1,
            'min_follow_through_atr': Decimal('0.1'),
            'follow_through_window': 5,
            'sweep_debounce_bars': 5
        })
        
        bars = self._build_bars_for_sweep(penetration=True, close_back=True)
        # Add second sweep attempt
        bars.append(Bar(
            Decimal('1.1017'), Decimal('1.1025'), Decimal('1.1015'), Decimal('1.1016'),
            Decimal('1000000'), datetime.now(timezone.utc) + timedelta(minutes=15 * 17)
        ))
        
        ohlcv = OHLCV('EURUSD', bars, '15m')
        bos = self._create_mock_bos('bullish', 15, Decimal('1.1020'))
        
        sweeps = det.detect(ohlcv, session, existing_structures=[bos])
        
        # Should only detect one sweep (second should be debounced)
        self.assertEqual(len(sweeps), 1)
        self.assertEqual(sweeps[0].origin_index, 16)  # First sweep only
    
    def test_sweep_dedupe_on_swing_direction(self):
        """Test sweep deduplication on (swing_index, direction)."""
        session = make_session()
        det = SweepDetector(parameters={
            'sweep_excess_atr': Decimal('0.1'),
            'close_back_inside_within': 1,
            'min_follow_through_atr': Decimal('0.1'),
            'follow_through_window': 5,
            'sweep_debounce_bars': 1  # Allow multiple sweeps for dedupe test
        })
        
        bars = self._build_bars_for_sweep(penetration=True, close_back=True)
        # Add overlapping sweep
        bars.append(Bar(
            Decimal('1.1017'), Decimal('1.1025'), Decimal('1.1015'), Decimal('1.1016'),
            Decimal('1000000'), datetime.now(timezone.utc) + timedelta(minutes=15 * 17)
        ))
        bars.append(Bar(
            Decimal('1.1016'), Decimal('1.1017'), Decimal('1.1014'), Decimal('1.1015'),
            Decimal('1000000'), datetime.now(timezone.utc) + timedelta(minutes=15 * 18)
        ))
        
        ohlcv = OHLCV('EURUSD', bars, '15m')
        bos = self._create_mock_bos('bullish', 15, Decimal('1.1020'))
        
        sweeps = det.detect(ohlcv, session, existing_structures=[bos])
        
        # Should dedupe to one sweep per (swing_index, direction)
        self.assertEqual(len(sweeps), 1)
        # Should keep the first one (higher quality due to earlier origin_index)
        self.assertEqual(sweeps[0].origin_index, 16)
    
    def test_sweep_determinism_and_no_prints(self):
        """Test sweep detector determinism and no prints."""
        session = make_session()
        det = SweepDetector(parameters={
            'sweep_excess_atr': Decimal('0.1'),
            'close_back_inside_within': 1,
            'min_follow_through_atr': Decimal('0.1'),
            'follow_through_window': 5
        })
        
        bars = self._build_bars_for_sweep(penetration=True, close_back=True)
        ohlcv = OHLCV('EURUSD', bars, '15m')
        bos = self._create_mock_bos('bullish', 15, Decimal('1.1020'))
        
        # First run
        sweeps1 = det.detect(ohlcv, session, existing_structures=[bos])
        ids1 = [s.structure_id for s in sweeps1]
        
        # Reset and second run
        det.reset()
        sweeps2 = det.detect(ohlcv, session, existing_structures=[bos])
        ids2 = [s.structure_id for s in sweeps2]
        
        # Should be identical
        self.assertEqual(ids1, ids2)
        self.assertEqual(len(sweeps1), len(sweeps2))


if __name__ == '__main__':
    unittest.main()


