"""Database session management — async SQLAlchemy 2.0."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_timeout=10,
    echo=False,
    # 15s per-statement timeout enforced at the asyncpg session level. Caps
    # the blast radius of any pathological JIP query so it can no longer
    # cascade-fail the API via QueuePool starvation.
    connect_args={
        "server_settings": {
            "statement_timeout": "15000",
            "application_name": "atlas-backend",
        },
    },
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI route handlers."""
    async with async_session_factory() as session:
        yield session
