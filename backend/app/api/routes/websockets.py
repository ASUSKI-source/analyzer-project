import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.api.ws_manager import manager

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ohlc")
async def websocket_endpoint(websocket: WebSocket):
    """
    Main entry point for the frontend's real-time price feed.
    Commands:
    - {"type": "SUBSCRIBE", "symbol": "AAPL"}
    - {"type": "UNSUBSCRIBE", "symbol": "AAPL"}
    """
    await manager.connect(websocket)
    try:
        while True:
            # Wait for any incoming control messages from the client
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type")
                symbol = msg.get("symbol")
                
                if not symbol:
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

import json # Ensure json is imported
