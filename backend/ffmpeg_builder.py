import os
import math
import shutil
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from backend.models import ServiceConfig


def _strip_protocol_and_path(value: str) -> str:
    clean = value
    for prefix in ["srt://", "rtmp://", "http://", "udp://", "rist://"]:
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
    if "/" in clean:
        clean = clean.split("/", 1)[0]
    return clean


def _hls_outputs(config: ServiceConfig):
    outputs = getattr(config, "hls_outputs", None)
    low_res = getattr(outputs, "low_res", None)
    full_res = getattr(outputs, "full_res", None)
    return low_res, full_res


def low_res_hls_enabled(config: ServiceConfig) -> bool:
    low_res, _ = _hls_outputs(config)
    return bool(getattr(config, "enable_hls_preview", False) or getattr(low_res, "enabled", False))


def full_res_hls_enabled(config: ServiceConfig) -> bool:
    _, full_res = _hls_outputs(config)
    return bool(getattr(full_res, "enabled", False))


def any_hls_output_enabled(config: ServiceConfig) -> bool:
    return low_res_hls_enabled(config) or full_res_hls_enabled(config)


def hls_output_dirs(preview_dir: str) -> list[str]:
    return [os.path.join(preview_dir, "low_res"), os.path.join(preview_dir, "full_res")]


def cleanup_hls_outputs(preview_dir: str) -> None:
    for output_dir in hls_output_dirs(preview_dir):
        if os.path.isdir(output_dir):
            shutil.rmtree(output_dir, ignore_errors=True)


def _parse_int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def estimate_hls_storage_bytes(config: ServiceConfig) -> int:
    low_res, full_res = _hls_outputs(config)
    total_bits = 0
    if low_res_hls_enabled(config):
        seconds = getattr(low_res, "buffer_seconds", 10) or 10
        total_bits += seconds * (400_000 + 800_000 + 64_000 + 96_000)
    if full_res_hls_enabled(config):
        seconds = min(getattr(full_res, "buffer_seconds", 3600) or 3600, 86400)
        total_bits += seconds * (3_000_000 + 6_000_000 + 128_000 + 160_000)
    return math.ceil(total_bits / 8)


def validate_hls_storage(preview_dir: str, config: ServiceConfig) -> None:
    if not any_hls_output_enabled(config):
        return
    os.makedirs(preview_dir, exist_ok=True)
    usage = shutil.disk_usage(preview_dir)
    minimum_free = _parse_int_env("HLS_MIN_FREE_BYTES", 1_000_000_000)
    if usage.free < minimum_free:
        raise RuntimeError(f"HLS storage free space is below HLS_MIN_FREE_BYTES ({minimum_free})")

    quota = _parse_int_env("HLS_STORAGE_QUOTA_BYTES", 0)
    estimated = estimate_hls_storage_bytes(config)
    if quota and estimated > quota:
        raise RuntimeError(f"Estimated HLS buffer size {estimated} exceeds HLS_STORAGE_QUOTA_BYTES ({quota})")


def _node_binding(config: ServiceConfig, node_role: str | None = None):
    if node_role and config.node_bindings:
        return config.node_bindings.get(node_role)
    return None


def resolve_input_bind_ip(config: ServiceConfig, node_role: str | None = None) -> str | None:
    binding = _node_binding(config, node_role)
    if binding:
        return binding.input_bind_ip or binding.local_bind_ip or config.local_bind_ip
    return config.local_bind_ip


def resolve_output_bind_ip(config: ServiceConfig, node_role: str | None = None) -> str | None:
    binding = _node_binding(config, node_role)
    if binding:
        return binding.output_bind_ip or binding.local_bind_ip or config.local_bind_ip
    return config.local_bind_ip


def resolve_local_bind_ip(config: ServiceConfig, node_role: str | None = None) -> str | None:
    return resolve_input_bind_ip(config, node_role)


def with_output_bind_url(destination_url: str, output_bind_ip: str | None) -> str:
    if not output_bind_ip:
        return destination_url
    if not (destination_url.startswith("srt://") or destination_url.startswith("udp://")):
        return destination_url

    parsed = urlsplit(destination_url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params["localaddr"] = output_bind_ip
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(params), parsed.fragment))


def build_input_url(config: ServiceConfig, use_backup: bool = False, node_role: str | None = None) -> str:
    input_ip = config.backup_input_ip if use_backup and config.backup_input_ip else config.source_ip
    clean_ip = _strip_protocol_and_path(input_ip)
    input_bind_ip = resolve_input_bind_ip(config, node_role)
    protocol = getattr(config.source_protocol, "value", config.source_protocol)

    if protocol == "hls":
        return config.source_url or input_ip

    if protocol == "srt":
        params = {"mode": config.source_mode, "rw_timeout": "5000000"}
        if config.latency_ms:
            params["latency"] = str(config.latency_ms)
        if config.passphrase:
            params["passphrase"] = config.passphrase
        if config.pbkeylen:
            params["pbkeylen"] = str(config.pbkeylen)
        if config.streamid:
            params["streamid"] = config.streamid
        if input_bind_ip and config.source_mode == "caller":
            params["localaddr"] = input_bind_ip
        elif input_bind_ip and config.source_mode == "listener":
            clean_ip = input_bind_ip
        return f"srt://{clean_ip}:{config.source_port}?{urlencode(params)}"

    if protocol == "udp":
        params = {"timeout": "5000000"}
        if input_bind_ip:
            params["localaddr"] = input_bind_ip
        return f"udp://{clean_ip}:{config.source_port}?{urlencode(params)}"

    if protocol == "rist":
        prefix = "@" if config.source_mode == "listener" else ""
        params = {"rist_profile": "main", "rw_timeout": "5000000"}
        if config.latency_ms:
            params["buffer_size"] = str(config.latency_ms)
        if config.passphrase:
            params["secret"] = config.passphrase
        return f"rist://{prefix}{clean_ip}:{config.source_port}?{urlencode(params)}"

    path = config.source_path or ""
    params = {"rw_timeout": "5000000"}
    if config.source_mode == "listener":
        params["listen"] = "1"
    return f"rtmp://{clean_ip}:{config.source_port}{path}?{urlencode(params)}"


def destination_format(destination_url: str) -> str | None:
    if destination_url.startswith("rtmp://") or destination_url.startswith("rtmps://"):
        return "flv"
    if destination_url.startswith("srt://") or destination_url.startswith("udp://"):
        return "mpegts"
    return None


def _encoder_options() -> list[str]:
    hw_accel = os.getenv("HW_ACCEL", "cpu")
    if hw_accel == "nvidia":
        return ["-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ll"]
    return ["-c:v", "libx264", "-preset", "ultrafast", "-threads", "auto"]


def _hls_list_size(buffer_seconds: int, segment_seconds: int) -> str:
    return str(max(1, math.ceil(buffer_seconds / segment_seconds)))


def _append_hls_rendition(
    command: list[str],
    preview_dir: str,
    profile_dir: str,
    height: int,
    video_bitrate: str,
    audio_bitrate: str,
    buffer_seconds: int,
    segment_seconds: int,
) -> None:
    output_dir = os.path.join(preview_dir, profile_dir, f"{height}p")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "stream.m3u8")
    command.extend([
        "-map",
        "0:v:0?",
        "-map",
        "0:a:0?",
        *_encoder_options(),
        "-b:v",
        video_bitrate,
        "-maxrate",
        video_bitrate,
        "-bufsize",
        f"{int(video_bitrate.rstrip('k')) * 2}k" if video_bitrate.endswith("k") else video_bitrate,
        "-vf",
        f"scale=-2:{height}",
        "-c:a",
        "aac",
        "-b:a",
        audio_bitrate,
        "-f",
        "hls",
        "-hls_time",
        str(segment_seconds),
        "-hls_list_size",
        _hls_list_size(buffer_seconds, segment_seconds),
        "-hls_flags",
        "delete_segments",
        output_path,
    ])


def _write_hls_master(preview_dir: str, profile_dir: str, variants: list[tuple[int, int]]) -> None:
    output_dir = os.path.join(preview_dir, profile_dir)
    os.makedirs(output_dir, exist_ok=True)
    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    for height, bandwidth in variants:
        lines.append(f"#EXT-X-STREAM-INF:BANDWIDTH={bandwidth}")
        lines.append(f"{height}p/stream.m3u8")
    with open(os.path.join(output_dir, "stream.m3u8"), "w", encoding="utf-8") as playlist:
        playlist.write("\n".join(lines) + "\n")


def _append_hls_outputs(command: list[str], config: ServiceConfig, preview_dir: str) -> None:
    low_res, full_res = _hls_outputs(config)
    if low_res_hls_enabled(config):
        buffer_seconds = getattr(low_res, "buffer_seconds", 10) or 10
        _write_hls_master(preview_dir, "low_res", [(360, 500000), (480, 1000000)])
        _append_hls_rendition(command, preview_dir, "low_res", 360, "400k", "64k", buffer_seconds, 2)
        _append_hls_rendition(command, preview_dir, "low_res", 480, "800k", "96k", buffer_seconds, 2)

    if full_res_hls_enabled(config):
        buffer_seconds = min(getattr(full_res, "buffer_seconds", 3600) or 3600, 86400)
        _write_hls_master(preview_dir, "full_res", [(720, 3500000), (1080, 7000000)])
        _append_hls_rendition(command, preview_dir, "full_res", 720, "3000k", "128k", buffer_seconds, 6)
        _append_hls_rendition(command, preview_dir, "full_res", 1080, "6000k", "160k", buffer_seconds, 6)


def build_ffmpeg_command(
    config: ServiceConfig,
    input_url: str,
    preview_dir: str,
    node_role: str | None = None,
) -> list[str]:
    preview_path = os.path.join(preview_dir, "preview.jpg")
    validate_hls_storage(preview_dir, config)
    destination_url = with_output_bind_url(config.destination_url, resolve_output_bind_ip(config, node_role))
    command = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-progress",
        "pipe:2",
        "-i",
        input_url,
    ]

    if destination_url:
        command.extend([
            "-map",
            "0:v?",
            "-map",
            "0:a?",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
        ])

        fmt = destination_format(destination_url)
        if fmt:
            command.extend(["-f", fmt])

        command.append(destination_url)

    command.extend([
        "-map",
        "0:v:0?",
        "-r",
        "1",
        "-update",
        "1",
        preview_path,
    ])

    _append_hls_outputs(command, config, preview_dir)

    return command
