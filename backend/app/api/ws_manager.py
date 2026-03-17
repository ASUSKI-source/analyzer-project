import logging
import json
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set, List, Optional, Any
from app.core.cache import cache_client
from app.services.stream import streamer

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages active WebSocket connections and their symbol subscriptions.
    """
    def __init__(self):
        # Map of Symbol -> Set of connected WebSockets
        self.symbol_subscriptions: Dict[str, Set[WebSocket]] = {}
        # Map of WebSocket -> Set of Symbols they are watching
        self.client_subscriptions: Dict[WebSocket, Set[str]] = {}
        # Global relay task
        self._relay_task: Optional[asyncio.Task] = None
        self._is_running = False

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.client_subscriptions[websocket] = set()
        
        # Start the relay if this is the first connection
        if not self._is_running:
            self._is_running = True
            self._relay_task = asyncio.create_task(self._redis_relay_loop())
            logger.info("WebSocket Redis Relay loop started.")

    def disconnect(self, websocket: WebSocket):
        # Clean up subscriptions
        symbols = self.client_subscriptions.pop(websocket, set())
        for symbol in symbols:
            if symbol in self.symbol_subscriptions:
                self.symbol_subscriptions[symbol].discard(websocket)
                # If no one is watching this symbol anymore, tell Polygon
                if not self.symbol_subscriptions[symbol]:
                    del self.symbol_subscriptions[symbol]
                    asyncio.create_task(streamer.unsubscribe(symbol))
        
        logger.info(f"Client disconnected. Active symbols: {list(self.symbol_subscriptions.keys())}")

    async def subscribe(self, websocket: WebSocket, symbol: str):
        """Subscribe a client to a specific ticker."""
        symbol = symbol.upper()
        
        if websocket not in self.client_subscriptions:
            return

        # Update tracking
        self.client_subscriptions[websocket].add(symbol)
        if symbol not in self.symbol_subscriptions:
            self.symbol_subscriptions[symbol] = set()
            # First person to watch this symbol? Tell provider to start streaming it.
            # BaseStreamer.subscribe internalizes the symbol set management
            await streamer.subscribe(symbol)
            
        self.symbol_subscriptions[symbol].add(websocket)
        logger.info(f"Client subscribed to {symbol}. Total watchers: {len(self.symbol_subscriptions[symbol])}")

    async def unsubscribe(self, websocket: WebSocket, symbol: str):
        """Remove a subscription for a client."""
        symbol = symbol.upper()
        if websocket in self.client_subscriptions:
            self.client_subscriptions[websocket].discard(symbol)
            
        if symbol in self.symbol_subscriptions:
            self.symbol_subscriptions[symbol].discard(websocket)
            if not self.symbol_subscriptions[symbol]:
                del self.symbol_subscriptions[symbol]
                # Last person left? Unsubscribe from provider to save resources.
                await streamer.unsubscribe(symbol)

    async def _redis_relay_loop(self):
        """
        Background task that listens to ALL price updates in Redis 
        and pushes them to the relevant WebSockets.
        """
        if not cache_client.redis:
            logger.error("Redis client not initialized. Relay loop aborting.")
            return

        pubsub = cache_client.redis.pubsub()
        # We listen to a wildcard pattern for all market data ticks
        await pubsub.psubscribe("ticker:*")
        
        try:
            async for message in pubsub.listen():
                if not self._is_running:
                    break
                
                if message["type"] == "pmessage":
                    try:
                        # Channel looks like ticker:AAPL
                        channel = message["channel"]
                        if isinstance(channel, bytes):
                            channel = channel.decode("utf-8")
                        
                        symbol = channel.split(":")[-1]
                        data = json.loads(message["data"])
                        
                        # Find all clients watching this symbol
                        listeners = self.symbol_subscriptions.get(symbol, set())
                        if listeners:
                            # Push to all connected clients
                            dead_clients = []
                            for client in listeners:
                                try:
                                    await client.send_json({
                                        "type": "TICK",
                                        "symbol": symbol,
                                        "data": data  # This is the normalized tick from FinnhubStreamer
                                    })
                                except Exception:
                                    dead_clients.append(client)
                            
                            # Clean up dead clients if they weren't caught by disconnect
                            for dead in dead_clients:
                                self.disconnect(dead)
                                
                    except Exception as e:
                        logger.error(f"Error in Redis Relay push: {e}")
        finally:
            await pubsub.punsubscribe("ticker:*")
            self._is_running = False

# Global singleton
manager = ConnectionManager()
