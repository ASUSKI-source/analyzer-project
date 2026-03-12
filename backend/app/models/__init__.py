# Import all models here to ensure they are loaded sequentially before Alembic runs
from app.models.base import Base
from app.models.user import User
from app.models.portfolio import Portfolio, Watchlist
from app.models.market import (
    Asset,
    AssetCandle,
    AssetTechnicalSnapshot,
    AssetFundamentalSnapshot,
    AssetEventSnapshot,
    AssetCoverageSnapshot,
)
