import logging
import json
import re
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.api.ws_manager import manager
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# Security: Regex for valid ticker symbols (Crypto or Stocks)
# Allows: BINANCE:BTCUSDT, AAPL, BTC-USD, etc.
SYMBOL_REGEX = re.compile(r"^[A-Z0-9\:\-\.]{1,20}$")

@router.websocket("/ohlc")
async def websocket_endpoint(websocket: WebSocket):
    """
    Main entry point for the frontend's real-time price feed.
    """
    # Security: Origin Validation
    origin = websocket.headers.get("origin")
    allowed_origin = settings.FRONTEND_URL

    # In development, we might allow localhost variations
    if allowed_origin and origin and origin != allowed_origin:
        if not ("localhost" in origin and "localhost" in allowed_origin):
            logger.warning(f"Blocked WebSocket connection from unauthorized origin: {origin}")
            await websocket.close(code=1008)
            return

    await manager.connect(websocket)
    try:
        while True:
            # Wait for any incoming control messages from the client
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type")
                symbol = msg.get("symbol", "").upper()

                # Security: Symbol Sanitization
                if not symbol or not SYMBOL_REGEX.match(symbol):
                    logger.warning(f"Invalid symbol requested: {symbol}")
                    continue

                if msg_type == "SUBSCRIBE":
                    await manager.subscribe(websocket, symbol)
                elif msg_type == "UNSUBSCRIBE":
                    await manager.unsubscribe(websocket, symbol)

            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Unexpected error in WebSocket session: {e}")
        manager.disconnect(websocket)
