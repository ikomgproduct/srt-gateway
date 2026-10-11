import hashlib
import ipaddress
import json
import os
from dataclasses import dataclass
from typing import Any


DEFAULT_UDP_MULTICAST_PORT_MIN = 1024
DEFAULT_UDP_MULTICAST_PORT_MAX = 65535
PRODUCTION_WORKER_ROLES = {"primary", "backup"}


@dataclass
class MulticastPolicyError(ValueError):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


def multicast_port_policy() -> tuple[int, int]:
    try:
        minimum = int(os.getenv("UDP_MULTICAST_PORT_MIN", str(DEFAULT_UDP_MULTICAST_PORT_MIN)))
        maximum = int(os.getenv("UDP_MULTICAST_PORT_MAX", str(DEFAULT_UDP_MULTICAST_PORT_MAX)))
    except ValueError as exc:
        raise RuntimeError("UDP_MULTICAST_PORT_MIN/MAX must be integers") from exc
    if minimum < 1 or maximum > 65535 or minimum > maximum:
        raise RuntimeError("UDP_MULTICAST_PORT_MIN/MAX must define a valid range within 1-65535")
    return minimum, maximum


def _as_dict(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def is_ipv4_multicast(value: str | None) -> bool:
    try:
        address = ipaddress.ip_address(value or "")
    except ValueError:
        return False
    return address.version == 4 and address.is_multicast


def is_udp_multicast(config: Any) -> bool:
    data = _as_dict(config)
    source = _as_dict(data.get("source"))
    if source:
        return source.get("protocol") == "udp" and source.get("type") == "multicast"
    protocol = data.get("source_protocol")
    protocol = getattr(protocol, "value", protocol)
    return protocol == "udp" and is_ipv4_multicast(data.get("source_ip"))


def source_endpoint(config: Any) -> tuple[str | None, int | None, str | None]:
    data = _as_dict(config)
    source = _as_dict(data.get("source"))
    endpoint = _as_dict(source.get("primary_endpoint"))
    address = endpoint.get("address") or data.get("source_ip")
    port = endpoint.get("port") if endpoint.get("port") is not None else data.get("source_port")
    return address, port, endpoint.get("bind_ip")


def resolve_input_bind_ip(config: Any, role: str | None = None) -> str | None:
    data = _as_dict(config)
    bindings = _as_dict(data.get("node_bindings"))
    binding = _as_dict(bindings.get(role)) if role else {}
    _, _, endpoint_bind_ip = source_endpoint(data)
    return (
        binding.get("input_bind_ip")
        or endpoint_bind_ip
        or binding.get("local_bind_ip")
        or data.get("local_bind_ip")
    )


def eligible_roles(config: Any) -> list[str]:
    data = _as_dict(config)
    target = data.get("target_node")
    if target == "all":
        return ["primary", "backup"]
    roles = [target] if target else []
    if data.get("ha_mode", "manual") == "active_passive" and data.get("failover_node"):
        roles.append(data["failover_node"])
    return list(dict.fromkeys(role for role in roles if role))


def validate_endpoint_interface(config: Any, inventory: list[dict] | None) -> None:
    if inventory is None:
        return
    data = _as_dict(config)
    source = _as_dict(data.get("source"))
    endpoint = _as_dict(source.get("primary_endpoint"))
    interface_id = endpoint.get("interface_id")
    if not interface_id:
        return

    matches = [item for item in inventory if item.get("id") == interface_id]
    if len(matches) != 1:
        reason = "unknown" if not matches else "duplicated"
        raise MulticastPolicyError(
            "invalid_bind_interface",
            f"Input interface ID {interface_id} is {reason} in the configured interface inventory",
        )

    interface = matches[0]
    if interface.get("purpose") != "video" or "input" not in (interface.get("directions") or []):
        raise MulticastPolicyError(
            "invalid_bind_interface",
            f"Input interface ID {interface_id} is not an eligible video interface for input",
        )

    bind_ip = endpoint.get("bind_ip")
    if not bind_ip or bind_ip != interface.get("ip"):
        raise MulticastPolicyError(
            "invalid_bind_interface",
            f"Input interface ID {interface_id} requires bind IP {interface.get('ip')}, not {bind_ip or 'empty'}",
        )


def multicast_bind_keys(config: Any) -> set[tuple[str, int]]:
    if not is_udp_multicast(config):
        return set()
    _, port, _ = source_endpoint(config)
    if port is None:
        return set()
    return {
        (bind_ip, int(port))
        for role in eligible_roles(config)
        if (bind_ip := resolve_input_bind_ip(config, role))
    }


def validate_multicast_config(
    config: Any,
    role: str | None = None,
    inventory: list[dict] | None = None,
) -> tuple[str, int, str]:
    if not is_udp_multicast(config):
        raise MulticastPolicyError("invalid_multicast_address", "Source is not configured as UDP multicast")

    validate_endpoint_interface(config, inventory)

    group, port, _ = source_endpoint(config)
    if not is_ipv4_multicast(group):
        raise MulticastPolicyError(
            "invalid_multicast_address",
            f"UDP multicast source address must be an IPv4 multicast group: {group or 'empty'}",
        )

    minimum, maximum = multicast_port_policy()
    if port is None or not minimum <= int(port) <= maximum:
        raise MulticastPolicyError(
            "port_out_of_policy",
            f"UDP multicast source port must be between {minimum} and {maximum}: {port}",
        )

    bind_ip = resolve_input_bind_ip(config, role)
    if not bind_ip:
        raise MulticastPolicyError(
            "invalid_bind_interface",
            f"UDP multicast requires an input bind interface for role {role or 'service'}",
        )

    if inventory is not None:
        enforce_role = role in PRODUCTION_WORKER_ROLES
        allowed = {
            item.get("ip")
            for item in inventory
            if item.get("purpose") == "video"
            and "input" in (item.get("directions") or [])
            and (not enforce_role or role in (item.get("node_roles") or []))
        }
        if bind_ip not in allowed:
            raise MulticastPolicyError(
                "invalid_bind_interface",
                f"Input bind IP {bind_ip} is not an eligible video interface for role {role or 'service'}",
            )
    return str(group), int(port), bind_ip


def config_fingerprint(config: Any) -> str:
    data = _as_dict(config)
    normalized = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
