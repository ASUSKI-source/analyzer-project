import logging
import asyncio
from app.core.celery_app import celery_app
from app.services.market_data import sync_asset_history
from app.core.database import AsyncSessionLocal
from sqlalchemy import select
from app.models.market import Asset

logger = logging.getLogger(__name__)

async def _sync_all_assets_async():
    """
    Asynchronous workload to fetch all active assets and sync them.
    Security: Uses secure async DB sessions.
    Reversibility: Clean reads/writes relying on on_conflict_do_nothing.
    """
    logger.info("Starting background synchronization of all market assets.")
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Asset))
        assets = result.scalars().all()
        
        if not assets:
            logger.warning("No active assets found to sync.")
            return []

        synced = []
        for asset in assets:
            try:
                # Syncing 2 days of recent history daily to cover any gaps safely
                count = await sync_asset_history(db=session, symbol=asset.symbol, days=2)
                synced.append(f"{asset.symbol}: {count} candles")
            except Exception as e:
                # Observability constraint: Log gracefully, do not swallow completely 
                logger.error(f"Failed to sync asset {asset.symbol}: {str(e)}", exc_info=True)
                
        return synced

@celery_app.task(name="app.tasks.market_tasks.sync_all_assets_task")
def sync_all_assets_task():
    """
    Synchronous Celery wrapper to execute the async DB sync task securely.
    """
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(_sync_all_assets_async())
        return {"status": "success", "results": results}
    except Exception as e:
        # Observability constraint: surface all runner failures
        logger.error(f"Celery task wrapper failed: {e}", exc_info=True)
        raise
