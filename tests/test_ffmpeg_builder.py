from backend.ffmpeg_builder import build_ffmpeg_command, build_input_url, destination_format, resolve_local_bind_ip
from backend.models import ServiceConfig


def make_config(**overrides):
    data = {
        "id": "svc-1",
        "name": "Builder test",
        "source_protocol": "srt",
        "source_mode": "caller",
        "source_ip": "127.0.0.1",
        "source_port": 9000,
        "destination_url": "udp://239.0.0.1:5000",
    }
    data.update(overrides)
    return ServiceConfig(**data)


def test_destination_format_matches_delivery_protocol():
    assert destination_format("rtmp://example/live/key") == "flv"
    assert destination_format("rtmps://example/live/key") == "flv"
    assert destination_format("srt://0.0.0.0:9000?mode=listener") == "mpegts"
    assert destination_format("udp://239.0.0.1:5000") == "mpegts"
    assert destination_format("rist://example:9000") is None


def test_rtmp_destination_uses_flv_format():
    config = make_config(destination_url="rtmp://example/live/key")
    command = build_ffmpeg_command(config, build_input_url(config), "frontend/previews/svc-1")

    fmt_index = command.index("-f")
    assert command[fmt_index + 1] == "flv"


def test_udp_destination_uses_mpegts_format():
    config = make_config(destination_url="udp://239.0.0.1:5000")
    command = build_ffmpeg_command(config, build_input_url(config), "frontend/previews/svc-1")

    fmt_index = command.index("-f")
    assert command[fmt_index + 1] == "mpegts"


def test_srt_caller_uses_localaddr_option():
    config = make_config(local_bind_ip="192.168.1.10")
    input_url = build_input_url(config)

    assert "localaddr=192.168.1.10" in input_url
    assert "localbind" not in input_url


def test_node_binding_overrides_legacy_local_bind_ip_for_node():
    config = make_config(
        local_bind_ip="10.50.1.10",
        node_bindings={
            "primary": {"local_bind_ip": "10.50.1.21"},
            "backup": {"local_bind_ip": "10.50.1.22"},
        },
    )

    assert resolve_local_bind_ip(config, "primary") == "10.50.1.21"
    assert resolve_local_bind_ip(config, "backup") == "10.50.1.22"
    assert resolve_local_bind_ip(config, "worker_3") == "10.50.1.10"


def test_srt_listener_binds_to_node_specific_video_ip():
    config = make_config(
        source_mode="listener",
        source_ip="0.0.0.0",
        node_bindings={
            "primary": {"local_bind_ip": "10.50.1.21"},
            "backup": {"local_bind_ip": "10.50.1.22"},
        },
    )

    assert build_input_url(config, node_role="primary").startswith("srt://10.50.1.21:9000")
    assert build_input_url(config, node_role="backup").startswith("srt://10.50.1.22:9000")


def test_udp_uses_node_specific_localaddr():
    config = make_config(
        source_protocol="udp",
        node_bindings={"primary": {"local_bind_ip": "10.50.1.21"}},
    )

    assert "localaddr=10.50.1.21" in build_input_url(config, node_role="primary")
