import pytest


@pytest.mark.asyncio
async def test_rejects_unknown_service_fields(async_client):
    payload = {
        "name": "Invalid extra field",
        "source_protocol": "srt",
        "source_ip": "127.0.0.1",
        "source_port": 9901,
        "destination_url": "udp://239.10.10.10:5001",
        "enabled": False,
        "unexpected_field": "boom",
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rejects_invalid_destination_protocol(async_client):
    payload = {
        "name": "Invalid destination",
        "source_protocol": "srt",
        "source_ip": "127.0.0.1",
        "source_port": 9901,
        "destination_url": "file:///tmp/out.ts",
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rejects_invalid_key_size(async_client):
    payload = {
        "name": "Invalid key",
        "source_protocol": "srt",
        "source_ip": "127.0.0.1",
        "source_port": 9901,
        "destination_url": "udp://239.10.10.10:5001",
        "pbkeylen": 15,
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_accepts_node_specific_video_bindings(async_client):
    payload = {
        "name": "Node bindings",
        "source_protocol": "srt",
        "source_ip": "0.0.0.0",
        "source_port": 9901,
        "destination_url": "udp://239.10.10.10:5001",
        "ha_mode": "active_passive",
        "target_node": "primary",
        "failover_node": "backup",
        "node_bindings": {
            "primary": {"local_bind_ip": "10.50.1.21"},
            "backup": {"local_bind_ip": "10.50.1.22"},
        },
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["node_bindings"]["primary"]["local_bind_ip"] == "10.50.1.21"
    assert data["node_bindings"]["backup"]["local_bind_ip"] == "10.50.1.22"


@pytest.mark.asyncio
async def test_rejects_invalid_node_binding_fields(async_client):
    payload = {
        "name": "Bad node binding",
        "source_protocol": "srt",
        "source_ip": "0.0.0.0",
        "source_port": 9901,
        "destination_url": "udp://239.10.10.10:5001",
        "node_bindings": {
            "primary": {"local_bind_ip": "10.50.1.21", "extra": "nope"},
        },
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 422
