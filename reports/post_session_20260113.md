# DEVI Post-Session Report: 2026-01-13
*Generated: 2026-01-17 22:56 UTC*

## Executive Summary
Today: 12 trades, 5W/7L (41.7% WR), $-891.52

## Today's Performance

| Metric | Value |
|--------|-------|
| Trades | 12 |
| Win Rate | 41.7% |
| PnL | $-891.52 |
| Profit Factor | 0.82 |
| Avg Winner | $791.88 |
| Avg Loser | $692.99 |

## 7-Day Rolling

| Metric | Value |
|--------|-------|
| Trades | 56 |
| Win Rate | 51.8% |
| PnL | $4,039.38 |
| Profit Factor | 1.29 |

## By Symbol (Today)

| Symbol | Trades | W/L | Win Rate | PnL |
|--------|--------|-----|----------|-----|
| AUDUSD | 6 | 1/5 | 16.7% | $-4,564.88 |
| EURUSD | 4 | 4/0 | 100.0% | $3,683.40 |
| AUDJPY | 2 | 0/2 | 0.0% | $-10.04 |

## By Structure (Today)

| Structure | Trades | W/L | Win Rate | PnL |
|-----------|--------|-----|----------|-----|
| engulfing | 5 | 4/1 | 80.0% | $2,638.20 |
| rejection | 7 | 1/6 | 14.3% | $-3,529.72 |

## Insights

- **observation**: AUDUSD and AUDJPY are underperforming, while EURUSD is performing well but with limited profitability.

## Recommendations

### 1. adjust_threshold
- **Scope**: {'symbol': 'AUDUSD', 'session': '1W', 'structure': 'engulfing'}
- **Change**: {'threshold_delta': 0.05}
- **Why**: To improve the win rate and potentially reduce losses.
- **Confidence**: low
- **Reversal**: When the win rate improves to 50% or above.
- **Guardrail**: confidence lowered due to small sample (n=4)

### 2. monitor
- **Scope**: {'symbol': 'EURUSD', 'session': '4W', 'structure': 'engulfing'}
- **Change**: {}
- **Why**: Performing well with a perfect win rate but limited profitability. Monitor for potential adjustments.
- **Confidence**: low
- **Reversal**: When the profitability increases significantly.
- **Guardrail**: confidence lowered due to small sample (n=1)

## Warnings

- **[HIGH]** The AUDJPY trade has a 0% win rate and should be closely monitored or potentially disabled.

## Detected Patterns

- **time_cluster**: 3 losses clustered around 16:00 UTC
- **time_cluster**: 4 losses clustered around 04:00 UTC
- **time_cluster**: 3 losses clustered around 18:00 UTC
- **time_cluster**: 3 losses clustered around 12:00 UTC
