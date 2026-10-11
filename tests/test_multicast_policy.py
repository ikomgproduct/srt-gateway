from urllib.parse import parse_qs, urlsplit

import pytest

from api.route_normalizer import normalize_service_payload
from backend.ffmpeg_builder import build_input_url
from backend.models import ServiceConfig
from backend.multicast_policy import (
    MulticastPolicyError,
    config_fingerprint,
    eligible_roles,
    is_ipv4_multicast,
    multicast_bind_keys,
    multicast_port_policy,
    resolve_input_bind_ip,
    validate_multicast_config,
)


def multicast_config(port=5500):
    return {
        "id": "svc-1",
        "name": "Multicast",
        "source_protocol": "udp",
        "source_ip": "239.10.10.10",
        "source_port": port,
        "source": {
            "protocol": "udp",
            "type": "multicast",
            "primary_endpoint": {
                "address": "239.10.10.10",
                "port": port,
                "bind_ip": "10.75.51.40",
            },
        },
        "destination_url": "udp://239.20.20.20:6000",
        "node_bindings": {
            "primary": {"input_bind_ip": "10.70.15.3"},
            "backup": {"input_bind_ip": "10.71.15.3"},
        },
        "target_node": "primary",
    }


def test_ipv4_multicast_detection():
    assert is_ipv4_multicast("239.1.2.3")
    assert not is_ipv4_multicast("10.0.0.1")
    assert not is_ipv4_multicast("not-an-ip")
    assert not is_ipv4_multicast("ff02::1")


def test_legacy_flat_udp_multicast_is_inferred():
    normalized = normalize_service_payload(multicast_config() | {"source": None})
    assert normalized["source"]["type"] == "multicast"


@pytest.mark.parametrize("port", [1024, 65535])
def test_multicast_policy_accepts_boundaries(port):
    assert validate_multicast_config(multicast_config(port), role="primary")[1] == port


def test_multicast_policy_rejects_port_below_policy():
    with pytest.raises(MulticastPolicyError) as exc:
        validate_multicast_config(multicast_config(1023), role="primary")
    assert exc.value.code == "port_out_of_policy"


def test_multicast_policy_env_is_validated(monkeypatch):
    monkeypatch.setenv("UDP_MULTICAST_PORT_MIN", "9000")
    monkeypatch.setenv("UDP_MULTICAST_PORT_MAX", "8000")
    with pytest.raises(RuntimeError):
        multicast_port_policy()


def test_multicast_policy_env_must_be_numeric(monkeypatch):
    monkeypatch.setenv("UDP_MULTICAST_PORT_MIN", "not-a-port")
    with pytest.raises(RuntimeError, match="must be integers"):
        multicast_port_policy()


def test_role_binding_precedence_and_bind_keys():
    config = multicast_config()
    assert resolve_input_bind_ip(config, "primary") == "10.70.15.3"
    assert resolve_input_bind_ip(config, "backup") == "10.71.15.3"
    config["target_node"] = "all"
    assert multicast_bind_keys(config) == {("10.70.15.3", 5500), ("10.71.15.3", 5500)}


@pytest.mark.parametrize("bindings", [{}, {"primary": {}}, {"backup": {}}, {"custom": {}}])
def test_all_always_requires_primary_and_backup(bindings):
    config = multicast_config()
    config["target_node"] = "all"
    config["node_bindings"] = bindings
    assert eligible_roles(config) == ["primary", "backup"]


def test_exact_interface_identity_rejects_ip_mismatch():
    config = multicast_config()
    config["source"]["primary_endpoint"]["interface_id"] = "main-video"
    inventory = [{
        "id": "main-video",
        "ip": "10.70.15.99",
        "purpose": "video",
        "directions": ["input"],
        "node_roles": ["primary"],
    }]
    with pytest.raises(MulticastPolicyError, match="requires bind IP"):
        validate_multicast_config(config, role="primary", inventory=inventory)


@pytest.mark.parametrize("purpose,directions", [("management", []), ("video", ["output"])])
def test_exact_interface_identity_rejects_non_input_video_interface(purpose, directions):
    config = multicast_config()
    config["source"]["primary_endpoint"]["interface_id"] = "selected"
    inventory = [{
        "id": "selected",
        "ip": "10.75.51.40",
        "purpose": purpose,
        "directions": directions,
        "node_roles": ["primary"],
    }]
    with pytest.raises(MulticastPolicyError, match="not an eligible video interface"):
        validate_multicast_config(config, role="primary", inventory=inventory)


@pytest.mark.parametrize("inventory", [[], [
    {"id": "selected", "ip": "10.75.51.40", "purpose": "video", "directions": ["input"]},
    {"id": "selected", "ip": "10.75.51.40", "purpose": "video", "directions": ["input"]},
]])
def test_exact_interface_identity_rejects_unknown_or_duplicate_id(inventory):
    config = multicast_config()
    config["source"]["primary_endpoint"]["interface_id"] = "selected"
    with pytest.raises(MulticastPolicyError, match="configured interface inventory"):
        validate_multicast_config(config, role="primary", inventory=inventory)


def test_role_override_may_differ_from_exact_endpoint_interface():
    config = multicast_config()
    config["source"]["primary_endpoint"]["interface_id"] = "dmz-video"
    inventory = [
        {
            "id": "dmz-video",
            "ip": "10.75.51.40",
            "purpose": "video",
            "directions": ["input"],
            "node_roles": ["primary"],
        },
        {
            "id": "main-video",
            "ip": "10.70.15.3",
            "purpose": "video",
            "directions": ["input"],
            "node_roles": ["primary"],
        },
    ]
    assert validate_multicast_config(config, role="primary", inventory=inventory)[2] == "10.70.15.3"


def test_legacy_worker_role_uses_video_input_ip_without_role_membership():
    config = multicast_config()
    config["source"] = None
    config["target_node"] = "worker_1"
    config["node_bindings"] = {}
    config["local_bind_ip"] = "10.70.15.3"
    inventory = [{
        "id": "main-video",
        "ip": "10.70.15.3",
        "purpose": "video",
        "directions": ["input"],
        "node_roles": ["primary", "backup"],
    }]
    assert validate_multicast_config(config, role="worker_1", inventory=inventory)[2] == "10.70.15.3"


def test_structured_endpoint_binding_precedes_legacy_binding():
    config = multicast_config()
    config["node_bindings"] = {}
    config["local_bind_ip"] = "10.0.0.9"
    assert resolve_input_bind_ip(config, "primary") == "10.75.51.40"


def test_structured_endpoint_binding_precedes_legacy_node_binding():
    config = multicast_config()
    config["node_bindings"]["primary"] = {"local_bind_ip": "10.0.0.8"}
    assert resolve_input_bind_ip(config, "primary") == "10.75.51.40"


def test_structured_multicast_ffmpeg_url_options():
    config = ServiceConfig(**multicast_config())
    url = build_input_url(config, node_role="primary")
    parsed = urlsplit(url)
    assert parsed.hostname == "239.10.10.10"
    assert parsed.port == 5500
    assert parse_qs(parsed.query) == {
        "timeout": ["5000000"],
        "localaddr": ["10.70.15.3"],
        "reuse": ["1"],
    }


def test_unicast_udp_does_not_add_reuse():
    data = multicast_config()
    data["source"]["type"] = "unicast"
    data["source"]["primary_endpoint"]["address"] = "10.20.30.40"
    data["source_ip"] = "10.20.30.40"
    url = build_input_url(ServiceConfig(**data), node_role="primary")
    assert "reuse=" not in url


def test_config_fingerprint_is_stable_and_changes_with_config():
    first = multicast_config()
    second = multicast_config()
    assert config_fingerprint(first) == config_fingerprint(second)
    second["source_port"] = 5501
    assert config_fingerprint(first) != config_fingerprint(second)
