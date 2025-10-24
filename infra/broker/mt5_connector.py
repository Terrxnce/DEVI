"""
MT5 Connector — Real Broker Integration

Handles MT5 login, symbol subscription, OHLC data fetch, and UTC conversion.
Switchable with synthetic data source for Phase 1 validation.
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import json

logger = logging.getLogger(__name__)


class MT5Connector:
    """
    MT5 broker connection handler.
    
    Responsibilities:
    - Login to MT5 terminal
    - Subscribe to symbols
    - Fetch OHLCV data
    - Convert broker time to UTC
    - Handle connection errors
    """
    
    def __init__(self, config: Dict):
        """
        Initialize MT5 connector.
        
        Args:
            config: MT5 connection config
                {
                  "enabled": true,
                  "broker": "ICMarkets-Demo",
                  "server": "ICMarkets-Demo",
                  "account": 12345,
                  "password": "***",
                  "timezone": "GMT",
                  "timeout_seconds": 30
                }
        """
        self.config = config
        self.enabled = config.get("enabled", False)
        self.broker = config.get("broker", "")
        self.server = config.get("server", "")
        self.account = config.get("account", 0)
        self.password = config.get("password", "")
        self.broker_timezone = config.get("timezone", "GMT")
        self.timeout = config.get("timeout_seconds", 30)
        
        self.mt5 = None
        self.connected = False
        self.subscribed_symbols: Dict[str, bool] = {}
    
    def login(self) -> bool:
        """
        Login to MT5 terminal.
        
        Returns:
            True if login successful, False otherwise
        """
        if not self.enabled:
            logger.info("MT5 connector disabled")
            return False
        
        try:
            import MetaTrader5 as mt5
            self.mt5 = mt5
            
            # Initialize MT5
            if not mt5.initialize():
                logger.error("MT5 initialization failed", extra={
                    "error": mt5.last_error()
                })
                return False
            
            # Login
            if not mt5.login(self.account, self.password, self.server):
                logger.error("MT5 login failed", extra={
                    "account": self.account,
                    "server": self.server,
                    "error": mt5.last_error()
                })
                return False
            
            self.connected = True
            logger.info("MT5 login successful", extra={
                "broker": self.broker,
                "server": self.server,
                "account": self.account
            })
            return True
        
        except ImportError:
            logger.error("MetaTrader5 module not installed")
            return False
        except Exception as e:
            logger.error("MT5 login error", extra={"error": str(e)})
            return False
    
    def subscribe_symbol(self, symbol: str) -> bool:
        """
        Subscribe to a symbol for data updates.
        
        Args:
            symbol: Symbol name (e.g., "EURUSD")
        
        Returns:
            True if subscription successful
        """
        if not self.connected or not self.mt5:
            logger.warning("MT5 not connected, cannot subscribe", extra={
                "symbol": symbol
            })
            return False
        
        try:
            if not self.mt5.symbol_select(symbol, True):
                logger.warning("Failed to subscribe to symbol", extra={
                    "symbol": symbol,
                    "error": self.mt5.last_error()
                })
                return False
            
            self.subscribed_symbols[symbol] = True
            logger.info("Symbol subscribed", extra={"symbol": symbol})
            return True
        
        except Exception as e:
            logger.error("Symbol subscription error", extra={
                "symbol": symbol,
                "error": str(e)
            })
            return False
    
    def fetch_ohlc(self, symbol: str, timeframe: str, count: int) -> Optional[List[Dict]]:
        """
        Fetch OHLCV data from MT5.
        
        Args:
            symbol: Symbol name (e.g., "EURUSD")
            timeframe: Timeframe (e.g., "M15", "H1")
            count: Number of bars to fetch
        
        Returns:
            List of OHLCV dicts with UTC timestamps, or None on error
        """
        if not self.connected or not self.mt5:
            logger.error("MT5 not connected")
            return None
        
        try:
            # Map timeframe string to MT5 constant
            tf_map = {
                "M1": self.mt5.TIMEFRAME_M1,
                "M5": self.mt5.TIMEFRAME_M5,
                "M15": self.mt5.TIMEFRAME_M15,
                "M30": self.mt5.TIMEFRAME_M30,
                "H1": self.mt5.TIMEFRAME_H1,
                "H4": self.mt5.TIMEFRAME_H4,
                "D1": self.mt5.TIMEFRAME_D1,
            }
            
            if timeframe not in tf_map:
                logger.error("Unsupported timeframe", extra={"timeframe": timeframe})
                return None
            
            mt5_timeframe = tf_map[timeframe]
            
            # Fetch bars
            rates = self.mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, count)
            
            if rates is None or len(rates) == 0:
                logger.warning("No data returned from MT5", extra={
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "count": count
                })
                return None
            
            # Convert to UTC and format
            bars = []
            for rate in rates:
                # rate is a tuple: (time, open, high, low, close, tick_volume, spread, real_volume)
                broker_time = datetime.fromtimestamp(rate[0])
                utc_time = self._convert_to_utc(broker_time)
                
                bar = {
                    "timestamp": utc_time.isoformat() + "Z",
                    "open": float(rate[1]),
                    "high": float(rate[2]),
                    "low": float(rate[3]),
                    "close": float(rate[4]),
                    "volume": int(rate[6]),  # real_volume
                }
                bars.append(bar)
            
            logger.info("OHLC data fetched", extra={
                "symbol": symbol,
                "timeframe": timeframe,
                "bars": len(bars)
            })
            return bars
        
        except Exception as e:
            logger.error("OHLC fetch error", extra={
                "symbol": symbol,
                "timeframe": timeframe,
                "error": str(e)
            })
            return None
    
    def _convert_to_utc(self, broker_time: datetime) -> datetime:
        """
        Convert broker time to UTC.
        
        Args:
            broker_time: Time from broker (assumed to be in broker_timezone)
        
        Returns:
            UTC datetime
        """
        # TODO: Implement timezone conversion based on broker_timezone
        # For now, assume broker time is already UTC
        if broker_time.tzinfo is None:
            return broker_time.replace(tzinfo=timezone.utc)
        return broker_time.astimezone(timezone.utc)
    
    def logout(self) -> bool:
        """
        Logout from MT5.
        
        Returns:
            True if logout successful
        """
        if not self.connected or not self.mt5:
            return False
        
        try:
            self.mt5.shutdown()
            self.connected = False
            logger.info("MT5 logout successful")
            return True
        except Exception as e:
            logger.error("MT5 logout error", extra={"error": str(e)})
            return False
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """
        Get symbol info from MT5.
        
        Args:
            symbol: Symbol name
        
        Returns:
            Symbol info dict or None
        """
        if not self.connected or not self.mt5:
            return None
        
        try:
            info = self.mt5.symbol_info(symbol)
            if info is None:
                return None
            
            return {
                "symbol": info.name,
                "bid": float(info.bid),
                "ask": float(info.ask),
                "point": float(info.point),
                "digits": int(info.digits),
                "volume_min": float(info.volume_min),
                "volume_max": float(info.volume_max),
                "volume_step": float(info.volume_step),
                "spread": float(info.spread),
            }
        except Exception as e:
            logger.error("Symbol info error", extra={
                "symbol": symbol,
                "error": str(e)
            })
            return None
