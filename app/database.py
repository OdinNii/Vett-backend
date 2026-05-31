from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent column additions for existing tables (dev-friendly migrations).
        # PostgreSQL: ADD COLUMN IF NOT EXISTS is safe to run repeatedly.
        _migrations = [
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS autopilot_enabled BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS push_token VARCHAR(500)",
        ]
        for sql in _migrations:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass  # Column already exists, or non-PostgreSQL backend
