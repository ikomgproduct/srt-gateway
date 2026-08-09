from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NodeBinding(BaseModel):
    local_bind_ip: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class ServiceConfigRequest(BaseModel):
    id: Optional[str] = ""
    name: str = Field(min_length=1)
    source_protocol: Literal["srt", "rtmp", "udp", "rist"] = "srt"
    source_mode: Literal["listener", "caller"] = "listener"
    source_ip: str = Field(default="0.0.0.0", min_length=1)
    source_port: int = Field(ge=1, le=65535)
    source_path: str = ""
    destination_url: str = Field(min_length=1)

    local_bind_ip: Optional[str] = None
    node_bindings: dict[str, NodeBinding] = Field(default_factory=dict)
    latency_ms: Optional[int] = Field(default=None, ge=1)
    passphrase: Optional[str] = None
    pbkeylen: Optional[Literal[16, 24, 32]] = None
    streamid: Optional[str] = None

    backup_input_ip: Optional[str] = None
    auto_failover: bool = False
    strict_probing: bool = False
    enable_hls_preview: bool = False

    target_node: str = Field(default="worker_1", min_length=1)
    ha_mode: Literal["manual", "active_passive", "active_active"] = "manual"
    failover_node: Optional[str] = None
    failover_after_seconds: int = Field(default=15, ge=5, le=300)
    failback_policy: Literal["manual", "automatic"] = "manual"
    enabled: bool = True

    model_config = ConfigDict(extra="forbid")

    @field_validator("destination_url")
    @classmethod
    def validate_destination_url(cls, value: str) -> str:
        allowed_prefixes = ("rtmp://", "rtmps://", "srt://", "udp://", "rist://")
        if not value.startswith(allowed_prefixes):
            raise ValueError("destination_url must start with rtmp://, rtmps://, srt://, udp://, or rist://")
        return value
