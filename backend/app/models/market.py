import uuid
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base

class Asset(Base):
    """
    Represents a tradable stock or cryptocurrency.
    """
    __tablename__ = "assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String, unique=True, index=True, nullable=False) # e.g. 'AAPL', 'BTC-USD'
    name = Column(String, nullable=False)
    asset_type = Column(String, nullable=False) # 'stock' or 'crypto'
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    candles = relationship("AssetCandle", back_populates="asset", cascade="all, delete-orphan")


class AssetCandle(Base):
    """
    Represents a single time-series data point (candlestick) for an asset.
    Designed to be compatible with TimescaleDB hypertables.
    """
    __tablename__ = "asset_candles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # TimescaleDB requires the time column to be indexed and ideally part of the primary key conceptually,
    # but for SQLAlchemy compatibility, we keep a surrogate UUID and index the timestamp heavily.
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # resolution/timeframe: '5m', '1h', '1d', '1w'
    timeframe = Column(String, default="1d", nullable=False, index=True)
    
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    asset = relationship("Asset", back_populates="candles")

    # Ensure we don't store duplicate candles for the same exact time, asset, and resolution
    __table_args__ = (
        UniqueConstraint('asset_id', 'timestamp', 'timeframe', name='uix_asset_timestamp_tf'),
    )
