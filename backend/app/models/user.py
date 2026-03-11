import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base

# Many-to-Many association table for Users saving Assets to their Watchlist
user_watchlist_association = Table(
    'user_watchlists',
    Base.metadata,
    Column('user_id', UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('asset_id', UUID(as_uuid=True), ForeignKey('assets.id', ondelete='CASCADE'), primary_key=True),
    Column('added_at', DateTime(timezone=True), server_default=func.now())
)

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_premium = Column(Boolean, default=False)  # Future capability for advanced AI features
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship to the Asset model using string references to avoid circular imports
    watchlist_assets = relationship("Asset", secondary=user_watchlist_association, backref="watchers")
