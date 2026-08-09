import pytest

from backend.models import ServiceConfig
from worker import worker
from worker.worker import WorkerNode, should_run_on_node


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expires = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        if ex:
            self.expires[key] = ex
        return True

    async def get(self, key):
        return self.values.get(key)

    async def exists(self, key):
        return 1 if key in self.values else 0

    async def expire(self, key, ttl):
        if key not in self.values:
            return False
        self.expires[key] = ttl
        return True

    async def delete(self, key):
        self.values.pop(key, None)
        self.expires.pop(key, None)
        return 1


def make_config(target_node, **overrides):
    data = dict(
        id="svc-1",
        name="Routing test",
        source_protocol="srt",
        source_mode="caller",
        source_ip="127.0.0.1",
        source_port=9000,
        destination_url="udp://239.0.0.1:5000",
        target_node=target_node,
    )
    data.update(overrides)
    return ServiceConfig(
        **data
    )


def test_worker_runs_matching_node():
    assert should_run_on_node(make_config("worker_1"), "worker_1") is True


def test_worker_runs_all_target():
    assert should_run_on_node(make_config("all"), "worker_1") is True


def test_worker_ignores_other_worker_targets():
    assert should_run_on_node(make_config("worker_2"), "worker_1") is False
    assert should_run_on_node(make_config("backup_only"), "worker_1") is False


def test_active_passive_allows_preferred_and_failover_nodes():
    config = make_config("primary", ha_mode="active_passive", failover_node="backup")

    assert should_run_on_node(config, "primary") is True
    assert should_run_on_node(config, "backup") is True
    assert should_run_on_node(config, "worker_3") is False


@pytest.mark.asyncio
async def test_preferred_node_acquires_active_passive_lease(monkeypatch):
    monkeypatch.setattr(worker, "NODE_ROLE", "primary")
    node = WorkerNode()
    node.redis = FakeRedis()
    config = make_config(
        "primary",
        ha_mode="active_passive",
        failover_node="backup",
    )

    assert await node.ensure_active_passive_lease(config) is True
    assert await node.owns_lease(config.id) is True


@pytest.mark.asyncio
async def test_failover_node_waits_while_preferred_heartbeat_is_healthy(monkeypatch):
    monkeypatch.setattr(worker, "NODE_ROLE", "backup")
    node = WorkerNode()
    node.redis = FakeRedis()
    await node.redis.set("worker_heartbeat:primary", "alive", ex=10)
    config = make_config(
        "primary",
        ha_mode="active_passive",
        failover_node="backup",
        failover_after_seconds=5,
    )
    node.first_seen[config.id] = 0

    assert await node.ensure_active_passive_lease(config) is False


@pytest.mark.asyncio
async def test_failover_node_claims_after_preferred_heartbeat_missing(monkeypatch):
    monkeypatch.setattr(worker, "NODE_ROLE", "backup")
    node = WorkerNode()
    node.redis = FakeRedis()
    config = make_config(
        "primary",
        ha_mode="active_passive",
        failover_node="backup",
        failover_after_seconds=5,
    )
    node.first_seen[config.id] = 0

    assert await node.ensure_active_passive_lease(config) is True
    assert await node.owns_lease(config.id) is True
