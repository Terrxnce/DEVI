"""
Data Loader — Switchable Source (Synthetic | MT5 | Cache)

Provides unified interface for loading OHLCV data from multiple sources.
Used by pipeline for Phase 1 (synthetic) → Phase 1.5 (MT5) transition.
"""

import logging
from typing import Dict, List, Optional
from enum import Enum
from datetime import datetime, timezone
import json
import os

logger = logging.getLogger(__name__)


class DataSource(Enum):
    """Data source types."""
    SYNTHETIC = "synthetic"
    MT5 = "mt5"
    CACHE = "cache"
    CSV = "csv"


class DataLoader:
    """
    Unified data loader with switchable sources.
    
    Supports:
    - Synthetic data generation (Phase 1 validation)
    - MT5 live feed (Phase 1.5+ production)
    - Cached data (backtest/replay)
    """
    
    def __init__(self, config: Dict):
        """
        Initialize data loader.
        
        Args:
            config: Data loader config
                {
                  "source": "synthetic|mt5|cache",
                  "synthetic": { ... },
                  "mt5": { ... },
                  "cache": { "path": "..." }
                }
        """
        self.config = config
        self.source = DataSource(config.get("source", "synthetic"))
        
        self.synthetic_config = config.get("synthetic", {})
        self.mt5_config = config.get("mt5", {})
        self.cache_config = config.get("cache", {})
        
        # Initialize source-specific handlers
        self.mt5_connector = None
        if self.source == DataSource.MT5:
            from ..broker.mt5_connector import MT5Connector
            self.mt5_connector = MT5Connector(self.mt5_config)
            if not self.mt5_connector.login():
                logger.error("MT5 login failed, falling back to synthetic")
                self.source = DataSource.SYNTHETIC
        
        logger.info("Data loader initialized", extra={"source": self.source.value})
    
    def fetch_ohlcv(self, symbol: str, timeframe: str, count: int) -> Optional[List[Dict]]:
        """
        Fetch OHLCV data from configured source.
        
        Args:
            symbol: Symbol name (e.g., "EURUSD")
            timeframe: Timeframe (e.g., "M15")
            count: Number of bars to fetch
        
        Returns:
            List of OHLCV dicts with UTC timestamps
        """
        if self.source == DataSource.SYNTHETIC:
            return self._fetch_synthetic(symbol, timeframe, count)
        elif self.source == DataSource.MT5:
            return self._fetch_mt5(symbol, timeframe, count)
        elif self.source == DataSource.CACHE:
            return self._fetch_cached(symbol, timeframe, count)
        elif self.source == DataSource.CSV:
            return self._fetch_csv(symbol, timeframe, count)
        else:
            logger.error("Unknown data source", extra={"source": self.source})
            return None
    
    def _fetch_synthetic(self, symbol: str, timeframe: str, count: int) -> List[Dict]:
        """
        Generate synthetic OHLCV data.
        
        Args:
            symbol: Symbol name
            timeframe: Timeframe
            count: Number of bars
        
        Returns:
            List of synthetic OHLCV dicts
        """
        from decimal import Decimal
        from datetime import timedelta
        
        bars = []
        base_price = Decimal(self.synthetic_config.get("base_price", "1.0950"))
        
        for i in range(count):
            # Generate timestamp (UTC)
            timestamp = datetime.now(timezone.utc) - timedelta(
                minutes=15 * (count - 1 - i)
            )
            
            # Simulate price movement
            price_change = Decimal(str((i % 20 - 10) * 0.00005))
            open_price = base_price + price_change
            close_price = open_price + Decimal(str((i % 5 - 2) * 0.0003))
            
            high_price = max(open_price, close_price) + Decimal("0.0008")
            low_price = min(open_price, close_price) - Decimal("0.0005")
            
            bar = {
                "timestamp": timestamp.isoformat() + "Z",
                "open": float(open_price),
                "high": float(high_price),
                "low": float(low_price),
                "close": float(close_price),
                "volume": 1000000,
            }
            bars.append(bar)
            base_price = close_price
        
        logger.info("Synthetic data generated", extra={
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": count
        })
        return bars
    
    def _fetch_mt5(self, symbol: str, timeframe: str, count: int) -> Optional[List[Dict]]:
        """
        Fetch OHLCV data from MT5.
        
        Args:
            symbol: Symbol name
            timeframe: Timeframe
            count: Number of bars
        
        Returns:
            List of OHLCV dicts or None
        """
        if not self.mt5_connector:
            logger.error("MT5 connector not initialized")
            return None
        
        # Subscribe to symbol
        if not self.mt5_connector.subscribe_symbol(symbol):
            logger.warning("Failed to subscribe to symbol", extra={"symbol": symbol})
            return None
        
        # Fetch OHLC data
        bars = self.mt5_connector.fetch_ohlc(symbol, timeframe, count)
        
        if bars:
            logger.info("MT5 data fetched", extra={
                "symbol": symbol,
                "timeframe": timeframe,
                "bars": len(bars)
            })
        
        return bars
    
    def _fetch_cached(self, symbol: str, timeframe: str, count: int) -> Optional[List[Dict]]:
        """
        Fetch OHLCV data from cache.
        
        Args:
            symbol: Symbol name
            timeframe: Timeframe
            count: Number of bars
        
        Returns:
            List of cached OHLCV dicts or None
        """
        cache_path = self.cache_config.get("path", "data/cache")
        cache_file = os.path.join(cache_path, f"{symbol}_{timeframe}.json")
        
        if not os.path.exists(cache_file):
            logger.warning("Cache file not found", extra={"file": cache_file})
            return None
        
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            bars = data.get("bars", [])[-count:]  # Get last N bars
            
            logger.info("Cached data loaded", extra={
                "symbol": symbol,
                "timeframe": timeframe,
                "bars": len(bars)
            })
            return bars
        
        except Exception as e:
            logger.error("Cache load error", extra={
                "file": cache_file,
                "error": str(e)
            })
            return None
    
    def cache_data(self, symbol: str, timeframe: str, bars: List[Dict]) -> bool:
        """
        Cache OHLCV data for later use.
        
        Args:
            symbol: Symbol name
            timeframe: Timeframe
            bars: List of OHLCV dicts
        
        Returns:
            True if caching successful
        """
        cache_path = self.cache_config.get("path", "data/cache")
        os.makedirs(cache_path, exist_ok=True)
        
        cache_file = os.path.join(cache_path, f"{symbol}_{timeframe}.json")
        
        try:
            data = {
                "symbol": symbol,
                "timeframe": timeframe,
                "cached_at": datetime.now(timezone.utc).isoformat() + "Z",
                "bars": bars,
            }
            
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            
            logger.info("Data cached", extra={
                "symbol": symbol,
                "timeframe": timeframe,
                "file": cache_file,
                "bars": len(bars)
            })
            return True
        
        except Exception as e:
            logger.error("Cache write error", extra={
                "file": cache_file,
                "error": str(e)
            })
            return False
    
    def switch_source(self, new_source: str) -> bool:
        """
        Switch data source at runtime.
        
        Args:
            new_source: New source ("synthetic", "mt5", or "cache")
        
        Returns:
            True if switch successful
        """
        try:
            new_source_enum = DataSource(new_source)
            
            if new_source_enum == DataSource.MT5 and not self.mt5_connector:
                from ..broker.mt5_connector import MT5Connector
                self.mt5_connector = MT5Connector(self.mt5_config)
                if not self.mt5_connector.login():
                    logger.error("MT5 login failed during source switch")
                    return False
            
            self.source = new_source_enum
            logger.info("Data source switched", extra={"source": new_source})
            return True
        
        except Exception as e:
            logger.error("Source switch error", extra={"error": str(e)})
            return False
    
    def _fetch_csv(self, symbol: str, timeframe: str, count: int) -> Optional[List[Dict]]:
        """
        Fetch OHLCV data from CSV file.
        
        Args:
            symbol: Symbol name
            timeframe: Timeframe
            count: Number of bars to fetch
        
        Returns:
            List of OHLCV dicts or None
        """
        try:
            import pandas as pd
            csv_path = self.config.get("csv_path", "infra/data/eurusd_m15_clean.csv")
            
            if not os.path.exists(csv_path):
                logger.error("CSV file not found", extra={"path": csv_path})
                return None
            
            df = pd.read_csv(csv_path)
            
            # Standardize column names
            df.columns = [c.strip().lower() for c in df.columns]
            
            # Parse timestamp
            time_col = next((c for c in ["timestamp_utc", "timestamp", "datetime"] if c in df.columns), None)
            if time_col is None:
                logger.error("No timestamp column found in CSV")
                return None
            
            df[time_col] = pd.to_datetime(df[time_col], utc=True)
            df = df.sort_values(time_col)
            
            # Get last N bars
            df = df.tail(count)
            
            # Convert to bar dicts
            bars = []
            for _, row in df.iterrows():
                bar = {
                    "timestamp": row[time_col].isoformat(),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0)),
                }
                bars.append(bar)
            
            logger.info("CSV data loaded", extra={
                "symbol": symbol,
                "timeframe": timeframe,
                "bars": len(bars),
                "path": csv_path
            })
            return bars
        
        except Exception as e:
            logger.error("CSV load error", extra={"error": str(e)})
            return None
    
    def get_source(self) -> str:
        """Get current data source."""
        return self.source.value
    
    def shutdown(self) -> None:
        """Shutdown data loader and close connections."""
        if self.mt5_connector:
            self.mt5_connector.logout()
        logger.info("Data loader shutdown")
