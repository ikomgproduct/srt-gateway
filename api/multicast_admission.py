import asyncio
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# Application-owned PostgreSQL advisory lock for enabled multicast bind claims.
MULTICAST_ADMISSION_LOCK_KEY = 0x5352544D43415354
_local_admission_lock = asyncio.Lock()


@asynccontextmanager
async def multicast_admission_guard(session: AsyncSession):
    async with _local_admission_lock:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": MULTICAST_ADMISSION_LOCK_KEY},
            )
        yield
