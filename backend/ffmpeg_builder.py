import os
from urllib.parse import urlencode

from backend.models import ServiceConfig


def _strip_protocol_and_path(value: str) -> str:
    clean = value
    for prefix in ["srt://", "rtmp://", "http://", "udp://", "rist://"]:
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
    if "/" in clean:
        clean = clean.split("/", 1)[0]
    return clean


def resolve_local_bind_ip(config: ServiceConfig, node_role: str | None = None) -> str | None:
    if node_role and config.node_bindings:
        binding = config.node_bindings.get(node_role)
        if binding and binding.local_bind_ip:
            return binding.local_bind_ip
    return config.local_bind_ip


def build_input_url(config: ServiceConfig, use_backup: bool = False, node_role: str | None = None) -> str:
    input_ip = config.backup_input_ip if use_backup and config.backup_input_ip else config.source_ip
    clean_ip = _strip_protocol_and_path(input_ip)
    local_bind_ip = resolve_local_bind_ip(config, node_role)
    protocol = getattr(config.source_protocol, "value", config.source_protocol)

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
        if local_bind_ip and config.source_mode == "caller":
            params["localaddr"] = local_bind_ip
        elif local_bind_ip and config.source_mode == "listener":
            clean_ip = local_bind_ip
        return f"srt://{clean_ip}:{config.source_port}?{urlencode(params)}"

    if protocol == "udp":
        params = {"timeout": "5000000"}
        if local_bind_ip:
            params["localaddr"] = local_bind_ip
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


def build_ffmpeg_command(config: ServiceConfig, input_url: str, preview_dir: str) -> list[str]:
    preview_path = os.path.join(preview_dir, "preview.jpg")
    command = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-progress",
        "pipe:2",
        "-i",
        input_url,
        "-map",
        "0:v?",
        "-map",
        "0:a?",
        "-c:v",
        "copy",
        "-c:a",
        "copy",
    ]

    fmt = destination_format(config.destination_url)
    if fmt:
        command.extend(["-f", fmt])

    command.extend([
        config.destination_url,
        "-map",
        "0:v:0?",
        "-r",
        "1",
        "-update",
        "1",
        preview_path,
    ])

    if getattr(config, "enable_hls_preview", False):
        command.extend(["-map", "0:v:0?", "-map", "0:a:0?"])
        hw_accel = os.getenv("HW_ACCEL", "cpu")
        if hw_accel == "nvidia":
            command.extend(["-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ll"])
        else:
            command.extend(["-c:v", "libx264", "-preset", "ultrafast", "-threads", "auto"])

        command.extend([
            "-b:v",
            "400k",
            "-maxrate",
            "400k",
            "-bufsize",
            "800k",
            "-vf",
            "scale=-2:360",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            "-f",
            "hls",
            "-hls_time",
            "2",
            "-hls_list_size",
            "3",
            "-hls_flags",
            "delete_segments",
            os.path.join(preview_dir, "stream.m3u8"),
        ])

    return command
