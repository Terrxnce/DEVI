#!/usr/bin/env python
"""Analyze rejection losses to find patterns."""

import json
import os
from datetime import datetime
from collections import defaultdict

journal_dir = r'c:\Users\Index\DEVI\logs\trade_journal'
files = [f for f in os.listdir(journal_dir) if f.startswith('trade_journal_202601') and f.endswith('.json')]

all_trades = []
for f in sorted(files):
    with open(os.path.join(journal_dir, f), 'r') as fp:
        trades = json.load(fp)
        all_trades.extend(trades)

# Filter to rejection losses only
rejection_losses = [t for t in all_trades 
                   if t.get('structure_type') == 'rejection' 
                   and t.get('outcome') == 'loss'
                   and t.get('direction') not in ['UNKNOWN', None]]

rejection_wins = [t for t in all_trades 
                 if t.get('structure_type') == 'rejection' 
                 and t.get('outcome') == 'win'
                 and t.get('direction') not in ['UNKNOWN', None]]

print('=== REJECTION LOSSES DEEP DIVE ===')
print(f'Total rejection losses: {len(rejection_losses)}')
print(f'Total rejection wins: {len(rejection_wins)}')
print(f'Win rate: {100*len(rejection_wins)/(len(rejection_wins)+len(rejection_losses)):.1f}%')
print()

# By symbol
print('--- BY SYMBOL ---')
by_symbol = defaultdict(lambda: {'wins': [], 'losses': []})
for t in all_trades:
    if t.get('structure_type') == 'rejection' and t.get('direction') not in ['UNKNOWN', None]:
        if t['outcome'] == 'win':
            by_symbol[t['symbol']]['wins'].append(t)
        else:
            by_symbol[t['symbol']]['losses'].append(t)

for sym in sorted(by_symbol.keys(), key=lambda x: len(by_symbol[x]['losses']), reverse=True):
    data = by_symbol[sym]
    w, l = len(data['wins']), len(data['losses'])
    total = w + l
    wr = 100*w/total if total > 0 else 0
    pnl = sum(t['pnl_usd'] for t in data['wins']) + sum(t['pnl_usd'] for t in data['losses'])
    print(f'{sym}: {w}W/{l}L ({wr:.0f}% WR), ${pnl:.2f}')
print()

# By session
print('--- BY SESSION ---')
by_session = defaultdict(lambda: {'wins': [], 'losses': []})
for t in all_trades:
    if t.get('structure_type') == 'rejection' and t.get('direction') not in ['UNKNOWN', None]:
        session = t.get('session_name', 'unknown')
        if t['outcome'] == 'win':
            by_session[session]['wins'].append(t)
        else:
            by_session[session]['losses'].append(t)

for sess in sorted(by_session.keys(), key=lambda x: len(by_session[x]['losses']), reverse=True):
    data = by_session[sess]
    w, l = len(data['wins']), len(data['losses'])
    total = w + l
    wr = 100*w/total if total > 0 else 0
    pnl = sum(t['pnl_usd'] for t in data['wins']) + sum(t['pnl_usd'] for t in data['losses'])
    print(f'{sess}: {w}W/{l}L ({wr:.0f}% WR), ${pnl:.2f}')
print()

# By direction
print('--- BY DIRECTION ---')
by_dir = defaultdict(lambda: {'wins': [], 'losses': []})
for t in all_trades:
    if t.get('structure_type') == 'rejection' and t.get('direction') not in ['UNKNOWN', None]:
        if t['outcome'] == 'win':
            by_dir[t['direction']]['wins'].append(t)
        else:
            by_dir[t['direction']]['losses'].append(t)

for d in sorted(by_dir.keys()):
    data = by_dir[d]
    w, l = len(data['wins']), len(data['losses'])
    total = w + l
    wr = 100*w/total if total > 0 else 0
    pnl = sum(t['pnl_usd'] for t in data['wins']) + sum(t['pnl_usd'] for t in data['losses'])
    print(f'{d}: {w}W/{l}L ({wr:.0f}% WR), ${pnl:.2f}')
print()

# By hour of entry (losses only)
print('--- LOSSES BY ENTRY HOUR (UTC) ---')
by_hour = defaultdict(list)
for t in rejection_losses:
    try:
        entry_time = datetime.fromisoformat(t['entry_time'].replace('Z', '+00:00'))
        by_hour[entry_time.hour].append(t)
    except:
        pass
for hour in sorted(by_hour.keys()):
    trades = by_hour[hour]
    total_loss = sum(t['pnl_usd'] for t in trades)
    print(f'{hour:02d}:00 UTC: {len(trades)} losses, ${total_loss:.2f}')
print()

# By symbol+session combo
print('--- BY SYMBOL x SESSION (2+ trades) ---')
by_combo = defaultdict(lambda: {'wins': [], 'losses': []})
for t in all_trades:
    if t.get('structure_type') == 'rejection' and t.get('direction') not in ['UNKNOWN', None]:
        combo = f"{t['symbol']}_{t.get('session_name', 'unknown')}"
        if t['outcome'] == 'win':
            by_combo[combo]['wins'].append(t)
        else:
            by_combo[combo]['losses'].append(t)

for combo in sorted(by_combo.keys(), key=lambda x: len(by_combo[x]['wins'])+len(by_combo[x]['losses']), reverse=True):
    data = by_combo[combo]
    w, l = len(data['wins']), len(data['losses'])
    total = w + l
    if total >= 2:
        wr = 100*w/total if total > 0 else 0
        pnl = sum(t['pnl_usd'] for t in data['wins']) + sum(t['pnl_usd'] for t in data['losses'])
        print(f'{combo}: {w}W/{l}L ({wr:.0f}% WR), ${pnl:.2f}')
print()

# Hold time analysis
print('--- HOLD TIME ANALYSIS ---')
win_hold_times = [t.get('hold_time_minutes', 0) for t in rejection_wins if t.get('hold_time_minutes')]
loss_hold_times = [t.get('hold_time_minutes', 0) for t in rejection_losses if t.get('hold_time_minutes')]
if win_hold_times:
    print(f'Avg win hold time: {sum(win_hold_times)/len(win_hold_times):.0f} min')
if loss_hold_times:
    print(f'Avg loss hold time: {sum(loss_hold_times)/len(loss_hold_times):.0f} min')
print()

# RR analysis
print('--- INTENDED RR ANALYSIS ---')
win_rrs = [t.get('intended_rr', 0) for t in rejection_wins if t.get('intended_rr')]
loss_rrs = [t.get('intended_rr', 0) for t in rejection_losses if t.get('intended_rr')]
if win_rrs:
    print(f'Avg intended RR (wins): {sum(win_rrs)/len(win_rrs):.2f}')
if loss_rrs:
    print(f'Avg intended RR (losses): {sum(loss_rrs)/len(loss_rrs):.2f}')
print()

# List worst losses
print('--- TOP 5 WORST REJECTION LOSSES ---')
sorted_losses = sorted(rejection_losses, key=lambda x: x['pnl_usd'])
for t in sorted_losses[:5]:
    entry_time = t.get('entry_time', 'unknown')[:16]
    print(f"{t['symbol']} {t['direction']} @ {entry_time}: ${t['pnl_usd']:.2f}, session={t.get('session_name', 'unknown')}")

# BUY vs SELL breakdown
print()
print('--- REJECTION BUY LOSSES DETAIL ---')
buy_losses = [t for t in rejection_losses if t['direction'] == 'BUY']
for t in sorted(buy_losses, key=lambda x: x['pnl_usd']):
    entry_time = t.get('entry_time', 'unknown')[:16]
    print(f"{t['symbol']} @ {entry_time}: ${t['pnl_usd']:.2f}, session={t.get('session_name', 'unknown')}")
