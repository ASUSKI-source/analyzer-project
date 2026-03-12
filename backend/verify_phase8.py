import asyncio
import logging
from datetime import datetime
from app.core.database import AsyncSessionLocal
from app.services.market_data import sync_asset_history, get_asset_history
from app.services.indicators import get_batch_indicators
from app.core.cache import cache_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("phase8_verify")

async def verify_intraday_persistence():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with AsyncSessionLocal() as db:
                symbol = "AAPL"
                logger.info(f"--- Verifying Phase 8: Intraday Persistence for {symbol} (Attempt {attempt+1}) ---")
                
                # 1. Test 5m sync
                logger.info("Syncing 5m data...")
                await sync_asset_history(db, symbol, days=1, timeframe="5m")
                
                # 2. Test 1h sync
                logger.info("Syncing 1h data...")
                await sync_asset_history(db, symbol, days=5, timeframe="1h")
                
                # 3. Retrieve from DB
                logger.info("Retrieving 5m data from DB...")
                candles_5m = await get_asset_history(db, symbol, days=1, timeframe="5m")
                logger.info(f"Fetched {len(candles_5m)} candles for 5m.")
                
                logger.info("Retrieving 1h data from DB...")
                candles_1h = await get_asset_history(db, symbol, days=5, timeframe="1h")
                logger.info(f"Fetched {len(candles_1h)} candles for 1h.")
                
                # 4. Check Indicator Cache
                logger.info("Checking multi-timeframe indicator batching...")
                batch_results = await get_batch_indicators([symbol], ["1h", "1d"], db)
                
                if batch_results[symbol].get("1h") and batch_results[symbol].get("1d"):
                    logger.info("SUCCESS: Multi-timeframe indicators generated.")
                else:
                    logger.error("FAILURE: Missing indicators for some timeframes.")
                
                logger.info("Phase 8 Verification Complete.")
                return # Exit on success
        except Exception as e:
            logger.error(f"Attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
            else:
                raise

if __name__ == "__main__":
    asyncio.run(verify_intraday_persistence())
