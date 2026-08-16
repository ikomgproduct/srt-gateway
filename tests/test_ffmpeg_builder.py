from backend.ffmpeg_builder import (
    build_ffmpeg_command,
    build_input_url,
    cleanup_hls_outputs,
    destination_format,
    resolve_input_bind_ip,
    resolve_local_bind_ip,
    resolve_output_bind_ip,
    validate_hls_storage,
    with_output_bind_url,
)
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


def test_input_and_output_bindings_override_legacy_node_binding():
    config = make_config(
        local_bind_ip="10.50.1.10",
        node_bindings={
            "primary": {
                "local_bind_ip": "10.50.1.21",
                "input_bind_ip": "10.50.1.31",
                "output_bind_ip": "10.50.1.41",
            },
        },
    )

    assert resolve_input_bind_ip(config, "primary") == "10.50.1.31"
    assert resolve_output_bind_ip(config, "primary") == "10.50.1.41"


def test_output_binding_falls_back_to_legacy_binding():
    config = make_config(
        local_bind_ip="10.50.1.10",
        node_bindings={"primary": {"local_bind_ip": "10.50.1.21"}},
    )

    assert resolve_output_bind_ip(config, "primary") == "10.50.1.21"


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


def test_srt_listener_prefers_node_specific_input_bind_ip():
    config = make_config(
        source_mode="listener",
        source_ip="0.0.0.0",
        node_bindings={
            "primary": {"local_bind_ip": "10.50.1.21", "input_bind_ip": "10.50.1.31"},
        },
    )

    assert build_input_url(config, node_role="primary").startswith("srt://10.50.1.31:9000")


def test_udp_uses_node_specific_localaddr():
    config = make_config(
        source_protocol="udp",
        node_bindings={"primary": {"local_bind_ip": "10.50.1.21"}},
    )

    assert "localaddr=10.50.1.21" in build_input_url(config, node_role="primary")


def test_srt_destination_uses_output_bind_ip():
    config = make_config(
        destination_url="srt://10.70.20.50:9000?mode=caller",
        node_bindings={"primary": {"output_bind_ip": "10.50.1.41"}},
    )
    command = build_ffmpeg_command(
        config,
        build_input_url(config, node_role="primary"),
        "frontend/previews/svc-1",
        node_role="primary",
    )

    assert "srt://10.70.20.50:9000?mode=caller&localaddr=10.50.1.41" in command


def test_udp_destination_uses_output_bind_ip():
    url = with_output_bind_url("udp://239.0.0.1:5000?ttl=16", "10.50.1.41")

    assert url == "udp://239.0.0.1:5000?ttl=16&localaddr=10.50.1.41"


def test_rtmp_destination_does_not_get_output_bind_ip():
    url = with_output_bind_url("rtmp://example/live/key", "10.50.1.41")

    assert url == "rtmp://example/live/key"


def test_hls_source_uses_source_url_directly():
    config = make_config(
        source_protocol="hls",
        source_url="https://example.com/live/stream.m3u8",
        source_port=None,
        destination_url="",
        enable_hls_preview=True,
    )

    assert build_input_url(config) == "https://example.com/live/stream.m3u8"


def test_low_res_hls_preview_builds_two_renditions_without_destination(monkeypatch):
    monkeypatch.setenv("HLS_MIN_FREE_BYTES", "0")
    config = make_config(destination_url="", enable_hls_preview=True)
    command = build_ffmpeg_command(config, build_input_url(config), "frontend/previews/svc-1")

    assert "" not in command
    assert "frontend/previews/svc-1/low_res/360p/stream.m3u8" in command
    assert "frontend/previews/svc-1/low_res/480p/stream.m3u8" in command
    assert "scale=-2:360" in command
    assert "scale=-2:480" in command
    assert command.count("-f") == 2


def test_low_res_hls_preview_writes_master_playlist(tmp_path):
    config = make_config(destination_url="", enable_hls_preview=True)

    build_ffmpeg_command(config, build_input_url(config), str(tmp_path))

    playlist = (tmp_path / "low_res" / "stream.m3u8").read_text()
    assert "RESOLUTION=" not in playlist
    assert "360p/stream.m3u8" in playlist
    assert "480p/stream.m3u8" in playlist


def test_full_hls_output_builds_hd_renditions_with_configurable_buffer(monkeypatch):
    monkeypatch.setenv("HLS_MIN_FREE_BYTES", "0")
    config = make_config(
        hls_outputs={
            "low_res": {"enabled": False, "buffer_seconds": 10},
            "full_res": {"enabled": True, "buffer_seconds": 86400},
        },
    )
    command = build_ffmpeg_command(config, build_input_url(config), "frontend/previews/svc-1")

    assert "frontend/previews/svc-1/full_res/720p/stream.m3u8" in command
    assert "frontend/previews/svc-1/full_res/1080p/stream.m3u8" in command
    assert "scale=-2:720" in command
    assert "scale=-2:1080" in command
    assert "14400" in command


def test_hls_storage_quota_blocks_oversized_full_hls(tmp_path, monkeypatch):
    monkeypatch.setenv("HLS_STORAGE_QUOTA_BYTES", "1")
    config = make_config(
        hls_outputs={
            "low_res": {"enabled": False, "buffer_seconds": 10},
            "full_res": {"enabled": True, "buffer_seconds": 3600},
        },
    )

    try:
        validate_hls_storage(str(tmp_path), config)
    except RuntimeError as exc:
        assert "HLS_STORAGE_QUOTA_BYTES" in str(exc)
    else:
        raise AssertionError("Expected storage quota failure")


def test_cleanup_hls_outputs_removes_generated_hls_directories(tmp_path):
    low_res = tmp_path / "low_res"
    full_res = tmp_path / "full_res"
    low_res.mkdir()
    full_res.mkdir()

    cleanup_hls_outputs(str(tmp_path))

    assert not low_res.exists()
    assert not full_res.exists()
