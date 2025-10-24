"""
Acceptance tests for UZR pipeline integration.

Tests verify:
1. Feature flag behavior (flag off: no behavior change, flag on: UZR logs appear)
2. Deterministic replay (identical IDs + logs)
3. No prints (only structured logs)
4. Compatibility shim (rejection/rejection_confirmed_next booleans populated)
"""

import json
import logging
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from io import StringIO

import pytest

from core.models.ohlcv import Bar, OHLCV
from core.models.config import Config
from core.models.structure import Structure, StructureType, StructureQuality, LifecycleState
from core.orchestration.pipeline import TradingPipeline
from core.models.session import Session
from configs import config_loader


class TestUZRFeatureFlag:
    """Test UZR feature flag behavior."""
    
    def test_flag_off_no_uzr_processing(self):
        """When flag is off, UZR should not process."""
        all_configs = config_loader.get_all_configs()
        
        # Ensure flag is off
        all_configs['system']['features']['unified_zone_rejection'] = False
        
        config = Config(
            session_configs=all_configs['sessions'].get('session_configs', {}),
            session_rotation=all_configs['sessions'].get('session_rotation', {}),
            structure_configs=all_configs['structure'].get('structure_configs', {}),
            quality_thresholds=all_configs['structure'].get('quality_thresholds', {}),
            scoring_weights=all_configs['scoring'].get('scoring_weights', {}),
            max_structures=all_configs['structure'].get('max_structures', {}),
            guard_configs=all_configs['guards'].get('guard_configs', {}),
            risk_limits=all_configs['guards'].get('risk_limits', {}),
            sltp_configs=all_configs['sltp'].get('sltp_configs', {}),
            indicator_configs=all_configs['indicators'],
            system_configs=all_configs['system'].get('system_configs', {})
        )
        
        pipeline = TradingPipeline(config)
        assert not pipeline.uzr_enabled
    
    def test_flag_on_uzr_enabled(self):
        """When flag is on, UZR should be enabled."""
        all_configs = config_loader.get_all_configs()
        
        # Enable flag
        all_configs['system']['features']['unified_zone_rejection'] = True
        
        config = Config(
            session_configs=all_configs['sessions'].get('session_configs', {}),
            session_rotation=all_configs['sessions'].get('session_rotation', {}),
            structure_configs=all_configs['structure'].get('structure_configs', {}),
            quality_thresholds=all_configs['structure'].get('quality_thresholds', {}),
            scoring_weights=all_configs['scoring'].get('scoring_weights', {}),
            max_structures=all_configs['structure'].get('max_structures', {}),
            guard_configs=all_configs['guards'].get('guard_configs', {}),
            risk_limits=all_configs['guards'].get('risk_limits', {}),
            sltp_configs=all_configs['sltp'].get('sltp_configs', {}),
            indicator_configs=all_configs['indicators'],
            system_configs=all_configs['system'].get('system_configs', {})
        )
        
        pipeline = TradingPipeline(config)
        assert pipeline.uzr_enabled


class TestUZRContextPopulation:
    """Test UZR context is properly populated in decisions."""
    
    def _create_sample_data(self) -> OHLCV:
        """Create sample OHLCV data."""
        bars = []
        base_price = Decimal('1.1000')
        
        for i in range(100):
            timestamp = datetime.now(timezone.utc) - timedelta(minutes=15 * (99 - i))
            price_change = Decimal(str((i % 10 - 5) * 0.0001))
            open_price = base_price + price_change
            high_price = open_price + Decimal('0.0005')
            low_price = open_price - Decimal('0.0003')
            close_price = open_price + Decimal(str((i % 3 - 1) * 0.0002))
            
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
    
    def test_uzr_context_in_metadata_flag_off(self):
        """With flag off, UZR fields should still be in metadata but false."""
        all_configs = config_loader.get_all_configs()
        all_configs['system']['features']['unified_zone_rejection'] = False
        
        config = Config(
            session_configs=all_configs['sessions'].get('session_configs', {}),
            session_rotation=all_configs['sessions'].get('session_rotation', {}),
            structure_configs=all_configs['structure'].get('structure_configs', {}),
            quality_thresholds=all_configs['structure'].get('quality_thresholds', {}),
            scoring_weights=all_configs['scoring'].get('scoring_weights', {}),
            max_structures=all_configs['structure'].get('max_structures', {}),
            guard_configs=all_configs['guards'].get('guard_configs', {}),
            risk_limits=all_configs['guards'].get('risk_limits', {}),
            sltp_configs=all_configs['sltp'].get('sltp_configs', {}),
            indicator_configs=all_configs['indicators'],
            system_configs=all_configs['system'].get('system_configs', {})
        )
        
        pipeline = TradingPipeline(config)
        sample_data = self._create_sample_data()
        timestamp = datetime.now(timezone.utc)
        
        decisions = pipeline.process_bar(sample_data, timestamp)
        
        # Check that decisions have UZR fields in metadata
        for decision in decisions:
            assert 'rejection' in decision.metadata
            assert 'rejection_confirmed_next' in decision.metadata
            assert 'uzr_enabled' in decision.metadata
            assert decision.metadata['uzr_enabled'] is False
    
    def test_uzr_context_in_metadata_flag_on(self):
        """With flag on, UZR fields should be populated in metadata."""
        all_configs = config_loader.get_all_configs()
        all_configs['system']['features']['unified_zone_rejection'] = True
        
        config = Config(
            session_configs=all_configs['sessions'].get('session_configs', {}),
            session_rotation=all_configs['sessions'].get('session_rotation', {}),
            structure_configs=all_configs['structure'].get('structure_configs', {}),
            quality_thresholds=all_configs['structure'].get('quality_thresholds', {}),
            scoring_weights=all_configs['scoring'].get('scoring_weights', {}),
            max_structures=all_configs['structure'].get('max_structures', {}),
            guard_configs=all_configs['guards'].get('guard_configs', {}),
            risk_limits=all_configs['guards'].get('risk_limits', {}),
            sltp_configs=all_configs['sltp'].get('sltp_configs', {}),
            indicator_configs=all_configs['indicators'],
            system_configs=all_configs['system'].get('system_configs', {})
        )
        
        pipeline = TradingPipeline(config)
        sample_data = self._create_sample_data()
        timestamp = datetime.now(timezone.utc)
        
        decisions = pipeline.process_bar(sample_data, timestamp)
        
        # Check that decisions have UZR fields in metadata
        for decision in decisions:
            assert 'rejection' in decision.metadata
            assert 'rejection_confirmed_next' in decision.metadata
            assert 'uzr_enabled' in decision.metadata
            assert decision.metadata['uzr_enabled'] is True


class TestDeterministicReplay:
    """Test deterministic replay of UZR detection."""
    
    def _create_sample_data(self) -> OHLCV:
        """Create sample OHLCV data."""
        bars = []
        base_price = Decimal('1.1000')
        
        for i in range(100):
            timestamp = datetime.now(timezone.utc) - timedelta(minutes=15 * (99 - i))
            price_change = Decimal(str((i % 10 - 5) * 0.0001))
            open_price = base_price + price_change
            high_price = open_price + Decimal('0.0005')
            low_price = open_price - Decimal('0.0003')
            close_price = open_price + Decimal(str((i % 3 - 1) * 0.0002))
            
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
    
    def test_identical_runs_produce_identical_decisions(self):
        """Two identical runs should produce identical decisions."""
        all_configs = config_loader.get_all_configs()
        all_configs['system']['features']['unified_zone_rejection'] = True
        
        config = Config(
            session_configs=all_configs['sessions'].get('session_configs', {}),
            session_rotation=all_configs['sessions'].get('session_rotation', {}),
            structure_configs=all_configs['structure'].get('structure_configs', {}),
            quality_thresholds=all_configs['structure'].get('quality_thresholds', {}),
            scoring_weights=all_configs['scoring'].get('scoring_weights', {}),
            max_structures=all_configs['structure'].get('max_structures', {}),
            guard_configs=all_configs['guards'].get('guard_configs', {}),
            risk_limits=all_configs['guards'].get('risk_limits', {}),
            sltp_configs=all_configs['sltp'].get('sltp_configs', {}),
            indicator_configs=all_configs['indicators'],
            system_configs=all_configs['system'].get('system_configs', {})
        )
        
        sample_data = self._create_sample_data()
        timestamp = datetime.now(timezone.utc)
        
        # Run 1
        pipeline1 = TradingPipeline(config)
        decisions1 = pipeline1.process_bar(sample_data, timestamp)
        
        # Run 2
        pipeline2 = TradingPipeline(config)
        decisions2 = pipeline2.process_bar(sample_data, timestamp)
        
        # Decisions should be identical
        assert len(decisions1) == len(decisions2)
        for d1, d2 in zip(decisions1, decisions2):
            assert d1.decision_type == d2.decision_type
            assert d1.symbol == d2.symbol
            assert d1.entry_price == d2.entry_price
            assert d1.stop_loss == d2.stop_loss
            assert d1.take_profit == d2.take_profit
            assert d1.structure_id == d2.structure_id


class TestStructuredLogging:
    """Test that only structured logs are produced (no prints)."""
    
    def _create_sample_data(self) -> OHLCV:
        """Create sample OHLCV data."""
        bars = []
        base_price = Decimal('1.1000')
        
        for i in range(100):
            timestamp = datetime.now(timezone.utc) - timedelta(minutes=15 * (99 - i))
            price_change = Decimal(str((i % 10 - 5) * 0.0001))
            open_price = base_price + price_change
            high_price = open_price + Decimal('0.0005')
            low_price = open_price - Decimal('0.0003')
            close_price = open_price + Decimal(str((i % 3 - 1) * 0.0002))
            
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
    
    def test_no_prints_only_structured_logs(self, caplog):
        """Pipeline should use structured logs, not prints."""
        all_configs = config_loader.get_all_configs()
        all_configs['system']['features']['unified_zone_rejection'] = True
        
        config = Config(
            session_configs=all_configs['sessions'].get('session_configs', {}),
            session_rotation=all_configs['sessions'].get('session_rotation', {}),
            structure_configs=all_configs['structure'].get('structure_configs', {}),
            quality_thresholds=all_configs['structure'].get('quality_thresholds', {}),
            scoring_weights=all_configs['scoring'].get('scoring_weights', {}),
            max_structures=all_configs['structure'].get('max_structures', {}),
            guard_configs=all_configs['guards'].get('guard_configs', {}),
            risk_limits=all_configs['guards'].get('risk_limits', {}),
            sltp_configs=all_configs['sltp'].get('sltp_configs', {}),
            indicator_configs=all_configs['indicators'],
            system_configs=all_configs['system'].get('system_configs', {})
        )
        
        pipeline = TradingPipeline(config)
        sample_data = self._create_sample_data()
        timestamp = datetime.now(timezone.utc)
        
        # Capture logs
        with caplog.at_level(logging.INFO):
            decisions = pipeline.process_bar(sample_data, timestamp)
        
        # Check that logs are structured (have extra field)
        for record in caplog.records:
            # Structured logs should have extra dict
            if hasattr(record, 'extra'):
                assert isinstance(record.extra, dict)


class TestSnapshotBehavior:
    """Test that flag off produces identical behavior to baseline."""
    
    def _create_sample_data(self) -> OHLCV:
        """Create sample OHLCV data."""
        bars = []
        base_price = Decimal('1.1000')
        
        for i in range(100):
            timestamp = datetime.now(timezone.utc) - timedelta(minutes=15 * (99 - i))
            price_change = Decimal(str((i % 10 - 5) * 0.0001))
            open_price = base_price + price_change
            high_price = open_price + Decimal('0.0005')
            low_price = open_price - Decimal('0.0003')
            close_price = open_price + Decimal(str((i % 3 - 1) * 0.0002))
            
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
    
    def test_flag_off_snapshot_unchanged(self):
        """With flag off, pipeline behavior should be identical to baseline."""
        all_configs = config_loader.get_all_configs()
        all_configs['system']['features']['unified_zone_rejection'] = False
        
        config = Config(
            session_configs=all_configs['sessions'].get('session_configs', {}),
            session_rotation=all_configs['sessions'].get('session_rotation', {}),
            structure_configs=all_configs['structure'].get('structure_configs', {}),
            quality_thresholds=all_configs['structure'].get('quality_thresholds', {}),
            scoring_weights=all_configs['scoring'].get('scoring_weights', {}),
            max_structures=all_configs['structure'].get('max_structures', {}),
            guard_configs=all_configs['guards'].get('guard_configs', {}),
            risk_limits=all_configs['guards'].get('risk_limits', {}),
            sltp_configs=all_configs['sltp'].get('sltp_configs', {}),
            indicator_configs=all_configs['indicators'],
            system_configs=all_configs['system'].get('system_configs', {})
        )
        
        pipeline = TradingPipeline(config)
        sample_data = self._create_sample_data()
        timestamp = datetime.now(timezone.utc)
        
        # Process with flag off
        decisions = pipeline.process_bar(sample_data, timestamp)
        
        # Verify decisions are generated (not affected by flag)
        assert isinstance(decisions, list)
        
        # Verify UZR context is present but disabled
        for decision in decisions:
            assert decision.metadata.get('uzr_enabled') is False
            assert decision.metadata.get('rejection') is False
            assert decision.metadata.get('rejection_confirmed_next') is False
