#!/usr/bin/env python3
"""Analyze trading pairs performance by session."""
import json
from collections import defaultdict

# Load all trade journals for Jan 26-30
files = [
    'logs/trade_journal/trade_journal_20260126.json',
    'logs/trade_journal/trade_journal_20260127.json',
    'logs/trade_journal/trade_journal_20260128.json',
    'logs/trade_journal/trade_journal_20260129.json',
    'logs/trade_journal/trade_journal_20260130.json'
]

all_trades = []
for f in files:
    try:
        with open(f) as fp:
            all_trades.extend(json.load(fp))
    except:
        pass

# Analyze by symbol + session
results = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0.0})

for t in all_trades:
    symbol = t.get('symbol', 'unknown')
    session = t.get('session_name', 'unknown')
    relevance = t.get('session_relevance', 'unknown')
    outcome = t.get('outcome', 'unknown')
    pnl = t.get('pnl_usd', 0)
    
    key = (symbol, session, relevance)
    results[key]['pnl'] += pnl
    if outcome == 'win':
        results[key]['wins'] += 1
    else:
        results[key]['losses'] += 1

print('=' * 80)
print('SYMBOL + SESSION PERFORMANCE ANALYSIS (Jan 26-30, 2026)')
print('=' * 80)

# Group by symbol
by_symbol = defaultdict(list)
for key, data in results.items():
    symbol, session, relevance = key
    total = data['wins'] + data['losses']
    wr = data['wins'] / total * 100 if total > 0 else 0
    by_symbol[symbol].append({
        'session': session,
        'relevance': relevance,
        'wins': data['wins'],
        'losses': data['losses'],
        'total': total,
        'wr': wr,
        'pnl': data['pnl']
    })

for symbol in sorted(by_symbol.keys()):
    print(f'\n## {symbol}')
    print(f"{'Session':<15} {'Relevance':<12} {'W/L':<8} {'WR%':<8} {'PnL':>12}")
    print('-' * 60)
    symbol_total_pnl = 0
    symbol_total_wins = 0
    symbol_total_losses = 0
    for row in sorted(by_symbol[symbol], key=lambda x: -x['total']):
        wl = f"{row['wins']}/{row['losses']}"
        pnl_str = f"${row['pnl']:,.2f}"
        status = "WIN" if row['pnl'] > 0 else "LOSS"
        print(f"{row['session']:<15} {row['relevance']:<12} {wl:<8} {row['wr']:.1f}%    {pnl_str:>12} [{status}]")
        symbol_total_pnl += row['pnl']
        symbol_total_wins += row['wins']
        symbol_total_losses += row['losses']
    
    total_trades = symbol_total_wins + symbol_total_losses
    total_wr = symbol_total_wins / total_trades * 100 if total_trades > 0 else 0
    print(f"{'TOTAL':<15} {'':<12} {symbol_total_wins}/{symbol_total_losses:<5} {total_wr:.1f}%    ${symbol_total_pnl:>10,.2f}")

# Summary by relevance
print('\n' + '=' * 80)
print('PERFORMANCE BY SESSION RELEVANCE')
print('=' * 80)

by_relevance = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0.0})
for key, data in results.items():
    symbol, session, relevance = key
    by_relevance[relevance]['wins'] += data['wins']
    by_relevance[relevance]['losses'] += data['losses']
    by_relevance[relevance]['pnl'] += data['pnl']

print(f"\n{'Relevance':<15} {'W/L':<10} {'WR%':<10} {'PnL':>15}")
print('-' * 50)
for rel in ['ideal', 'acceptable', 'unknown', 'avoid']:
    if rel in by_relevance:
        data = by_relevance[rel]
        total = data['wins'] + data['losses']
        wr = data['wins'] / total * 100 if total > 0 else 0
        wl = f"{data['wins']}/{data['losses']}"
        status = "WIN" if data['pnl'] > 0 else "LOSS"
        print(f"{rel:<15} {wl:<10} {wr:.1f}%      ${data['pnl']:>12,.2f} [{status}]")
