import json

import pytest

import api.main
from api.route_normalizer import normalize_service_payload


def base_hls_outputs():
    return {
        "low_res": {"enabled": False, "buffer_seconds": 10},
        "full_res": {"enabled": False, "buffer_seconds": 3600},
    }


@pytest.mark.asyncio
async def test_structured_srt_listener_source_derives_legacy_fields(async_client):
    payload = {
        "name": "Structured SRT listener",
        "destination_url": "udp://239.10.10.10:5000",
        "source": {
            "protocol": "srt",
            "mode": "listener",
            "primary_endpoint": {"interface_id": "primary-video-main", "address": "0.0.0.0", "port": 9000},
            "srt": {"latency_ms": 125, "passphrase": "secret"},
        },
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["source_protocol"] == "srt"
    assert data["source_mode"] == "listener"
    assert data["source_ip"] == "0.0.0.0"
    assert data["source_port"] == 9000
    assert data["latency_ms"] == 125
    assert data["passphrase"] == "secret"
    assert data["source"]["primary_endpoint"]["interface_id"] == "primary-video-main"


@pytest.mark.asyncio
async def test_structured_srt_caller_source_derives_legacy_fields(async_client):
    payload = {
        "name": "Structured SRT caller",
        "destination_url": "udp://239.10.10.10:5000",
        "source": {
            "protocol": "srt",
            "mode": "caller",
            "primary_endpoint": {"address": "192.0.2.10", "port": 9001},
        },
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["source_protocol"] == "srt"
    assert data["source_mode"] == "caller"
    assert data["source_ip"] == "192.0.2.10"
    assert data["source_port"] == 9001


@pytest.mark.asyncio
async def test_structured_udp_unicast_source_derives_legacy_fields(async_client):
    payload = {
        "name": "Structured UDP unicast",
        "destination_url": "udp://239.10.10.10:5000",
        "source": {
            "protocol": "udp",
            "type": "unicast",
            "primary_endpoint": {"address": "239.20.20.20", "port": 9010},
        },
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["source_protocol"] == "udp"
    assert data["source_ip"] == "239.20.20.20"
    assert data["source_port"] == 9010
    assert data["source"]["type"] == "unicast"


@pytest.mark.asyncio
async def test_structured_udp_multicast_source_derives_legacy_fields(async_client):
    payload = {
        "name": "Structured UDP multicast",
        "destination_url": "udp://239.10.10.10:5000",
        "source": {
            "protocol": "udp",
            "type": "multicast",
            "primary_endpoint": {"address": "239.30.30.30", "port": 9011},
        },
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["source_protocol"] == "udp"
    assert data["source_ip"] == "239.30.30.30"
    assert data["source_port"] == 9011
    assert data["source"]["type"] == "multicast"


@pytest.mark.asyncio
async def test_structured_srt_custom_stream_id_derives_legacy_streamid(async_client):
    payload = {
        "name": "Structured custom streamid",
        "destination_url": "udp://239.10.10.10:5000",
        "source": {
            "protocol": "srt",
            "mode": "caller",
            "primary_endpoint": {"address": "192.0.2.10", "port": 9001},
            "srt": {
                "stream_id": {
                    "mode": "custom",
                    "custom_value": "#!::r=resource,m=publish",
                }
            },
        },
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 200
    assert response.json()["streamid"] == "#!::r=resource,m=publish"


@pytest.mark.asyncio
async def test_structured_srt_default_stream_id_does_not_invent_legacy_streamid(async_client):
    payload = {
        "name": "Structured default streamid",
        "destination_url": "udp://239.10.10.10:5000",
        "source": {
            "protocol": "srt",
            "mode": "caller",
            "primary_endpoint": {"address": "192.0.2.10", "port": 9001},
            "srt": {
                "stream_id": {
                    "mode": "default",
                    "host_mode": "publish",
                    "resource_name": "resource",
                    "username": "user",
                }
            },
        },
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 200
    assert response.json()["streamid"] is None


@pytest.mark.asyncio
async def test_structured_udp_destination_derives_destination_url(async_client):
    payload = {
        "name": "Structured UDP destination",
        "source_protocol": "srt",
        "source_ip": "127.0.0.1",
        "source_port": 9901,
        "destinations": [
            {
                "protocol": "udp",
                "type": "multicast",
                "primary_endpoint": {"address": "239.10.10.10", "port": 5000},
                "link_parameters": {"ttl": 64},
            }
        ],
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 200
    assert response.json()["destination_url"] == "udp://239.10.10.10:5000?ttl=64"


@pytest.mark.asyncio
async def test_structured_srt_destination_derives_destination_url(async_client):
    payload = {
        "name": "Structured SRT destination",
        "source_protocol": "srt",
        "source_ip": "127.0.0.1",
        "source_port": 9901,
        "destinations": [
            {
                "protocol": "srt",
                "mode": "caller",
                "primary_endpoint": {"address": "192.0.2.30", "port": 7000},
                "srt": {
                    "stream_id": {"mode": "custom", "custom_value": "publish/me"},
                    "passphrase": "secret",
                },
            }
        ],
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 200
    assert response.json()["destination_url"] == (
        "srt://192.0.2.30:7000?mode=caller&streamid=publish%2Fme&passphrase=secret"
    )


@pytest.mark.asyncio
async def test_rejects_multiple_enabled_normal_destinations(async_client):
    payload = {
        "name": "Too many destinations",
        "source_protocol": "srt",
        "source_ip": "127.0.0.1",
        "source_port": 9901,
        "destinations": [
            {"protocol": "udp", "primary_endpoint": {"address": "239.0.0.1", "port": 5000}},
            {"protocol": "udp", "primary_endpoint": {"address": "239.0.0.2", "port": 5001}},
        ],
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 422
    assert "Only one enabled normal destination" in response.text


@pytest.mark.asyncio
async def test_rejects_enabled_structured_destination_without_target(async_client):
    payload = {
        "name": "Destination without target",
        "source_protocol": "srt",
        "source_ip": "127.0.0.1",
        "source_port": 9901,
        "destinations": [{"protocol": "raw"}],
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 422
    assert "raw structured destination requires url" in response.text


@pytest.mark.asyncio
async def test_rejects_enabled_path_redundancy_without_secondary_endpoint(async_client):
    payload = {
        "name": "Invalid path redundancy",
        "destination_url": "udp://239.10.10.10:5000",
        "source": {
            "protocol": "udp",
            "type": "unicast",
            "primary_endpoint": {"address": "239.20.20.20", "port": 9901},
            "path_redundancy": {
                "enabled": True,
                "mode": "manual",
            },
        },
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 422
    assert "secondary_endpoint with port is required" in response.text


@pytest.mark.asyncio
async def test_rejects_enabled_path_redundancy_with_none_mode(async_client):
    payload = {
        "name": "Invalid redundancy mode",
        "destination_url": "udp://239.10.10.10:5000",
        "source": {
            "protocol": "udp",
            "type": "unicast",
            "primary_endpoint": {"address": "239.20.20.20", "port": 9901},
            "path_redundancy": {
                "enabled": True,
                "mode": "none",
                "secondary_endpoint": {"address": "239.20.20.21", "port": 9902},
            },
        },
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 422
    assert "mode must be manual when path redundancy is enabled" in response.text


@pytest.mark.asyncio
async def test_rejects_rendezvous_mode(async_client):
    payload = {
        "name": "No rendezvous",
        "destination_url": "udp://239.10.10.10:5000",
        "source": {
            "protocol": "srt",
            "mode": "rendezvous",
            "primary_endpoint": {"address": "192.0.2.10", "port": 9001},
        },
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rejects_rtp_protocol(async_client):
    payload = {
        "name": "No RTP yet",
        "destination_url": "udp://239.10.10.10:5000",
        "source": {
            "protocol": "rtp",
            "primary_endpoint": {"address": "239.0.0.1", "port": 5000},
        },
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_structured_hls_source_url_validates(async_client):
    payload = {
        "name": "Structured HLS source",
        "source": {"protocol": "hls", "url": "https://example.com/live/stream.m3u8"},
        "destination_url": "",
        "enable_hls_preview": True,
        "enabled": False,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["source_protocol"] == "hls"
    assert data["source_url"] == "https://example.com/live/stream.m3u8"
    assert data["source_port"] is None


@pytest.mark.asyncio
async def test_structured_fields_round_trip_and_sync_to_redis(async_client):
    payload = {
        "name": "Structured round trip",
        "source": {
            "protocol": "udp",
            "type": "unicast",
            "primary_endpoint": {"address": "239.10.10.10", "port": 9000},
            "path_redundancy": {
                "enabled": True,
                "mode": "manual",
                "secondary_endpoint": {"address": "239.10.10.11", "port": 9001},
            },
        },
        "destinations": [
            {"protocol": "udp", "primary_endpoint": {"address": "239.20.20.20", "port": 5000}}
        ],
        "enabled": True,
    }

    response = await async_client.post("/api/services", json=payload)

    assert response.status_code == 200
    data = response.json()
    service_id = data["id"]
    assert data["source"]["path_redundancy"]["secondary_endpoint"]["port"] == 9001
    assert data["destinations"][0]["primary_endpoint"]["address"] == "239.20.20.20"

    stored = api.main.redis_client.hashes["service_configs"][service_id]
    redis_config = json.loads(stored)
    assert redis_config["source"]["protocol"] == "udp"
    assert redis_config["destinations"][0]["protocol"] == "udp"


def test_normalizer_builds_structured_source_from_flat_payload():
    data = normalize_service_payload({
        "name": "flat",
        "source_protocol": "srt",
        "source_mode": "caller",
        "source_ip": "192.0.2.10",
        "source_port": 9000,
        "source_path": "",
        "source_url": None,
        "destination_url": "udp://239.0.0.1:5000",
        "streamid": "legacy",
        "hls_outputs": base_hls_outputs(),
        "enable_hls_preview": False,
    })

    assert data["source"]["protocol"] == "srt"
    assert data["source"]["primary_endpoint"]["address"] == "192.0.2.10"
    assert data["source"]["srt"]["stream_id"]["custom_value"] == "legacy"
    assert data["destinations"][0]["protocol"] == "udp"
