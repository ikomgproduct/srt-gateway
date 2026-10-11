import pytest

from backend.models import ServiceConfig
from backend.multicast_policy import config_fingerprint
from worker.worker import WorkerNode, classify_ffmpeg_error


def config(port=5500):
    return ServiceConfig(
        id="svc-1",
        name="Multicast",
        source_protocol="udp",
        source_ip="239.1.1.1",
        source_port=port,
        source={
            "protocol": "udp",
            "type": "multicast",
            "primary_endpoint": {"address": "239.1.1.1", "port": port},
        },
        node_bindings={"primary": {"input_bind_ip": "10.70.15.3"}},
        destination_url="udp://239.2.2.2:6000",
        target_node="primary",
    )


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("bind failed: Address already in use", "port_in_use"),
        ("Cannot assign requested address", "invalid_bind_interface"),
        ("Failed to join multicast group", "multicast_join_failed"),
    ],
)
def test_ffmpeg_stable_error_classification(message, code):
    assert classify_ffmpeg_error(message) == (code, False)


def test_unknown_ffmpeg_error_remains_retryable():
    assert classify_ffmpeg_error("temporary input timeout") == (None, True)


@pytest.mark.asyncio
async def test_reconcile_suppresses_unchanged_non_retryable_config(monkeypatch):
    monkeypatch.setattr("worker.worker.NODE_ROLE", "primary")
    worker = WorkerNode()
    candidate = config()
    worker.state[candidate.id] = {
        "config": candidate,
        "status": "error",
        "retryable": False,
        "config_fingerprint": config_fingerprint(candidate),
    }
    calls = []

    async def fake_start(current, use_backup=False):
        calls.append(current)

    monkeypatch.setattr(worker, "start_service", fake_start)
    await worker.reconcile_service(candidate)
    assert calls == []

    changed = config(port=5501)
    await worker.reconcile_service(changed)
    assert calls == [changed]


@pytest.mark.asyncio
async def test_explicit_start_forces_one_retry(monkeypatch):
    monkeypatch.setattr("worker.worker.NODE_ROLE", "primary")
    worker = WorkerNode()
    candidate = config()
    worker.state[candidate.id] = {
        "config": candidate,
        "status": "error",
        "retryable": False,
        "config_fingerprint": config_fingerprint(candidate),
    }
    calls = []

    async def fake_start(current, use_backup=False):
        calls.append(current)

    monkeypatch.setattr(worker, "start_service", fake_start)
    await worker.reconcile_service(candidate, force_retry=True)
    assert calls == [candidate]


@pytest.mark.asyncio
async def test_worker_preflight_rejects_missing_local_interface(monkeypatch):
    monkeypatch.setattr("worker.worker.NODE_ROLE", "primary")
    monkeypatch.setattr("worker.worker.local_ipv4_addresses", lambda: {"127.0.0.1"})
    worker = WorkerNode()

    async def no_publish(service_id):
        return None

    monkeypatch.setattr(worker, "publish_service_state", no_publish)
    await worker.start_service(config())
    assert worker.state["svc-1"]["status"] == "error"
    assert worker.state["svc-1"]["error_code"] == "invalid_bind_interface"
    assert worker.state["svc-1"]["retryable"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stderr_line", "expected_code"),
    [
        ("udp bind failed: Address already in use", "port_in_use"),
        ("Cannot assign requested address", "invalid_bind_interface"),
        ("Failed to join multicast group", "multicast_join_failed"),
    ],
)
async def test_monitor_publishes_stable_ffmpeg_network_error(monkeypatch, stderr_line, expected_code):
    worker = WorkerNode()
    candidate = config()

    class FakeStderr:
        def __init__(self):
            self.lines = [stderr_line.encode(), b""]

        async def readline(self):
            return self.lines.pop(0)

    class FakeProcess:
        def __init__(self):
            self.stderr = FakeStderr()
            self.returncode = 1

        async def wait(self):
            return self.returncode

        def kill(self):
            self.returncode = 1

    worker.processes[candidate.id] = FakeProcess()
    worker.state[candidate.id] = {
        "config": candidate,
        "status": "running",
        "active_input": "main",
        "bitrate": 0,
        "cc": 0,
        "error_msg": "",
        "error_code": None,
        "retryable": True,
        "config_fingerprint": config_fingerprint(candidate),
        "enabled": True,
    }

    published = []

    async def fake_publish(service_id):
        published.append(service_id)

    monkeypatch.setattr(worker, "publish_service_state", fake_publish)
    await worker.monitor_process(candidate.id, "udp://239.1.1.1:5500")

    assert published == [candidate.id]
    assert worker.state[candidate.id]["status"] == "error"
    assert worker.state[candidate.id]["error_msg"] == stderr_line
    assert worker.state[candidate.id]["error_code"] == expected_code
    assert worker.state[candidate.id]["retryable"] is False
