from types import SimpleNamespace

import pytest

from api.multicast_admission import (
    MULTICAST_ADMISSION_LOCK_KEY,
    multicast_admission_guard,
)


class FakeSession:
    def __init__(self, dialect_name):
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))
        self.executed = []

    def get_bind(self):
        return self.bind

    async def execute(self, statement, parameters):
        self.executed.append((str(statement), parameters))


@pytest.mark.asyncio
async def test_postgresql_admission_uses_transaction_scoped_advisory_lock():
    session = FakeSession("postgresql")
    async with multicast_admission_guard(session):
        pass
    assert session.executed == [(
        "SELECT pg_advisory_xact_lock(:key)",
        {"key": MULTICAST_ADMISSION_LOCK_KEY},
    )]


@pytest.mark.asyncio
async def test_sqlite_admission_uses_only_local_lock():
    session = FakeSession("sqlite")
    async with multicast_admission_guard(session):
        pass
    assert session.executed == []
