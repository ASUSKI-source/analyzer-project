
import asyncio
import os
import sys
from datetime import datetime

# Add the project root to sys.path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.api.routes.data import get_asset_analysis
from app.schemas.market import AssetAnalysisResponse
from unittest.mock import AsyncMock, MagicMock

async def run_diag(symbol="AAPL"):
    print(f"--- Diagnosing Analysis Data for {symbol} ---")
    
    # Mock DB and User
    db = AsyncMock()
    user = MagicMock()
    user.id = "test-user"
    
    try:
        # Call the endpoint function directly
        response = await get_asset_analysis(symbol=symbol, db=db, _current_user=user)
        
        print(f"Status: Success")
        print(f"Raw Technicals keys: {list(response.technicals.model_dump().keys()) if response.technicals else 'None'}")
        print(f"Raw Fundamentals keys: {list(response.fundamentals.model_dump().keys()) if response.fundamentals else 'None'}")
        
        print(f"Technicals RSI: {response.technicals.rsi}")
        print(f"Technicals Signal: {response.technicals.trend_signal}")
        print(f"Fundamentals P/E: {response.fundamentals.pe_ratio}")
        print(f"Fundamentals Market Cap: {response.fundamentals.market_cap}")
        print(f"Fundamentals Shares Float: {response.fundamentals.shares_float}")
        
        if response.on_chain:
            print(f"On-chain F&G: {response.on_chain.fear_and_greed.value if response.on_chain.fear_and_greed else 'None'}")
        else:
            print("On-chain: None")
            
        if response.institutional:
            print(f"Institutional Held: {response.institutional.shares_held}%")
        else:
            print("Institutional: None")
            
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_diag("AAPL"))
    asyncio.run(run_diag("BTC/USD"))
