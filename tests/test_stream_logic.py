import pytest

from backend import stream_manager
from backend.models import ServiceConfig, ServiceState


@pytest.mark.asyncio
async def test_strict_probing_injection(async_client):
    payload = {
        "name": "Strict Probing SRT Stream",
        "source_protocol": "srt",
        "source_ip": "10.0.0.9",
        "source_port": 8800,
        "destination_url": "udp://239.0.0.2:5000",
        "enabled": True,
        "strict_probing": True,
        "auto_failover": True,
        "backup_input_ip": "10.0.0.10"
    }
    
    response = await async_client.post("/api/services", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["strict_probing"] is True
    assert data["auto_failover"] is True
    assert data["backup_input_ip"] == "10.0.0.10"
    service_id = data["id"]
    
    # Send a simulated PUT update mapping to stop and start explicitly
    payload["name"] = "Strict Probing Update"
    update_response = await async_client.put(f"/api/services/{service_id}", json=payload)
    assert update_response.status_code == 200
    
    del_resp = await async_client.delete(f"/api/services/{service_id}")
    assert del_resp.status_code == 200


@pytest.mark.asyncio
async def test_legacy_stream_manager_passes_node_role_to_ffmpeg_builder(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setattr(stream_manager, "CONFIG_FILE", str(tmp_path / "config.json"))

    def fake_build_ffmpeg_command(config, input_url, preview_dir, node_role="primary"):
        captured["node_role"] = node_role
        return ["true"]

    class FakeProcess:
        def __init__(self):
            self.pid = 1234
            self.returncode = None

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess()

    async def fake_monitor_process(self, service_id):
        return None

    monkeypatch.setattr(stream_manager, "build_ffmpeg_command", fake_build_ffmpeg_command)
    monkeypatch.setattr(stream_manager.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(stream_manager.StreamManager, "monitor_process", fake_monitor_process)

    manager = stream_manager.StreamManager()
    manager.node_role = "backup"
    config = ServiceConfig(
        id="legacy-bind-test",
        name="Legacy bind test",
        source_protocol="srt",
        source_mode="caller",
        source_ip="127.0.0.1",
        source_port=9000,
        destination_url="udp://239.0.0.1:5000",
        target_node="backup",
    )
    manager.services[config.id] = ServiceState(config=config)

    await manager.start_service(config.id)

    assert captured["node_role"] == "backup"
