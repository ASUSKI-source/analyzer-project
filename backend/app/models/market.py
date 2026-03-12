import uuid
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, UniqueConstraint, Integer, JSON
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
    technical_snapshots = relationship("AssetTechnicalSnapshot", back_populates="asset", cascade="all, delete-orphan")
    fundamental_snapshots = relationship("AssetFundamentalSnapshot", back_populates="asset", cascade="all, delete-orphan")
    event_snapshots = relationship("AssetEventSnapshot", back_populates="asset", cascade="all, delete-orphan")
    coverage_snapshots = relationship("AssetCoverageSnapshot", back_populates="asset", cascade="all, delete-orphan")


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


class AssetTechnicalSnapshot(Base):
    """
    Canonical technical indicator snapshot for a symbol/timeframe/as_of.
    """
    __tablename__ = "asset_technical_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    timeframe = Column(String, nullable=False, index=True)  # 1h,1d,1w,1m
    as_of = Column(DateTime(timezone=True), nullable=False, index=True)

    rsi_14 = Column(Float, nullable=True)
    macd_line = Column(Float, nullable=True)
    macd_signal = Column(Float, nullable=True)
    macd_histogram = Column(Float, nullable=True)
    ema_9 = Column(Float, nullable=True)
    ema_21 = Column(Float, nullable=True)
    sma_20 = Column(Float, nullable=True)
    sma_50 = Column(Float, nullable=True)
    sma_200 = Column(Float, nullable=True)
    trend_signal = Column(String, nullable=True)

    data_quality = Column(String, nullable=False, default="ok")
    source = Column(String, nullable=False, default="derived")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    asset = relationship("Asset", back_populates="technical_snapshots")

    __table_args__ = (
        UniqueConstraint("asset_id", "timeframe", "as_of", name="uix_asset_technical_snapshot"),
    )


class AssetFundamentalSnapshot(Base):
    """
    Canonical fundamental snapshot at a given as_of time.
    """
    __tablename__ = "asset_fundamental_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    as_of = Column(DateTime(timezone=True), nullable=False, index=True)

    market_cap = Column(Float, nullable=True)
    pe_ratio = Column(Float, nullable=True)
    dividend_yield = Column(Float, nullable=True)
    eps = Column(Float, nullable=True)
    high_52week = Column(Float, nullable=True)
    low_52week = Column(Float, nullable=True)
    beta = Column(Float, nullable=True)
    sector = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    description = Column(String, nullable=True)

    source = Column(String, nullable=False, default="finnhub")
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    asset = relationship("Asset", back_populates="fundamental_snapshots")

    __table_args__ = (
        UniqueConstraint("asset_id", "as_of", name="uix_asset_fundamental_snapshot"),
    )


class AssetEventSnapshot(Base):
    """
    Earnings/events/news snapshot rows for point-in-time context.
    """
    __tablename__ = "asset_event_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    event_time = Column(DateTime(timezone=True), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)  # earnings|news|macro
    headline = Column(String, nullable=True)
    sentiment_score = Column(Float, nullable=True)
    relevance_score = Column(Float, nullable=True)
    payload = Column(JSON, nullable=True)
    source = Column(String, nullable=False, default="finnhub")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    asset = relationship("Asset", back_populates="event_snapshots")

    __table_args__ = (
        UniqueConstraint("asset_id", "event_time", "event_type", "headline", name="uix_asset_event_snapshot"),
    )


class AssetCoverageSnapshot(Base):
    """
    Coverage/freshness ledger for observability and AI data gating.
    """
    __tablename__ = "asset_coverage_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    as_of = Column(DateTime(timezone=True), nullable=False, index=True)
    asset_type = Column(String, nullable=False)
    timeframe = Column(String, nullable=False, index=True)
    expected_field_count = Column(Integer, nullable=False, default=0)
    available_field_count = Column(Integer, nullable=False, default=0)
    coverage_score = Column(Float, nullable=False, default=0.0)
    freshness_seconds = Column(Integer, nullable=True)
    anomaly_flags = Column(JSON, nullable=True)
    source = Column(String, nullable=False, default="snapshot_pipeline")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    asset = relationship("Asset", back_populates="coverage_snapshots")

    __table_args__ = (
        UniqueConstraint("asset_id", "as_of", "timeframe", name="uix_asset_coverage_snapshot"),
    )
