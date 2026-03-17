import uuid
from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.models.base import Base

class Portfolio(Base):
    __tablename__ = "portfolios"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    user = relationship("User", backref="portfolios")

# Many-to-Many association table for Watchlists saving Assets
from sqlalchemy import Table, Column, Integer, String, ForeignKey, DateTime
from app.models.market import Asset

watchlist_asset_association = Table(
    'watchlist_assets',
    Base.metadata,
    Column('watchlist_id', UUID(as_uuid=True), ForeignKey('watchlists.id', ondelete='CASCADE'), primary_key=True),
    Column('asset_id', UUID(as_uuid=True), ForeignKey('assets.id', ondelete='CASCADE'), primary_key=True),
    Column('added_at', DateTime(timezone=True), server_default=func.now()),
    extend_existing=True
)

class Watchlist(Base):
    __tablename__ = "watchlists"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship to Assets
    assets = relationship("Asset", secondary=watchlist_asset_association, backref="watchlists")
    user = relationship("User", back_populates="watchlists")
