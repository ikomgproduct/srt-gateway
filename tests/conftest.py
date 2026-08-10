import pytest
import os
import pytest_asyncio
from httpx import AsyncClient

# 1. Hijack the global environment database strictly onto a volatile SQLite memory matrix
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from api.main import app
from api.database import engine, Base

@pytest.fixture(scope="session")
def event_loop():
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    # Instantiates the underlying relational structural database natively bypassing physical PSQL
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def async_client():
    # Lightning-fast ASGI routing dynamically bypassing absolute network socket architectures
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client

# 2. Block FastAPI from trying to dial physical Redis container clusters perfectly
@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    class DummyRedis:
        def __init__(self):
            self.hashes = {}

        async def close(self): pass
        async def publish(self, channel, message): return 1
        async def hget(self, name, key):
            return self.hashes.get(name, {}).get(key)
        async def hset(self, name, key, value):
            self.hashes.setdefault(name, {})[key] = value
            return 1
        async def hdel(self, name, key):
            self.hashes.setdefault(name, {}).pop(key, None)
            return 1
        async def scan_iter(self, pattern):
            if False:
                yield pattern
        
    import api.main
    monkeypatch.setattr(api.main, "redis_client", DummyRedis())
