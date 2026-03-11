from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings

# Docs: We must ensure the database URL uses the asyncpg driver, required by FastAPI's async paradigms
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://") if settings.DATABASE_URL.startswith("postgresql://") else settings.DATABASE_URL

# Engine is configured for async I/O
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=False,
    future=True
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db():
    """Dependency used in FastAPI routes to inject a DB session per request."""
    async with AsyncSessionLocal() as session:
        yield session
