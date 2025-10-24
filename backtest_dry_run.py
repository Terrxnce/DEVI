"""
Dry-Run Backtest Script

Runs the trading pipeline in dry-run mode to validate executor reliability.
Generates test data and processes through the pipeline, collecting execution metrics.
"""

import sys
import os

# Force UTF-8 encoding on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import json
import logging
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Import core modules
from core.models.ohlcv import Bar, OHLCV
from core.models.config import Config
from core.orchestration.pipeline import TradingPipeline
from configs import config_loader


# Configure logging to JSON format
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        # Add extra fields
        if hasattr(record, '__dict__'):
            for key, value in record.__dict__.items():
                if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName', 
                              'levelname', 'levelno', 'lineno', 'module', 'msecs', 'message',
                              'pathname', 'process', 'processName', 'relativeCreated', 'thread',
                              'threadName', 'exc_info', 'exc_text', 'stack_info', 'getMessage']:
                    if not key.startswith('_'):
                        log_obj[key] = value
        return json.dumps(log_obj)


def setup_logging():
    """Setup JSON logging to file."""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / f'dry_run_backtest_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.json'
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # File handler with JSON formatter
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    root_logger.addHandler(console_handler)
    
    return log_file


def load_csv_data(csv_path: str = 'infra/data/eurusd_m15_clean.csv', symbol: str = 'EURUSD', num_bars: int = 1000) -> OHLCV:
    """Load OHLCV data from CSV file."""
    import pandas as pd
    
    if not Path(csv_path).exists():
        print(f"CSV file not found: {csv_path}, falling back to synthetic")
        return create_sample_data(num_bars, symbol)
    
    try:
        df = pd.read_csv(csv_path)
        df.columns = [c.strip().lower() for c in df.columns]
        
        # Find timestamp column
        time_col = next((c for c in ['timestamp_utc', 'timestamp', 'datetime'] if c in df.columns), None)
        if time_col is None:
            raise ValueError("No timestamp column found")
        
        df[time_col] = pd.to_datetime(df[time_col], utc=True)
        df = df.sort_values(time_col)
        df = df.tail(num_bars)
        
        bars = []
        for _, row in df.iterrows():
            bar = Bar(
                open=Decimal(str(row['open'])),
                high=Decimal(str(row['high'])),
                low=Decimal(str(row['low'])),
                close=Decimal(str(row['close'])),
                volume=Decimal(str(row.get('volume', 0))),
                timestamp=row[time_col].to_pydatetime()
            )
            bars.append(bar)
        
        print(f"Loaded {len(bars)} bars from CSV")
        return OHLCV(
            symbol=symbol,
            bars=tuple(bars),
            timeframe='15m'
        )
    except Exception as e:
        print(f"Error loading CSV: {e}, falling back to synthetic")
        return create_sample_data(num_bars, symbol)


def create_sample_data(num_bars: int = 1000, symbol: str = 'EURUSD') -> OHLCV:
    """Create sample OHLCV data for backtesting."""
    bars = []
    base_price = Decimal('1.0950')
    
    # Generate bars with realistic price movement
    # Use fixed base time at 12:00 UTC (LONDON session is 8:00-17:00 UTC)
    base_time = datetime(2025, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
    
    for i in range(num_bars):
        timestamp = base_time - timedelta(minutes=15 * (num_bars - 1 - i))
        
        # Add occasional volatility shocks every 60-90 bars to create gaps/impulses
        shock_intensity = Decimal('0')
        if (i % 75 == 0) and i > 0:
            # Create a directional shock (impulse move)
            shock_intensity = Decimal(str(0.0015 if i % 150 == 0 else -0.0015))
        
        # Simulate price movement with some volatility
        price_change = Decimal(str((i % 20 - 10) * 0.00005)) + shock_intensity
        open_price = base_price + price_change
        close_price = open_price + Decimal(str((i % 5 - 2) * 0.0003))
        
        # Ensure high >= max(open, close) and low <= min(open, close)
        high_price = max(open_price, close_price) + Decimal('0.0012')  # Increased for more structure
        low_price = min(open_price, close_price) - Decimal('0.0008')   # Increased for more structure
        
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
    
    return OHLCV(
        symbol=symbol,
        bars=tuple(bars),
        timeframe='15m'
    )


def create_config() -> Config:
    """Create configuration for backtesting."""
    all_configs = config_loader.get_all_configs()
    
    return Config(
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


def create_mock_structures(data: OHLCV, session, num_structures: int = 3):
    """Create mock OB/FVG structures for testing pipeline end-to-end."""
    from core.models.structure import Structure, StructureType, StructureQuality, LifecycleState
    from decimal import Decimal
    from datetime import datetime, timezone
    
    structures = []
    bars = data.bars
    now = datetime.now(timezone.utc)
    
    # Create mock OB at bar 200
    if len(bars) > 200:
        bar_idx = 200
        structures.append(Structure(
            structure_id=f"mock_ob_1_{bar_idx}",
            structure_type=StructureType.ORDER_BLOCK,
            symbol=data.symbol,
            timeframe='15m',
            origin_index=bar_idx,
            start_bar=bars[bar_idx],
            end_bar=bars[bar_idx],
            high_price=bars[bar_idx].high + Decimal('0.0010'),
            low_price=bars[bar_idx].low - Decimal('0.0010'),
            direction='bullish',
            quality=StructureQuality.HIGH,
            quality_score=Decimal('0.75'),
            lifecycle=LifecycleState.UNFILLED,
            created_timestamp=now,
            session_id=session.session_id if session else 'BACKTEST',
            metadata={'source': 'synthetic_injected', 'detector': 'mock'}
        ))
    
    # Create mock FVG at bar 400
    if len(bars) > 400:
        bar_idx = 400
        structures.append(Structure(
            structure_id=f"mock_fvg_1_{bar_idx}",
            structure_type=StructureType.FAIR_VALUE_GAP,
            symbol=data.symbol,
            timeframe='15m',
            origin_index=bar_idx,
            start_bar=bars[bar_idx],
            end_bar=bars[bar_idx],
            high_price=bars[bar_idx].high + Decimal('0.0005'),
            low_price=bars[bar_idx].low - Decimal('0.0005'),
            direction='bearish',
            quality=StructureQuality.MEDIUM,
            quality_score=Decimal('0.65'),
            lifecycle=LifecycleState.UNFILLED,
            created_timestamp=now,
            session_id=session.session_id if session else 'BACKTEST',
            metadata={'source': 'synthetic_injected', 'detector': 'mock'}
        ))
    
    # Create mock OB at bar 600
    if len(bars) > 600:
        bar_idx = 600
        structures.append(Structure(
            structure_id=f"mock_ob_2_{bar_idx}",
            structure_type=StructureType.ORDER_BLOCK,
            symbol=data.symbol,
            timeframe='15m',
            origin_index=bar_idx,
            start_bar=bars[bar_idx],
            end_bar=bars[bar_idx],
            high_price=bars[bar_idx].high + Decimal('0.0010'),
            low_price=bars[bar_idx].low - Decimal('0.0010'),
            direction='bearish',
            quality=StructureQuality.HIGH,
            quality_score=Decimal('0.72'),
            lifecycle=LifecycleState.UNFILLED,
            created_timestamp=now,
            session_id=session.session_id if session else 'BACKTEST',
            metadata={'source': 'synthetic_injected', 'detector': 'mock'}
        ))
    
    return structures[:num_structures]


def run_backtest(num_bars: int = 1000, symbol: str = 'EURUSD'):
    """Run dry-run backtest."""
    logger = logging.getLogger(__name__)
    
    print("\n" + "="*70)
    print("D.E.V.I 2.0 DRY-RUN BACKTEST")
    print("="*70)
    
    # Setup
    print("\n[1/5] Setting up logging...")
    log_file = setup_logging()
    print(f"      Logs: {log_file}")
    
    print("\n[2/5] Loading data...")
    # Try to load from CSV first, fall back to synthetic
    sample_data = load_csv_data(csv_path='infra/data/eurusd_m15_clean.csv', symbol=symbol, num_bars=num_bars)
    print(f"      Loaded {len(sample_data.bars)} bars for {symbol}")
    
    print("\n[3/5] Loading configuration...")
    config = create_config()
    print(f"      Config hash: {str(config.config_hash.hash_value)[:16]}...")
    print(f"      Data source: {config.system_configs.get('data_source', 'UNKNOWN')}")
    
    # Verify execution config
    exec_config = config.system_configs.get('execution', {})
    print(f"      Execution mode: {exec_config.get('mode', 'UNKNOWN')}")
    print(f"      Execution enabled: {exec_config.get('enabled', False)}")
    print(f"      Min RR: {exec_config.get('min_rr', 'UNKNOWN')}")
    
    print("\n[4/5] Initializing pipeline...")
    pipeline = TradingPipeline(config)
    print(f"      Pipeline ready (executor enabled: {pipeline.executor.enabled})")
    print(f"      Executor mode: {pipeline.executor.mode.value}")
    print(f"      Broker symbols registered: {sorted(pipeline.broker_symbols.keys())}")
    
    print("\n[5/5] Processing bars through pipeline...")
    
    total_decisions = 0
    total_execution_results = 0
    
    # Process each bar
    for i, bar in enumerate(sample_data.bars):
        # Create OHLCV for this bar
        bar_data = OHLCV(
            symbol=symbol,
            bars=sample_data.bars[:i+1],
            timeframe='15m'
        )
        
        # Use bar's timestamp for session gate (not current time)
        timestamp = bar.timestamp
        
        # Process bar
        decisions = pipeline.process_bar(bar_data, timestamp)
        total_decisions += len(decisions)
        total_execution_results = len(pipeline.execution_results)
        
        # Progress indicator
        if (i + 1) % 50 == 0:
            print(f"      Processed {i+1}/{len(sample_data.bars)} bars | Decisions: {total_decisions} | Results: {total_execution_results}")
    
    print(f"      OK Completed {len(sample_data.bars)} bars")
    
    # Finalize session
    print("\n[6/6] Finalizing session...")
    pipeline.finalize_session("BACKTEST")
    print("      OK Session finalized, dry-run summary logged")
    
    # Collect metrics
    print("\n" + "="*70)
    print("BACKTEST RESULTS")
    print("="*70)
    
    stats = pipeline.get_pipeline_stats()
    print(f"\nPipeline Statistics:")
    print(f"  - Processed bars: {stats['processed_bars']}")
    print(f"  - Decisions generated: {stats['decisions_generated']}")
    print(f"  - Execution results: {stats['execution_results']}")
    print(f"  - Executor mode: {stats['executor_mode']}")
    
    # Detector summary
    print(f"\nDetector Summary:")
    detector_summary = pipeline.structure_manager.get_detector_summary()
    for detector_name, stats_dict in detector_summary.items():
        print(f"  - {detector_name}: seen={stats_dict['seen']}, fired={stats_dict['fired']}")
    
    # Calculate execution metrics
    if pipeline.execution_results:
        passed = sum(1 for r in pipeline.execution_results if r.success)
        failed = sum(1 for r in pipeline.execution_results if not r.success)
        pass_rate = (passed / len(pipeline.execution_results)) * 100 if pipeline.execution_results else 0
        
        print(f"\nExecution Metrics:")
        print(f"  - Total orders: {len(pipeline.execution_results)}")
        print(f"  - Passed: {passed}")
        print(f"  - Failed: {failed}")
        print(f"  - Pass rate: {pass_rate:.1f}%")
        
        # RR analysis
        rr_values = [r.rr for r in pipeline.execution_results if r.success and r.rr]
        if rr_values:
            avg_rr = sum(rr_values) / len(rr_values)
            min_rr = min(rr_values)
            max_rr = max(rr_values)
            print(f"\nRisk-Reward Ratio:")
            print(f"  - Average RR: {avg_rr:.2f}")
            print(f"  - Min RR: {min_rr:.2f}")
            print(f"  - Max RR: {max_rr:.2f}")
        
        # Error analysis
        if failed > 0:
            error_counts = {}
            for result in pipeline.execution_results:
                if not result.success:
                    for error in result.validation_errors:
                        error_counts[error] = error_counts.get(error, 0) + 1
            
            print(f"\nValidation Errors:")
            for error, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"  - {error}: {count}")
    else:
        print("\nNo execution results collected (no decisions generated)")
    
    print("\n" + "="*70)
    print(f"Log file: {log_file}")
    print("="*70 + "\n")
    
    return {
        'log_file': str(log_file),
        'bars_processed': stats['processed_bars'],
        'decisions_generated': stats['decisions_generated'],
        'execution_results': stats['execution_results'],
        'executor_mode': stats['executor_mode']
    }


if __name__ == "__main__":
    import sys
    
    # Parse arguments
    num_bars = 1000
    symbol = 'EURUSD'
    
    if len(sys.argv) > 1:
        try:
            num_bars = int(sys.argv[1])
        except ValueError:
            pass
    
    if len(sys.argv) > 2:
        symbol = sys.argv[2]
    
    # Run backtest
    results = run_backtest(num_bars=num_bars, symbol=symbol)
    
    # Print summary JSON
    print("\nBacktest Summary JSON:")
    print(json.dumps(results, indent=2))
