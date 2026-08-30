from copy import deepcopy
from urllib.parse import parse_qsl, urlencode, urlsplit


NORMAL_DESTINATION_PROTOCOLS = {"srt", "udp", "rtmp", "rtmps", "rist", "raw"}


def _strip_empty(value):
    return value if value not in ("", None) else None


def _streamid_from_srt_params(srt_params: dict | None, fallback: str | None = None) -> str | None:
    if not srt_params:
        return fallback

    stream_id = srt_params.get("stream_id") or {}
    if stream_id.get("mode") == "custom":
        return _strip_empty(stream_id.get("custom_value")) or fallback
    return fallback


def _endpoint_from_url(url: str) -> dict:
    parsed = urlsplit(url)
    return {
        "address": parsed.hostname or "0.0.0.0",
        "port": parsed.port,
    }


def _source_from_flat(data: dict) -> dict | None:
    protocol = data.get("source_protocol")
    if not protocol:
        return None

    if protocol == "hls":
        return {
            "protocol": "hls",
            "url": data.get("source_url"),
            "path": data.get("source_path") or "",
        }

    source = {
        "protocol": protocol,
        "mode": data.get("source_mode"),
        "primary_endpoint": {
            "address": data.get("source_ip") or "0.0.0.0",
            "port": data.get("source_port"),
        },
        "path": data.get("source_path") or "",
    }
    if protocol == "udp":
        source["type"] = "unicast"
    if protocol == "srt":
        srt = {}
        if data.get("latency_ms") is not None:
            srt["latency_ms"] = data.get("latency_ms")
        if data.get("passphrase"):
            srt["passphrase"] = data.get("passphrase")
        if data.get("streamid"):
            srt["stream_id"] = {
                "mode": "custom",
                "custom_value": data.get("streamid"),
            }
        if srt:
            source["srt"] = srt
    return source


def _destination_from_flat(destination_url: str) -> dict | None:
    if not destination_url:
        return None

    parsed = urlsplit(destination_url)
    protocol = parsed.scheme or "raw"
    if protocol not in NORMAL_DESTINATION_PROTOCOLS:
        protocol = "raw"

    destination = {
        "protocol": protocol,
        "url": destination_url,
        "enabled": True,
    }
    if protocol in {"srt", "udp", "rist"}:
        destination["primary_endpoint"] = _endpoint_from_url(destination_url)
    if protocol == "udp":
        destination["type"] = "unicast"
    if protocol == "srt":
        params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        srt = {}
        if params.get("latency"):
            try:
                srt["latency_ms"] = int(params["latency"])
            except ValueError:
                pass
        if params.get("passphrase"):
            srt["passphrase"] = params["passphrase"]
        if params.get("streamid"):
            srt["stream_id"] = {
                "mode": "custom",
                "custom_value": params["streamid"],
            }
        destination["mode"] = params.get("mode") or "caller"
        if srt:
            destination["srt"] = srt
    return destination


def _first_enabled_destination(destinations: list[dict]) -> dict | None:
    enabled = [item for item in destinations if item.get("enabled", True)]
    if len(enabled) > 1:
        raise ValueError("Only one enabled normal destination is supported in this release")
    return enabled[0] if enabled else None


def build_legacy_destination_url(destination: dict) -> str:
    if not destination:
        return ""

    url = destination.get("url")
    if url:
        return url

    protocol = destination.get("protocol")
    if protocol == "raw":
        if not url:
            raise ValueError("Raw structured destination requires url")
        return url

    endpoint = destination.get("primary_endpoint") or {}
    address = endpoint.get("address")
    port = endpoint.get("port")
    if not address or not port:
        raise ValueError("Structured destination requires url or primary endpoint address and port")

    if protocol in {"rtmp", "rtmps"}:
        path = destination.get("path") or ""
        return f"{protocol}://{address}:{port}{path}"

    params = {}
    if protocol == "srt":
        params["mode"] = destination.get("mode") or "caller"
        streamid = _streamid_from_srt_params(destination.get("srt"))
        if streamid:
            params["streamid"] = streamid
        srt_params = destination.get("srt") or {}
        if srt_params.get("passphrase"):
            params["passphrase"] = srt_params["passphrase"]
    elif protocol == "udp":
        link_parameters = destination.get("link_parameters") or {}
        if link_parameters.get("ttl") is not None:
            params["ttl"] = str(link_parameters["ttl"])

    query = f"?{urlencode(params)}" if params else ""
    return f"{protocol}://{address}:{port}{query}"


def derive_legacy_fields(data: dict) -> dict:
    source = data.get("source")
    if source:
        data["source_protocol"] = source.get("protocol") or data.get("source_protocol")
        if source.get("mode"):
            data["source_mode"] = source["mode"]
        data["source_path"] = source.get("path") or data.get("source_path") or ""

        if source.get("protocol") == "hls":
            data["source_url"] = source.get("url") or data.get("source_url")
            data["source_port"] = None
        else:
            endpoint = source.get("primary_endpoint") or {}
            if endpoint.get("address"):
                data["source_ip"] = endpoint["address"]
            if endpoint.get("port") is not None:
                data["source_port"] = endpoint["port"]

        srt_params = source.get("srt") or {}
        if srt_params.get("latency_ms") is not None:
            data["latency_ms"] = srt_params["latency_ms"]
        if srt_params.get("passphrase"):
            data["passphrase"] = srt_params["passphrase"]
        data["streamid"] = _streamid_from_srt_params(srt_params, data.get("streamid"))

    destinations = data.get("destinations") or []
    if destinations:
        destination = _first_enabled_destination(destinations)
        if destination:
            data["destination_url"] = build_legacy_destination_url(destination)

    return data


def normalize_service_payload(data: dict) -> dict:
    normalized = deepcopy(data)

    if not normalized.get("source"):
        normalized["source"] = _source_from_flat(normalized)

    if not normalized.get("destinations"):
        destination = _destination_from_flat(normalized.get("destination_url") or "")
        normalized["destinations"] = [destination] if destination else []

    return derive_legacy_fields(normalized)
