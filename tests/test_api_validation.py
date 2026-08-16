import pytest
from api.main import eligible_worker_roles, service_has_eligible_worker


@pytest.mark.asyncio
async def test_interfaces_endpoint_returns_configured_inventory(async_client):
    response = await async_client.get("/api/interfaces")

    assert response.status_code == 200
    interfaces = response.json()["interfaces"]
    assert any(item["ip"] == "10.70.15.3" and "primary" in item["node_roles"] for item in interfaces)
    assert any(item["ip"] == "10.71.15.3" and "backup" in item["node_roles"] for item in interfaces)


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
async def test_rejects_missing_destination_when_hls_disabled(async_client):
    payload = {
        "name": "No output",
        "source_protocol": "srt",
        "source_ip": "127.0.0.1",
        "source_port": 9901,
        "destination_url": "",
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_accepts_hls_only_low_res_output(async_client):
    payload = {
        "name": "HLS only",
        "source_protocol": "srt",
        "source_ip": "127.0.0.1",
        "source_port": 9901,
        "destination_url": "",
        "enable_hls_preview": True,
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["destination_url"] == ""
    assert data["hls_outputs"]["low_res"]["enabled"] is True


@pytest.mark.asyncio
async def test_accepts_hls_source_url(async_client):
    payload = {
        "name": "HLS source",
        "source_protocol": "hls",
        "source_url": "https://example.com/live/stream.m3u8",
        "destination_url": "",
        "hls_outputs": {
            "low_res": {"enabled": True, "buffer_seconds": 10},
            "full_res": {"enabled": False, "buffer_seconds": 3600},
        },
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["source_protocol"] == "hls"
    assert data["source_url"] == "https://example.com/live/stream.m3u8"
    assert data["source_port"] is None


@pytest.mark.asyncio
async def test_rejects_hls_source_without_url(async_client):
    payload = {
        "name": "Bad HLS source",
        "source_protocol": "hls",
        "destination_url": "",
        "enable_hls_preview": True,
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rejects_full_hls_when_service_limit_is_reached(async_client, monkeypatch):
    monkeypatch.setenv("MAX_FULL_HLS_SERVICES", "1")
    payload = {
        "name": "Full HLS 1",
        "source_protocol": "srt",
        "source_ip": "127.0.0.1",
        "source_port": 9901,
        "destination_url": "",
        "hls_outputs": {
            "low_res": {"enabled": False, "buffer_seconds": 10},
            "full_res": {"enabled": True, "buffer_seconds": 3600},
        },
        "enabled": True,
    }

    first = await async_client.post("/api/services", json=payload)
    assert first.status_code == 200

    payload["name"] = "Full HLS 2"
    second = await async_client.post("/api/services", json=payload)

    assert second.status_code == 422
    assert "Full HLS service limit reached" in second.text


@pytest.mark.asyncio
async def test_full_hls_limit_counts_enabled_services_only(async_client, monkeypatch):
    monkeypatch.setenv("MAX_FULL_HLS_SERVICES", "1")
    payload = {
        "name": "Disabled Full HLS template 1",
        "source_protocol": "srt",
        "source_ip": "127.0.0.1",
        "source_port": 9901,
        "destination_url": "",
        "hls_outputs": {
            "low_res": {"enabled": False, "buffer_seconds": 10},
            "full_res": {"enabled": True, "buffer_seconds": 3600},
        },
        "enabled": False,
    }

    first = await async_client.post("/api/services", json=payload)
    assert first.status_code == 200

    payload["name"] = "Disabled Full HLS template 2"
    payload["source_port"] = 9902
    second = await async_client.post("/api/services", json=payload)

    assert second.status_code == 200


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
async def test_accepts_input_and_output_node_bindings(async_client):
    payload = {
        "name": "Split bindings",
        "source_protocol": "srt",
        "source_ip": "0.0.0.0",
        "source_port": 9901,
        "destination_url": "udp://239.10.10.10:5001",
        "target_node": "primary",
        "node_bindings": {
            "primary": {
                "input_bind_ip": "10.70.15.3",
                "output_bind_ip": "10.70.15.3",
            },
            "backup": {
                "input_bind_ip": "10.71.15.3",
                "output_bind_ip": "10.71.15.3",
            },
        },
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["node_bindings"]["primary"]["input_bind_ip"] == "10.70.15.3"
    assert data["node_bindings"]["backup"]["output_bind_ip"] == "10.71.15.3"


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


def test_active_passive_workers_are_eligible():
    config = {
        "target_node": "primary",
        "ha_mode": "active_passive",
        "failover_node": "backup",
    }

    assert eligible_worker_roles(config) == {"primary", "backup"}
    assert service_has_eligible_worker(config, {"backup"})


def test_all_target_still_requires_online_worker():
    config = {"target_node": "all", "ha_mode": "manual"}

    assert not service_has_eligible_worker(config, set())
    assert service_has_eligible_worker(config, {"worker_1"})


@pytest.mark.asyncio
async def test_enabled_service_without_matching_worker_reports_pending(async_client):
    payload = {
        "name": "No matching worker",
        "source_protocol": "srt",
        "source_ip": "127.0.0.1",
        "source_port": 9901,
        "destination_url": "udp://239.10.10.10:5001",
        "target_node": "primary",
        "enabled": True,
    }

    create_response = await async_client.post("/api/services", json=payload)
    assert create_response.status_code == 200

    response = await async_client.get("/api/services")

    assert response.status_code == 200
    service = response.json()[0]
    assert service["status"] == "pending_worker"
    assert "No eligible worker online" in service["error_msg"]
