"""
Post-Session Analyzer - Generates AI-powered daily trading insights.

Aggregates trade journal data, computes statistics, and uses Ollama (LLaMA 3)
to generate structured insights and recommendations.

Output:
- Markdown report for human review
- JSON payload with schema-enforced recommendations
"""

import json
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict
import requests

logger = logging.getLogger(__name__)


@dataclass
class TradeSummary:
    """Aggregated trade statistics."""
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_winner: float = 0.0
    avg_loser: float = 0.0
    profit_factor: float = 0.0
    avg_rr: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0


@dataclass 
class Recommendation:
    """A single recommendation from the AI."""
    action: str
    scope: Dict[str, str]
    change: Dict[str, Any]
    why: str
    evidence: Dict[str, Any]
    confidence: str
    reversal_condition: str
    auto_applicable: bool = False


class PostSessionAnalyzer:
    """
    Analyzes trading performance and generates AI-powered insights.
    
    Usage:
        analyzer = PostSessionAnalyzer()
        report = analyzer.generate_report(date="2026-01-15")
    """
    
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL = "llama3"
    
    # Guardrails
    MIN_SAMPLE_SIZE = 10
    MAX_THRESHOLD_DELTA = 0.10
    MAX_CHANGES_PER_DAY = 2
    
    def __init__(
        self,
        journal_dir: str = None,
        reports_dir: str = None,
        ollama_url: str = None,
        model: str = None
    ):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.journal_dir = journal_dir or os.path.join(base_dir, "logs", "trade_journal")
        self.reports_dir = reports_dir or os.path.join(base_dir, "reports")
        self.ollama_url = ollama_url or self.OLLAMA_URL
        self.model = model or self.MODEL
        
        os.makedirs(self.reports_dir, exist_ok=True)
    
    def load_trades(self, date: datetime) -> List[Dict[str, Any]]:
        """Load trades for a specific date."""
        filename = f"trade_journal_{date.strftime('%Y%m%d')}.json"
        filepath = os.path.join(self.journal_dir, filename)
        
        if not os.path.exists(filepath):
            return []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                trades = json.load(f)
            # Filter out invalid entries
            return [t for t in trades if t.get('direction') not in ['UNKNOWN', None] and t.get('symbol')]
        except Exception as e:
            logger.warning(f"Failed to load trades from {filepath}: {e}")
            return []
    
    def load_trades_range(self, end_date: datetime, days: int = 7) -> List[Dict[str, Any]]:
        """Load trades for a date range."""
        all_trades = []
        for i in range(days):
            date = end_date - timedelta(days=i)
            all_trades.extend(self.load_trades(date))
        return all_trades
    
    def compute_summary(self, trades: List[Dict[str, Any]]) -> TradeSummary:
        """Compute aggregate statistics for a list of trades."""
        if not trades:
            return TradeSummary()
        
        wins = [t for t in trades if t.get('outcome') == 'win']
        losses = [t for t in trades if t.get('outcome') == 'loss']
        
        win_pnls = [t['pnl_usd'] for t in wins]
        loss_pnls = [abs(t['pnl_usd']) for t in losses]
        
        total_wins = sum(win_pnls) if win_pnls else 0
        total_losses = sum(loss_pnls) if loss_pnls else 0
        
        return TradeSummary(
            total_trades=len(trades),
            wins=len(wins),
            losses=len(losses),
            win_rate=len(wins) / len(trades) if trades else 0,
            total_pnl=sum(t['pnl_usd'] for t in trades),
            avg_winner=total_wins / len(wins) if wins else 0,
            avg_loser=total_losses / len(losses) if losses else 0,
            profit_factor=total_wins / total_losses if total_losses > 0 else float('inf'),
            avg_rr=sum(t.get('achieved_rr', 0) for t in trades) / len(trades) if trades else 0,
            best_trade=max(t['pnl_usd'] for t in trades) if trades else 0,
            worst_trade=min(t['pnl_usd'] for t in trades) if trades else 0
        )
    
    def compute_breakdowns(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute breakdowns by symbol, structure, session."""
        breakdowns = {
            'by_symbol': defaultdict(list),
            'by_structure': defaultdict(list),
            'by_session': defaultdict(list),
            'by_symbol_session': defaultdict(list),
            'by_symbol_structure': defaultdict(list)
        }
        
        for t in trades:
            symbol = t.get('symbol', 'UNKNOWN')
            structure = t.get('structure_type', 'unknown')
            session = t.get('session_name', 'unknown')
            
            breakdowns['by_symbol'][symbol].append(t)
            breakdowns['by_structure'][structure].append(t)
            breakdowns['by_session'][session].append(t)
            breakdowns['by_symbol_session'][f"{symbol}_{session}"].append(t)
            breakdowns['by_symbol_structure'][f"{symbol}_{structure}"].append(t)
        
        # Convert to summaries
        result = {}
        for category, groups in breakdowns.items():
            result[category] = {}
            for key, group_trades in groups.items():
                summary = self.compute_summary(group_trades)
                result[category][key] = asdict(summary)
        
        return result
    
    def find_patterns(self, trades: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Identify notable patterns in the data."""
        patterns = []
        
        if not trades:
            return patterns
        
        # Check for time-clustered losses
        losses = [t for t in trades if t.get('outcome') == 'loss']
        if len(losses) >= 3:
            # Group losses by hour
            loss_hours = defaultdict(int)
            for t in losses:
                try:
                    entry_time = datetime.fromisoformat(t['entry_time'].replace('Z', '+00:00'))
                    loss_hours[entry_time.hour] += 1
                except:
                    pass
            
            for hour, count in loss_hours.items():
                if count >= 3:
                    patterns.append({
                        "type": "time_cluster",
                        "text": f"{count} losses clustered around {hour:02d}:00 UTC"
                    })
        
        # Check for symbol-specific issues
        by_symbol = defaultdict(list)
        for t in trades:
            by_symbol[t.get('symbol', 'UNKNOWN')].append(t)
        
        for symbol, symbol_trades in by_symbol.items():
            wins = len([t for t in symbol_trades if t['outcome'] == 'win'])
            total = len(symbol_trades)
            if total >= 5 and wins / total < 0.3:
                patterns.append({
                    "type": "underperforming_symbol",
                    "text": f"{symbol} underperforming: {wins}/{total} wins ({100*wins/total:.0f}% WR)"
                })
            elif total >= 5 and wins / total > 0.7:
                patterns.append({
                    "type": "strong_symbol",
                    "text": f"{symbol} performing well: {wins}/{total} wins ({100*wins/total:.0f}% WR)"
                })
        
        # Check for structure-specific issues
        by_structure = defaultdict(list)
        for t in trades:
            by_structure[t.get('structure_type', 'unknown')].append(t)
        
        for structure, struct_trades in by_structure.items():
            wins = len([t for t in struct_trades if t['outcome'] == 'win'])
            total = len(struct_trades)
            if total >= 5 and wins / total < 0.35:
                patterns.append({
                    "type": "weak_structure",
                    "text": f"{structure} structure weak: {wins}/{total} wins ({100*wins/total:.0f}% WR)"
                })
        
        return patterns
    
    def _compact_breakdown(self, breakdown: Dict[str, Any]) -> str:
        """Convert breakdown to compact string format."""
        lines = []
        for key, stats in breakdown.items():
            w = stats.get('wins', 0)
            l = stats.get('losses', 0)
            wr = stats.get('win_rate', 0)
            pnl = stats.get('total_pnl', 0)
            lines.append(f"  {key}: {w}W/{l}L ({wr:.0%}), ${pnl:.0f}")
        return "\n".join(lines)
    
    def build_prompt(
        self,
        today_summary: TradeSummary,
        week_summary: TradeSummary,
        today_breakdowns: Dict[str, Any],
        week_breakdowns: Dict[str, Any],
        patterns: List[Dict[str, str]],
        date: datetime
    ) -> str:
        """Build the prompt for Ollama."""
        
        # Compact breakdowns to reduce prompt size
        symbol_str = self._compact_breakdown(today_breakdowns.get('by_symbol', {}))
        structure_str = self._compact_breakdown(today_breakdowns.get('by_structure', {}))
        session_str = self._compact_breakdown(today_breakdowns.get('by_session', {}))
        patterns_str = "\n".join([f"  - {p.get('text', '')}" for p in patterns[:5]])
        
        prompt = f"""Analyze trading: {today_summary.total_trades} trades, {today_summary.win_rate:.0%} WR, ${today_summary.total_pnl:.0f}. Symbols: {symbol_str}. Structures: {structure_str}.

Reply JSON only:
{{
  "summary": "1 sentence",
  "insights": [{{"text": "observation"}}],
  "recommendations": [
    {{
      "action": "adjust_threshold|disable_combo|monitor",
      "scope": {{"symbol": "...", "session": "...", "structure": "..."}},
      "change": {{"threshold_delta": 0.05}},
      "why": "reason based on data",
      "evidence": {{"n": 10, "win_rate": 0.3, "pnl": -500}},
      "confidence": "high|medium|low",
      "reversal_condition": "when to revert this change"
    }}
  ],
  "warnings": [
    {{"severity": "high|medium|low", "text": "warning description"}}
  ]
}}

Rules:
- Only recommend changes if sample size >= {self.MIN_SAMPLE_SIZE}
- threshold_delta must be between -{self.MAX_THRESHOLD_DELTA} and +{self.MAX_THRESHOLD_DELTA}
- Maximum {self.MAX_CHANGES_PER_DAY} recommendations
- Be conservative - only recommend changes with clear evidence
- If performance is good, say so and recommend no changes

Respond ONLY with the JSON object, no other text."""

        return prompt
    
    def call_ollama(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Call Ollama API and parse response using streaming to avoid timeout."""
        try:
            # Use streaming to avoid timeout on slow CPU inference
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 1000
                    }
                },
                stream=True,
                timeout=600
            )
            response.raise_for_status()
            
            # Collect streamed response
            text = ""
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        text += chunk.get('response', '')
                        if chunk.get('done', False):
                            break
                    except json.JSONDecodeError:
                        continue
            
            # Extract JSON from response
            # Try to find JSON block
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = text[start:end]
                return json.loads(json_str)
            
            logger.warning("No valid JSON found in Ollama response")
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API error: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Ollama response as JSON: {e}")
            return None
    
    def validate_recommendations(self, ai_response: Dict[str, Any]) -> Dict[str, Any]:
        """Apply guardrails to AI recommendations."""
        if not ai_response:
            return ai_response
        
        recommendations = ai_response.get('recommendations', [])
        validated = []
        
        for rec in recommendations[:self.MAX_CHANGES_PER_DAY]:
            # Check threshold delta bounds
            change = rec.get('change', {})
            delta = change.get('threshold_delta', 0)
            if abs(delta) > self.MAX_THRESHOLD_DELTA:
                change['threshold_delta'] = self.MAX_THRESHOLD_DELTA if delta > 0 else -self.MAX_THRESHOLD_DELTA
                rec['change'] = change
                rec['_guardrail_applied'] = f"threshold_delta clamped to ±{self.MAX_THRESHOLD_DELTA}"
            
            # Check sample size
            evidence = rec.get('evidence', {})
            n = evidence.get('n', 0)
            if n < self.MIN_SAMPLE_SIZE:
                rec['confidence'] = 'low'
                rec['_guardrail_applied'] = f"confidence lowered due to small sample (n={n})"
            
            # Mark as not auto-applicable (Phase 1)
            rec['auto_applicable'] = False
            
            validated.append(rec)
        
        ai_response['recommendations'] = validated
        return ai_response
    
    def generate_markdown(
        self,
        date: datetime,
        today_summary: TradeSummary,
        week_summary: TradeSummary,
        today_breakdowns: Dict[str, Any],
        patterns: List[Dict[str, str]],
        ai_response: Optional[Dict[str, Any]]
    ) -> str:
        """Generate markdown report."""
        
        lines = [
            f"# DEVI Post-Session Report: {date.strftime('%Y-%m-%d')}",
            f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
            "",
            "## Executive Summary",
        ]
        
        if ai_response and ai_response.get('executive_summary'):
            lines.append(ai_response['executive_summary'])
        else:
            lines.append(f"Today: {today_summary.total_trades} trades, {today_summary.wins}W/{today_summary.losses}L ({today_summary.win_rate:.1%} WR), ${today_summary.total_pnl:,.2f}")
        
        lines.extend([
            "",
            "## Today's Performance",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Trades | {today_summary.total_trades} |",
            f"| Win Rate | {today_summary.win_rate:.1%} |",
            f"| PnL | ${today_summary.total_pnl:,.2f} |",
            f"| Profit Factor | {today_summary.profit_factor:.2f} |",
            f"| Avg Winner | ${today_summary.avg_winner:,.2f} |",
            f"| Avg Loser | ${today_summary.avg_loser:,.2f} |",
            "",
            "## 7-Day Rolling",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Trades | {week_summary.total_trades} |",
            f"| Win Rate | {week_summary.win_rate:.1%} |",
            f"| PnL | ${week_summary.total_pnl:,.2f} |",
            f"| Profit Factor | {week_summary.profit_factor:.2f} |",
            "",
        ])
        
        # Breakdown tables
        if today_breakdowns.get('by_symbol'):
            lines.extend([
                "## By Symbol (Today)",
                "",
                "| Symbol | Trades | W/L | Win Rate | PnL |",
                "|--------|--------|-----|----------|-----|",
            ])
            for symbol, stats in today_breakdowns['by_symbol'].items():
                lines.append(f"| {symbol} | {stats['total_trades']} | {stats['wins']}/{stats['losses']} | {stats['win_rate']:.1%} | ${stats['total_pnl']:,.2f} |")
            lines.append("")
        
        if today_breakdowns.get('by_structure'):
            lines.extend([
                "## By Structure (Today)",
                "",
                "| Structure | Trades | W/L | Win Rate | PnL |",
                "|-----------|--------|-----|----------|-----|",
            ])
            for structure, stats in today_breakdowns['by_structure'].items():
                lines.append(f"| {structure} | {stats['total_trades']} | {stats['wins']}/{stats['losses']} | {stats['win_rate']:.1%} | ${stats['total_pnl']:,.2f} |")
            lines.append("")
        
        # AI Insights
        if ai_response:
            if ai_response.get('insights'):
                lines.extend(["## Insights", ""])
                for insight in ai_response['insights']:
                    lines.append(f"- **{insight.get('type', 'observation')}**: {insight.get('text', '')}")
                lines.append("")
            
            if ai_response.get('recommendations'):
                lines.extend(["## Recommendations", ""])
                for i, rec in enumerate(ai_response['recommendations'], 1):
                    lines.append(f"### {i}. {rec.get('action', 'unknown')}")
                    lines.append(f"- **Scope**: {rec.get('scope', {})}")
                    lines.append(f"- **Change**: {rec.get('change', {})}")
                    lines.append(f"- **Why**: {rec.get('why', '')}")
                    lines.append(f"- **Confidence**: {rec.get('confidence', 'unknown')}")
                    lines.append(f"- **Reversal**: {rec.get('reversal_condition', '')}")
                    if rec.get('_guardrail_applied'):
                        lines.append(f"- **Guardrail**: {rec['_guardrail_applied']}")
                    lines.append("")
            
            if ai_response.get('warnings'):
                lines.extend(["## Warnings", ""])
                for warning in ai_response['warnings']:
                    severity = warning.get('severity', 'medium').upper()
                    lines.append(f"- **[{severity}]** {warning.get('text', '')}")
                lines.append("")
        
        # Detected patterns
        if patterns:
            lines.extend(["## Detected Patterns", ""])
            for p in patterns:
                lines.append(f"- **{p.get('type', 'pattern')}**: {p.get('text', '')}")
            lines.append("")
        
        return "\n".join(lines)
    
    def generate_report(self, date: datetime = None) -> Dict[str, Any]:
        """
        Generate a complete post-session report.
        
        Args:
            date: Date to analyze (defaults to today)
            
        Returns:
            Dict with 'markdown', 'json', 'success' keys
        """
        if date is None:
            date = datetime.now(timezone.utc)
        
        logger.info(f"Generating post-session report for {date.strftime('%Y-%m-%d')}")
        
        # Load data
        today_trades = self.load_trades(date)
        week_trades = self.load_trades_range(date, days=7)
        
        if not today_trades and not week_trades:
            return {
                'success': False,
                'error': 'No trades found for the specified period',
                'markdown': None,
                'json': None
            }
        
        # Compute summaries
        today_summary = self.compute_summary(today_trades)
        week_summary = self.compute_summary(week_trades)
        
        # Compute breakdowns
        today_breakdowns = self.compute_breakdowns(today_trades)
        week_breakdowns = self.compute_breakdowns(week_trades)
        
        # Find patterns
        patterns = self.find_patterns(week_trades)
        
        # Build prompt and call Ollama
        prompt = self.build_prompt(
            today_summary, week_summary,
            today_breakdowns, week_breakdowns,
            patterns, date
        )
        
        ai_response = self.call_ollama(prompt)
        if ai_response:
            ai_response = self.validate_recommendations(ai_response)
        
        # Generate outputs
        markdown = self.generate_markdown(
            date, today_summary, week_summary,
            today_breakdowns, patterns, ai_response
        )
        
        json_output = {
            'date': date.strftime('%Y-%m-%d'),
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'summary': {
                'today': asdict(today_summary),
                'week': asdict(week_summary)
            },
            'breakdowns': {
                'today': today_breakdowns,
                'week': week_breakdowns
            },
            'patterns': patterns,
            'ai_analysis': ai_response
        }
        
        # Save files
        date_str = date.strftime('%Y%m%d')
        md_path = os.path.join(self.reports_dir, f"post_session_{date_str}.md")
        json_path = os.path.join(self.reports_dir, f"post_session_{date_str}.json")
        
        try:
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(markdown)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_output, f, indent=2)
            
            logger.info(f"Report saved to {md_path} and {json_path}")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
        
        return {
            'success': True,
            'markdown': markdown,
            'json': json_output,
            'md_path': md_path,
            'json_path': json_path
        }
