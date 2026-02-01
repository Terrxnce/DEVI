"""
Quick validation script to verify the 10016 fix is working.
Monitors logs in real-time and reports on pre-check behavior.
"""
import json
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict

def monitor_validation_test(log_file: Path, duration_minutes: int = 120):
    """
    Monitor a live run and report on pre-check performance.
    
    Args:
        log_file: Path to the log file being written
        duration_minutes: How long to monitor (default 2 hours)
    """
    print("=" * 80)
    print("10016 FIX VALIDATION MONITOR")
    print("=" * 80)
    print(f"Monitoring: {log_file}")
    print(f"Duration: {duration_minutes} minutes")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print("\nWaiting for log file to be created...")
    
    # Wait for log file to exist
    while not log_file.exists():
        time.sleep(1)
    
    print(f"✓ Log file found: {log_file.name}\n")
    
    # Track statistics
    stats = {
        'pre_check_blocks': defaultdict(int),
        'order_send_attempts': defaultdict(int),
        'order_send_success': defaultdict(int),
        'order_send_10016': defaultdict(int),
        'total_10016_errors': 0,
        'total_trades_attempted': 0,
        'total_trades_succeeded': 0,
    }
    
    # Read log file continuously
    start_time = time.time()
    last_position = 0
    
    try:
        while (time.time() - start_time) < (duration_minutes * 60):
            with open(log_file, 'r', encoding='utf-8') as f:
                f.seek(last_position)
                new_lines = f.readlines()
                last_position = f.tell()
            
            for line in new_lines:
                try:
                    event = json.loads(line.strip())
                    msg = event.get('message', '')
                    symbol = event.get('symbol', 'UNKNOWN')
                    
                    # Track pre-check blocks
                    if msg == 'sl_too_close_for_broker':
                        stats['pre_check_blocks'][symbol] += 1
                        print(f"[PRE-CHECK BLOCK] {symbol}: SL {event.get('actual_sl_distance_pts', 0):.1f} pts < {event.get('min_required_pts', 0):.1f} pts (min: {event.get('symbol_min', 0)})")
                    
                    # Track order send attempts
                    elif msg == 'order_send_attempt':
                        stats['order_send_attempts'][symbol] += 1
                        stats['total_trades_attempted'] += 1
                    
                    # Track order results
                    elif msg == 'order_send_result':
                        retcode = event.get('retcode')
                        success = event.get('success', False)
                        
                        if success:
                            stats['order_send_success'][symbol] += 1
                            stats['total_trades_succeeded'] += 1
                            print(f"[SUCCESS] {symbol}: Order executed (ticket: {event.get('ticket')})")
                        elif retcode == 10016:
                            stats['order_send_10016'][symbol] += 1
                            stats['total_10016_errors'] += 1
                            print(f"[!!!10016!!!] {symbol}: INVALID STOPS ERROR - FIX FAILED!")
                        else:
                            print(f"[FAIL] {symbol}: {event.get('retcode_description', 'Unknown error')}")
                    
                except:
                    continue
            
            # Print periodic summary
            elapsed = int(time.time() - start_time)
            if elapsed % 300 == 0 and elapsed > 0:  # Every 5 minutes
                print_summary(stats, elapsed)
            
            time.sleep(2)  # Check every 2 seconds
    
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user.")
    
    # Final summary
    print("\n" + "=" * 80)
    print("FINAL VALIDATION SUMMARY")
    print("=" * 80)
    print_summary(stats, int(time.time() - start_time))
    
    # Verdict
    print("\n" + "=" * 80)
    if stats['total_10016_errors'] == 0:
        print("✅ VALIDATION PASSED - ZERO 10016 ERRORS!")
        print("The fix is working correctly. Pre-check is preventing invalid orders.")
    else:
        print(f"❌ VALIDATION FAILED - {stats['total_10016_errors']} 10016 ERRORS DETECTED")
        print("The fix needs adjustment. Review logs for details.")
    print("=" * 80)

def print_summary(stats, elapsed_seconds):
    """Print current statistics."""
    print(f"\n--- Summary ({elapsed_seconds // 60} min elapsed) ---")
    print(f"Total trades attempted: {stats['total_trades_attempted']}")
    print(f"Total trades succeeded: {stats['total_trades_succeeded']}")
    print(f"Total 10016 errors: {stats['total_10016_errors']}")
    
    print("\nPer-symbol breakdown:")
    all_symbols = set(list(stats['pre_check_blocks'].keys()) + 
                     list(stats['order_send_attempts'].keys()))
    
    for symbol in sorted(all_symbols):
        blocks = stats['pre_check_blocks'].get(symbol, 0)
        attempts = stats['order_send_attempts'].get(symbol, 0)
        success = stats['order_send_success'].get(symbol, 0)
        errors = stats['order_send_10016'].get(symbol, 0)
        
        print(f"  {symbol}: {blocks} blocked | {attempts} attempted | {success} succeeded | {errors} 10016 errors")
    print()

if __name__ == "__main__":
    # Find the most recent log file
    log_dir = Path(r"c:\Users\Index\DEVI\logs")
    
    # Look for today's log file
    today = datetime.now().strftime("%Y%m%d")
    pattern = f"live_mt5_{today}_*.json"
    
    log_files = sorted(log_dir.glob(pattern))
    
    if log_files:
        latest_log = log_files[-1]
        print(f"Found existing log: {latest_log.name}")
        print("Monitoring this file...\n")
    else:
        # Wait for new log file
        print(f"No log file found matching pattern: {pattern}")
        print("Waiting for new log file to be created...")
        print("(Start the live run now with: python run_live_mt5.py --symbols EURUSD XAUUSD GBPUSD USDJPY --mode live)\n")
        
        # Create expected log file path (will be created when run starts)
        timestamp = datetime.now().strftime("%H%M%S")
        latest_log = log_dir / f"live_mt5_{today}_{timestamp}.json"
    
    # Monitor the log
    monitor_validation_test(latest_log, duration_minutes=120)
