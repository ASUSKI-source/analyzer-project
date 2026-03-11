from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db

router = APIRouter()

@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Basic health check to ensure the API and Database are functioning.
    """
    db_status = "offline"
    try:
        # Test DB connection via the dependency injection
        await db.execute(text("SELECT 1"))
        db_status = "online"
    except Exception as e:
        # Ignore for health check, the DB might be unreachable
        db_status = f"offline (error)"
        
    return {
        "status": "ok",
        "api": "online",
        "database": db_status
    }

@router.get("/error-test")
async def error_test():
    """Dummy endpoint to test our global exception handler according to CONVENTIONS."""
    from app.core.errors import AssetNotFoundException
    raise AssetNotFoundException(message="The ticker AAPL is not supported in the free tier.")
