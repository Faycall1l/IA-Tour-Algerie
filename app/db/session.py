from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

connect_args = {}
if settings.database.url and "sslmode=require" in settings.database.url:
    connect_args["ssl"] = "require"

engine = create_async_engine(
    settings.database.url,
    pool_size=settings.database.pool_size,
    max_overflow=settings.database.max_overflow,
    pool_pre_ping=settings.database.pool_pre_ping,
    pool_recycle=settings.database.pool_recycle,
    pool_timeout=settings.database.pool_timeout,
    echo=settings.debug,
    connect_args=connect_args,
)

async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session
