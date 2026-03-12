from fastapi import APIRouter
from app.api.routes import health, data, auth, watchlist, users, ai, websockets, portfolio

api_router = APIRouter()

# Register all sub-routers here
# By grouping them under api_router, we prefix them all with /api/v1 in main.py
api_router.include_router(health.router, prefix="/system", tags=["System"])
api_router.include_router(data.router, prefix="/market", tags=["Market Data"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(watchlist.router, prefix="/watchlist", tags=["Watchlist"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(portfolio.router, prefix="/portfolio", tags=["Portfolio"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI Analysis"])
api_router.include_router(websockets.router, prefix="/ws", tags=["WebSockets"])

