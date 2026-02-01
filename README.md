# D.E.V.I 2.0 - Deterministic Intraday Trading System

## Overview

D.E.V.I 2.0 is a deterministic, session-aware, structure-based trading system designed for intraday trading. The system prioritizes parity between backtest and live trading environments through deterministic algorithms and comprehensive configuration management.

## Architecture

### Core Principles

- **Determinism First**: All operations must produce identical results given the same inputs and configuration
- **Session Autonomy**: Each trading session (Asia, London, NY AM, NY PM) operates independently
- **Structure-Based**: Trading decisions based on market structure analysis (Order Blocks, Fair Value Gaps, etc.)
- **Parity Guarantee**: Backtest and live results must be bit-identical

### Pipeline Flow

```
15-min Bar → Session Gate → Pre-filters → Indicators → Structure Detection → 
Scoring → Guards → SL/TP Planning → Decision
```

### Directory Structure

```
DEVI/
├── core/                    # Core trading logic (no external dependencies)
│   ├── models/             # Data models (OHLCV, Decision, Structure, etc.)
│   ├── sessions/           # Session management and rotation
│   ├── indicators/         # Technical indicators (ATR, MA, etc.)
│   ├── structure/          # Market structure detection
│   ├── scoring/            # Structure scoring and ranking
│   ├── guards/             # Risk management guards
│   ├── sltp/               # Stop Loss / Take Profit planning
│   └── orchestration/      # Pipeline orchestration
├── apps/                   # Application layer (depends on core/)
│   ├── api/               # REST API
│   ├── backtester/        # Backtesting engine
│   ├── trader-daemon/     # Live trading daemon
│   └── workers/           # Background workers
├── configs/               # Configuration files
├── tests/                 # Test suite
│   ├── unit/             # Unit tests
│   ├── integration/      # Integration tests
│   └── parity/           # Parity tests
└── infra/                # Infrastructure (broker, data, logging)
```

## Key Features

### 1. Session Management
- **Automatic Rotation**: Asia → London → NY AM → NY PM → Asia
- **Session Autonomy**: Each session trades its own symbol list and parameters
- **Force Close**: All positions closed at session end
- **Idle Periods**: System remains idle between sessions

### 2. Structure Detection
- **Order Blocks (OB)**: Supply/demand zones with quality scoring
- **Fair Value Gaps (FVG)**: Price imbalances requiring fill
- **Break of Structure (BOS)**: Trend continuation signals
- **Sweeps**: Liquidity grab patterns
- **Quality Ranking**: Keep ≤5 OBs and ≤5 FVGs per chart

### 3. Risk Management Guards
- **Spread/ATR**: Trade only when spreads are reasonable
- **Min R:R**: Minimum risk-reward ratio enforcement
- **Hourly Caps**: Limit trades per hour
- **Drawdown Gates**: Halt trading on excessive losses
- **News Lockout**: Block trading around high-impact events

### 4. SL/TP Planning
- **Structure-Aware**: SL anchored to protective structures
- **Graceful Degradation**: Structure → ATR → Fixed fallback
- **Early Exit**: Exit on structure invalidation
- **R:R Optimization**: TP aimed at opposing structures

### 5. Deterministic Pipeline
- **No Randomness**: All operations use deterministic algorithms
- **No Wall Clock**: Use provided timestamps, not system time
- **No External I/O**: Core modules have no external dependencies
- **Config Hash**: All configurations are hashable for reproducibility

## Configuration

### Session Configuration (`configs/sessions.json`)
```json
{
  "session_configs": {
    "ASIA": {
      "symbols": ["EURUSD", "GBPUSD", "USDJPY"],
      "max_positions": 3,
      "max_risk_per_trade": 0.02
    }
  }
}
```

### Structure Configuration (`configs/structure.json`)
```json
{
  "structure_configs": {
    "order_block": {
      "min_bos_strength": 0.005,
      "min_retest_reaction": 0.003
    }
  }
}
```

### Guard Configuration (`configs/guards.json`)
```json
{
  "guard_configs": {
    "risk_reward": {
      "min_risk_reward_ratio": 1.5
    }
  }
}
```

## Usage

### Basic Pipeline Demo
```python
from core.orchestration.pipeline import TradingPipeline
from core.models.config import Config
from configs import config_loader

# Load configuration
all_configs = config_loader.get_all_configs()
config = Config(
    session_configs=all_configs['sessions']['session_configs'],
    # ... other configs
)

# Initialize pipeline
pipeline = TradingPipeline(config)

# Process data
decisions = pipeline.process_bar(ohlcv_data, timestamp)
```

### Running Tests
```bash
# Run unit tests
python -m pytest tests/unit/ -v

# Run integration tests
python -m pytest tests/integration/ -v

# Run parity tests
python -m pytest tests/parity/ -v
```

## Development Status

### ✅ Completed (Week 1 Deliverables)
- [x] SPECs for all core modules
- [x] Core models (OHLCV, Decision, Structure, Session)
- [x] Session management (Asia, London, NY AM, NY PM rotation)
- [x] Technical indicators (ATR, MA, Volatility, Momentum)
- [x] Structure detection (OB, FVG, BOS, Sweep)
- [x] Configuration system with placeholders
- [x] Basic pipeline orchestration
- [x] Unit test framework
- [x] Demo pipeline

### 🚧 In Progress
- [ ] Scoring system (Core + capped Addon)
- [ ] Guards implementation (spread/ATR, min R:R, hourly caps, drawdown, news lockout)
- [ ] SL/TP planning (structure-aware with fallback)
- [ ] Integration tests
- [ ] Parity testing framework

### 📋 Planned
- [ ] Broker adapter
- [ ] Backtesting engine
- [ ] Live trading daemon
- [ ] Performance optimization
- [ ] Documentation

## Testing Strategy

### Unit Tests (90% Coverage Target)
- Test each core module in isolation
- Validate deterministic behavior
- Test edge cases and error conditions

### Integration Tests
- Test full pipeline with fixtures
- Validate end-to-end functionality
- Test session transitions

### Parity Tests
- Compare backtest vs live results
- Validate deterministic outputs
- Test configuration hash consistency

## Performance Targets

- **Latency**: < 100ms per 15-min bar processing
- **Memory**: < 100MB for 1000 bars
- **Determinism**: 100% parity between runs
- **Reliability**: 99.9% uptime for live trading

## Contributing

1. Follow deterministic principles - no randomness in core/
2. Maintain 90% test coverage for new code
3. Update SPECs when modifying interfaces
4. Ensure all operations are hashable
5. Validate parity between backtest and live

## License

Proprietary - D.E.V.I Trading Systems

---

**Version**: 2.0  
**Status**: Development  
**Last Updated**: 2024




