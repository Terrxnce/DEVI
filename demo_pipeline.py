"""
D.E.V.I 2.0 Pipeline Demo

Demonstrates the trading pipeline with sample data.
"""

import json
from decimal import Decimal
from datetime import datetime, timezone, timedelta

# Import core modules
from core.models.ohlcv import Bar, OHLCV
from core.models.config import Config
from core.orchestration.pipeline import TradingPipeline
from configs import config_loader


def create_sample_data() -> OHLCV:
    """Create sample OHLCV data for demonstration."""
    bars = []
    base_price = Decimal('1.1000')
    
    # Generate 100 bars of sample data
    for i in range(100):
        timestamp = datetime.now(timezone.utc) - timedelta(minutes=15 * (99 - i))
        
        # Simple price movement simulation
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
    
    return OHLCV(
        symbol='EURUSD',
        bars=tuple(bars),
        timeframe='15m'
    )


def create_sample_config() -> Config:
    """Create sample configuration for demonstration."""
    # Load configurations
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


def main():
    """Main demo function."""
    print("D.E.V.I 2.0 Pipeline Demo")
    print("=" * 50)
    
    # Create sample data and configuration
    print("Creating sample data...")
    sample_data = create_sample_data()
    print(f"Generated {len(sample_data.bars)} bars for {sample_data.symbol}")
    
    print("Loading configuration...")
    config = create_sample_config()
    print(f"Configuration loaded with hash: {config.config_hash.hash_value[:16]}...")
    
    # Initialize pipeline
    print("Initializing trading pipeline...")
    pipeline = TradingPipeline(config)
    print("Pipeline initialized successfully")
    
    # Process sample data
    print("\nProcessing sample data...")
    timestamp = datetime.now(timezone.utc)
    
    decisions = pipeline.process_bar(sample_data, timestamp)
    
    print(f"\nPipeline Results:")
    print(f"- Processed bars: {pipeline.processed_bars}")
    print(f"- Decisions generated: {pipeline.decisions_generated}")
    
    if decisions:
        print(f"\nDecisions Generated:")
        for i, decision in enumerate(decisions, 1):
            print(f"  {i}. {decision.decision_type.value} {decision.symbol}")
            print(f"     Entry: {decision.entry_price}")
            print(f"     SL: {decision.stop_loss}")
            print(f"     TP: {decision.take_profit}")
            print(f"     R:R: {decision.risk_reward_ratio:.2f}")
            print(f"     Confidence: {decision.confidence_score:.2f}")
            print(f"     Reasoning: {decision.reasoning}")
    else:
        print("No trading decisions generated (likely due to guards or session restrictions)")
    
    # Show pipeline statistics
    stats = pipeline.get_pipeline_stats()
    print(f"\nPipeline Statistics:")
    print(json.dumps(stats, indent=2, default=str))
    
    print("\nDemo completed successfully!")


if __name__ == "__main__":
    main()




