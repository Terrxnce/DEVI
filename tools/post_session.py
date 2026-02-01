#!/usr/bin/env python
"""
Post-Session Report Generator CLI

Generates AI-powered trading insights using Ollama (LLaMA 3).

Usage:
    python tools/post_session.py --today
    python tools/post_session.py --date 2026-01-15
    python tools/post_session.py --date 2026-01-15 --no-ai
"""

import argparse
import sys
import os
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.analysis.post_session_analyzer import PostSessionAnalyzer


def main():
    parser = argparse.ArgumentParser(
        description="Generate post-session trading report with AI insights"
    )
    parser.add_argument(
        "--today",
        action="store_true",
        help="Generate report for today"
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Date to analyze (YYYY-MM-DD format)"
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip AI analysis (stats only)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="llama3",
        help="Ollama model to use (default: llama3)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console output"
    )
    
    args = parser.parse_args()
    
    # Determine date
    if args.today:
        target_date = datetime.now(timezone.utc)
    elif args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            print(f"Error: Invalid date format '{args.date}'. Use YYYY-MM-DD.")
            sys.exit(1)
    else:
        print("Error: Must specify --today or --date YYYY-MM-DD")
        parser.print_help()
        sys.exit(1)
    
    if not args.quiet:
        print(f"Generating post-session report for {target_date.strftime('%Y-%m-%d')}...")
        print()
    
    # Create analyzer
    analyzer = PostSessionAnalyzer(model=args.model)
    
    # If --no-ai, we still generate but skip Ollama call
    if args.no_ai:
        # Temporarily disable Ollama
        original_call = analyzer.call_ollama
        analyzer.call_ollama = lambda x: None
    
    # Generate report
    result = analyzer.generate_report(date=target_date)
    
    if args.no_ai:
        analyzer.call_ollama = original_call
    
    if not result['success']:
        print(f"Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)
    
    if not args.quiet:
        print("=" * 60)
        print(result['markdown'])
        print("=" * 60)
        print()
        print(f"Reports saved to:")
        print(f"  - {result['md_path']}")
        print(f"  - {result['json_path']}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
