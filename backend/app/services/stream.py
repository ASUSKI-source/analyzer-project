import json
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Set, Dict, Any, Optional
import websockets
from app.core.config import settings
from app.core.cache import get_redis

logger = logging.getLogger(__name__)

class BaseStreamer(ABC):
    """Abstract base class for real-time market data streamers."""
    
    def __init__(self):
        self.active_symbols: Set[str] = set()
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self._redis = None

    @abstractmethod
    async def connect(self):
        """Establish connection to the provider."""
        pass

    @abstractmethod
    async def subscribe(self, symbol: str):
        """Subscribe to a specific symbol."""
        pass

    @abstractmethod
    async def unsubscribe(self, symbol: str):
        """Unsubscribe from a specific symbol."""
        pass

    async def start(self):
        """Start the background streaming task."""
        if self.is_running:
            return
        self.is_running = True
        self._redis = await get_redis()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"{self.__name__ if hasattr(self, '__name__') else self.__class__.__name__} started.")

    async def stop(self):
        """Stop the background streaming task."""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"{self.__name__ if hasattr(self, '__name__') else self.__class__.__name__} stopped.")

    @abstractmethod
    async def _run_loop(self):
        """Main loop for handling connection and messages."""
        pass

    async def broadcast(self, symbol: str, data: Dict[str, Any]):
        """Publish normalized data to Redis."""
        if self._redis:
            channel = f"ticker:{symbol}"
            await self._redis.publish(channel, json.dumps(data))

class FinnhubStreamer(BaseStreamer):
    """
    Finnhub WebSocket implementation.
    Unified stream for Stocks, Forex, and Crypto on free tier.
    """
    
    def __init__(self):
        super().__init__()
        self.api_key = settings.FINNHUB_API_KEY
        self.uri = f"wss://ws.finnhub.io?token={self.api_key}"
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._reconnect_delay = 1.0  # Initial delay for reconnect

    async def connect(self):
        """Connect to Finnhub WebSocket."""
        if not self.api_key:
            logger.error("FINNHUB_API_KEY is missing. Streaming disabled.")
            return False
        
        try:
            self._ws = await websockets.connect(self.uri)
            logger.info("Connected to Finnhub WebSocket.")
            # Resubscribe to active symbols on reconnect
            for sym in self.active_symbols:
                await self._send_subscription(sym)
            self._reconnect_delay = 1.0  # Reset delay on success
            return True
        except Exception as e:
            logger.error(f"Finnhub connection failed: {e}")
            return False

    async def _send_subscription(self, symbol: str):
        """Internal helper to send subscription message."""
        if self._ws:
            payload = {"type": "subscribe", "symbol": symbol}
            await self._ws.send(json.dumps(payload))
            logger.info(f"Subscribed to {symbol} on Finnhub.")

    async def subscribe(self, symbol: str):
        """External call to track and subscribe to a symbol."""
        if symbol not in self.active_symbols:
            self.active_symbols.add(symbol)
            if self._ws:
                await self._send_subscription(symbol)

    async def unsubscribe(self, symbol: str):
        """External call to stop tracking a symbol."""
        if symbol in self.active_symbols:
            self.active_symbols.remove(symbol)
            if self._ws:
                payload = {"type": "unsubscribe", "symbol": symbol}
                await self._ws.send(json.dumps(payload))
                logger.info(f"Unsubscribed from {symbol} on Finnhub.")

    async def _run_loop(self):
        """Handles connection persistence and message normalization."""
        while self.is_running:
            connected = await self.connect()
            if not connected:
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60.0)
                continue

            try:
                # Use while loop with recv() for more control over connection state
                while self.is_running:
                    message = await self._ws.recv()
                    data = json.loads(message)
                    if data.get("type") == "trade":
                        await self._process_trades(data["data"])
                    elif data.get("type") == "ping":
                        pass
            except websockets.ConnectionClosed:
                logger.warning("Finnhub WebSocket closed. Reconnecting...")
            except Exception as e:
                logger.error(f"Error in Finnhub stream loop: {e}")
                await asyncio.sleep(1)

    async def _process_trades(self, trades: list):
        """
        Normalize Finnhub trade data to our internal tick format.
        Finnhub format: [{'p': price, 's': symbol, 't': timestamp, 'v': volume}]
        """
        for trade in trades:
            symbol = trade['s']
            price = trade['p']
            timestamp = trade['t']
            
            # Normalize to our 'tick' format
            normalized = {
                "symbol": symbol,
                "price": price,
                "timestamp": timestamp,
                "type": "tick"
            }
            await self.broadcast(symbol, normalized)

# Singleton instance for consistent connection management
streamer = FinnhubStreamer()
