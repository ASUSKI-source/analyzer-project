import logging
import json
import asyncio
from typing import Optional, Set, Any
from polygon import WebSocketClient
from app.core.config import settings
from app.core.cache import cache_client

logger = logging.getLogger(__name__)

class PolygonStreamer:
    """
    Stateful manager for the Polygon.io WebSocket connection.
    Maintains a single connection to Polygon and broadcasts ticks to Redis.
    """
    def __init__(self):
        self.api_key = settings.POLYGON_API_KEY
        self.client: Any = None
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self._active_subscriptions: Set[str] = set()

    async def start(self):
        if self.is_running:
            return
        
        if not self.api_key:
            logger.error("POLYGON_API_KEY not found. Streamer will not start.")
            return

        self.is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Polygon Streamer background task initialized.")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Polygon Streamer background task stopped.")

    def handle_msg(self, msg):
        """Callback for the Polygon client."""
        # Note: This usually runs in the client's thread or loop.
        # We need to bridge it to our Redis client.
        try:
            # Polygon messages are often list of dicts
            for m in msg:
                symbol = m.get("sym")
                if not symbol:
                    continue
                
                # Channel name: market_data:ticks:AAPL
                channel = f"market_data:ticks:{symbol}"
                
                # We use the sync-style redis publish if we are in a different thread,
                # but cache_client.client is usually an async connection.
                # Polygon StreamClient.run() can be blocking.
                
                # Let's ensure we handle this correctly.
                asyncio.run_coroutine_threadsafe(
                    cache_client.client.publish(channel, json.dumps(m)),
                    asyncio.get_event_loop()
                )
        except Exception as e:
            logger.error(f"Error processing Polygon message: {e}")

    async def _run_loop(self):
        """Internal loop to maintain the connection."""
        while self.is_running:
            try:
                # Initialize client
                self.client = WebSocketClient(
                    api_key=self.api_key
                )
                
                # If we have previous subscriptions, restore them
                if self._active_subscriptions:
                    subs = [f"A.{s}" for s in self._active_subscriptions]
                    self.client.subscribe(*subs)
                
                logger.info(f"Connecting to Polygon WebSocket... (Subs: {self._active_subscriptions})")
                
                # .run() is blocking and takes handle_msg as a callback.
                await asyncio.to_thread(self.client.run, self.handle_msg)
                
            except Exception as e:
                if self.is_running:
                    logger.error(f"Polygon Streamer connection lost: {e}. Retrying in 5s...")
                    await asyncio.sleep(5)
                else:
                    break

    async def subscribe(self, symbol: str):
        """Add a ticker to the active stream."""
        if symbol in self._active_subscriptions:
            return
            
        self._active_subscriptions.add(symbol)
        if self.client:
            # Note: We need to be careful about thread-safety here too
            # client.subscribe is usually safe but we check
            try:
                self.client.subscribe(f"A.{symbol}")
                logger.info(f"Subscribed to Polygon: A.{symbol}")
            except Exception as e:
                logger.error(f"Failed to subscribe to {symbol}: {e}")

    async def unsubscribe(self, symbol: str):
        """Remove a ticker if no one is watching."""
        if symbol not in self._active_subscriptions:
            return
            
        self._active_subscriptions.remove(symbol)
        if self.client:
            try:
                self.client.unsubscribe(f"A.{symbol}")
                logger.info(f"Unsubscribed from Polygon: A.{symbol}")
            except Exception as e:
                logger.error(f"Failed to unsubscribe from {symbol}: {e}")

# Global singleton
streamer = PolygonStreamer()
