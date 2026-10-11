import asyncio
import json

import pytest

from api.database import AsyncSessionLocal
from api.models import ServiceModel
import api.main as api_main


def payload(name, port=5500, enabled=True, service_id=""):
    return {
        "id": service_id,
        "name": name,
        "source_protocol": "udp",
        "source_mode": "listener",
        "source_ip": "239.10.10.10",
        "source_port": port,
        "source": {
            "protocol": "udp",
            "type": "multicast",
            "primary_endpoint": {
                "interface_id": "main-video",
                "bind_ip": "10.70.15.3",
                "address": "239.10.10.10",
                "port": port,
            },
        },
        "destination_url": "udp://239.20.20.20:6000",
        "node_bindings": {
            "primary": {"input_bind_ip": "10.70.15.3", "output_bind_ip": "10.70.15.3"},
        },
        "target_node": "primary",
        "enabled": enabled,
    }


@pytest.mark.asyncio
async def test_runtime_policy_endpoint(async_client):
    response = await async_client.get("/api/runtime-policy")
    assert response.status_code == 200
    assert response.json() == {"udp_multicast": {"min_port": 1024, "max_port": 65535}}


@pytest.mark.asyncio
async def test_runtime_policy_endpoint_honors_environment(async_client, monkeypatch):
    monkeypatch.setenv("UDP_MULTICAST_PORT_MIN", "2000")
    monkeypatch.setenv("UDP_MULTICAST_PORT_MAX", "12000")
    response = await async_client.get("/api/runtime-policy")
    assert response.status_code == 200
    assert response.json() == {"udp_multicast": {"min_port": 2000, "max_port": 12000}}


@pytest.mark.asyncio
async def test_enabled_multicast_bind_conflict_is_rejected(async_client):
    first = await async_client.post("/api/services", json=payload("First"))
    assert first.status_code == 200
    second = await async_client.post("/api/services", json=payload("Second"))
    assert second.status_code == 422
    assert "10.70.15.3:5500" in second.json()["detail"]
    assert "First" in second.json()["detail"]


@pytest.mark.asyncio
async def test_same_multicast_port_on_different_bind_ips_is_allowed(async_client):
    assert (await async_client.post("/api/services", json=payload("Main"))).status_code == 200
    backup = payload("Backup")
    backup["source"]["primary_endpoint"]["interface_id"] = "backup-video"
    backup["source"]["primary_endpoint"]["bind_ip"] = "10.71.15.3"
    backup["node_bindings"]["primary"]["input_bind_ip"] = "10.71.15.3"
    response = await async_client.post("/api/services", json=backup)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_disabled_multicast_templates_may_overlap(async_client):
    assert (await async_client.post("/api/services", json=payload("First", enabled=False))).status_code == 200
    assert (await async_client.post("/api/services", json=payload("Second", enabled=False))).status_code == 200


@pytest.mark.asyncio
async def test_disabled_multicast_template_still_requires_valid_configuration(async_client):
    data = payload("Invalid disabled", enabled=False)
    data["source"]["primary_endpoint"]["address"] = "10.1.1.1"
    data["source_ip"] = "10.1.1.1"
    response = await async_client.post("/api/services", json=data)
    assert response.status_code == 422
    assert "IPv4 multicast group" in response.json()["detail"]


@pytest.mark.asyncio
async def test_concurrent_conflicting_creates_admit_exactly_one(async_client):
    responses = await asyncio.gather(
        async_client.post("/api/services", json=payload("Concurrent first")),
        async_client.post("/api/services", json=payload("Concurrent second")),
    )
    assert sorted(response.status_code for response in responses) == [200, 422]


@pytest.mark.asyncio
async def test_all_target_rejects_when_backup_resolved_binding_is_ineligible(
    async_client,
    monkeypatch,
):
    inventory = [{
        "id": "main-video",
        "ip": "10.70.15.3",
        "purpose": "video",
        "directions": ["input", "output"],
        "node_roles": ["primary"],
        "network": "video",
    }]
    monkeypatch.setenv("INTERFACE_INVENTORY_JSON", json.dumps(inventory))
    data = payload("Incomplete all target")
    data["target_node"] = "all"
    response = await async_client.post("/api/services", json=data)
    assert response.status_code == 422
    assert "role backup" in response.json()["detail"]


@pytest.mark.asyncio
async def test_all_target_accepts_distinct_primary_and_backup_bindings(async_client):
    data = payload("Complete all target")
    data["target_node"] = "all"
    data["node_bindings"]["backup"] = {
        "input_bind_ip": "10.71.15.3",
        "output_bind_ip": "10.71.15.3",
    }
    response = await async_client.post("/api/services", json=data)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_legacy_worker_one_flat_multicast_remains_compatible(async_client):
    data = payload("Legacy worker")
    data["source"] = None
    data["target_node"] = "worker_1"
    data["node_bindings"] = {}
    data["local_bind_ip"] = "10.70.15.3"
    response = await async_client.post("/api/services", json=data)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_start_rechecks_multicast_bind_conflict(async_client):
    assert (await async_client.post("/api/services", json=payload("Running"))).status_code == 200
    waiting = await async_client.post("/api/services", json=payload("Waiting", enabled=False))
    response = await async_client.post(f"/api/services/{waiting.json()['id']}/start")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_enabled_update_rechecks_multicast_bind_conflict(async_client):
    assert (await async_client.post("/api/services", json=payload("Running"))).status_code == 200
    waiting = await async_client.post("/api/services", json=payload("Waiting", enabled=False))
    service_id = waiting.json()["id"]
    response = await async_client.put(
        f"/api/services/{service_id}",
        json=payload("Waiting", enabled=True, service_id=service_id),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_multicast_rejects_unicast_address(async_client):
    data = payload("Invalid")
    data["source"]["primary_endpoint"]["address"] = "10.1.1.1"
    data["source_ip"] = "10.1.1.1"
    response = await async_client.post("/api/services", json=data)
    assert response.status_code == 422
    assert "IPv4 multicast group" in response.json()["detail"]


@pytest.mark.asyncio
async def test_multicast_rejects_port_above_custom_policy(async_client, monkeypatch):
    monkeypatch.setenv("UDP_MULTICAST_PORT_MIN", "2000")
    monkeypatch.setenv("UDP_MULTICAST_PORT_MAX", "12000")
    response = await async_client.post("/api/services", json=payload("Invalid", port=12001))
    assert response.status_code == 422
    assert "between 2000 and 12000" in response.json()["detail"]


@pytest.mark.asyncio
async def test_multicast_rejects_management_interface(async_client):
    data = payload("Invalid management bind")
    data["source"]["primary_endpoint"]["interface_id"] = "management"
    data["source"]["primary_endpoint"]["bind_ip"] = "10.75.15.3"
    data["node_bindings"]["primary"]["input_bind_ip"] = "10.75.15.3"
    response = await async_client.post("/api/services", json=data)
    assert response.status_code == 422
    assert "not an eligible video interface" in response.json()["detail"]


@pytest.mark.asyncio
async def test_startup_quarantines_invalid_enabled_legacy_service(monkeypatch):
    invalid = payload("Invalid legacy")
    invalid["source"] = None
    invalid["source_ip"] = "239.10.10.10"
    invalid["source_port"] = 1023
    invalid["id"] = "invalid-legacy"
    async with AsyncSessionLocal() as session:
        session.add(ServiceModel(**invalid))
        await session.commit()

    class StartupRedis:
        def __init__(self):
            self.hashes = {}

        async def hset(self, name, key, value):
            self.hashes.setdefault(name, {})[key] = value

        async def hdel(self, name, key):
            self.hashes.setdefault(name, {}).pop(key, None)

        async def publish(self, channel, message):
            return 1

        async def close(self):
            return None

    client = StartupRedis()
    monkeypatch.setattr(api_main.redis, "from_url", lambda url: client)
    await api_main.startup()
    try:
        assert "invalid-legacy" not in client.hashes.get("service_configs", {})
        assert "invalid-legacy" in client.hashes["stream_metrics_cache"]
    finally:
        await api_main.shutdown()
