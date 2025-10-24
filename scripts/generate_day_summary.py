#!/usr/bin/env python3
"""Generate DAY_X summary from backtest logs."""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

def generate_summary(log_file: str):
    """Generate summary from log file."""
    log_path = Path(log_file)
    if not log_path.exists():
        print(f"Log file not found: {log_file}")
        return None
    
    # Read logs
    logs = []
    with open(log_path, 'r') as f:
        for line in f:
            try:
                logs.append(json.loads(line))
            except:
                pass
    
    # Extract metrics
    decisions = [l for l in logs if l.get('message') == 'decision_generated']
    execution_results = [l for l in logs if l.get('message') == 'execution_result']
    structures = [l for l in logs if 'detected' in l.get('message', '')]
    
    # Detector stats
    detector_stats = defaultdict(lambda: {'seen': 0, 'fired': 0})
    for log in logs:
        if log.get('detector'):
            detector_stats[log['detector']]['seen'] += 1
            if 'detected' in log.get('message', ''):
                detector_stats[log['detector']]['fired'] += 1
    
    # RR analysis
    rr_values = []
    for d in decisions:
        rr = d.get('rr')
        if rr:
            rr_values.append(float(rr))
    
    # Validation errors
    validation_errors = defaultdict(int)
    for r in execution_results:
        for err in r.get('validation_errors', []):
            validation_errors[err] += 1
    
    # Summary
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "log_file": str(log_path),
        "pipeline_stats": {
            "total_logs": len(logs),
            "structures_detected": len(structures),
            "decisions_generated": len(decisions),
            "execution_results": len(execution_results),
            "pass_rate": f"{(len([r for r in execution_results if r.get('success')]) / len(execution_results) * 100):.1f}%" if execution_results else "N/A"
        },
        "detector_summary": dict(detector_stats),
        "rr_analysis": {
            "count": len(rr_values),
            "avg": f"{sum(rr_values) / len(rr_values):.2f}" if rr_values else "N/A",
            "min": f"{min(rr_values):.2f}" if rr_values else "N/A",
            "max": f"{max(rr_values):.2f}" if rr_values else "N/A",
            "rr_gte_1_5": len([r for r in rr_values if r >= 1.5])
        },
        "validation_errors": dict(validation_errors),
        "structure_types": defaultdict(int),
    }
    
    for s in structures:
        struct_type = s.get('message', '').replace('_detected', '').upper()
        summary["structure_types"][struct_type] += 1
    
    return summary

if __name__ == "__main__":
    # Get latest log file
    log_dir = Path("logs")
    if not log_dir.exists():
        print("No logs directory found")
        sys.exit(1)
    
    latest_log = max(log_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    print(f"[*] Processing: {latest_log}")
    
    summary = generate_summary(str(latest_log))
    if summary:
        print("\n" + "="*70)
        print("PHASE 1.5 DAY 1 SUMMARY")
        print("="*70)
        print(json.dumps(summary, indent=2))
        
        # Save summary
        summary_file = Path("artifacts") / f"day_1_summary_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        summary_file.parent.mkdir(exist_ok=True)
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"\n[OK] Summary saved: {summary_file}")
