from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class NodeBinding(BaseModel):
    input_bind_ip: Optional[str] = None
    output_bind_ip: Optional[str] = None
    local_bind_ip: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class HlsOutputProfile(BaseModel):
    enabled: bool = False
    buffer_seconds: int = Field(default=10, ge=1, le=86400)

    model_config = ConfigDict(extra="forbid")


class HlsOutputs(BaseModel):
    low_res: HlsOutputProfile = Field(default_factory=lambda: HlsOutputProfile(buffer_seconds=10))
    full_res: HlsOutputProfile = Field(default_factory=lambda: HlsOutputProfile(buffer_seconds=3600))

    model_config = ConfigDict(extra="forbid")


class ServiceConfigRequest(BaseModel):
    id: Optional[str] = ""
    name: str = Field(min_length=1)
    source_protocol: Literal["srt", "rtmp", "udp", "rist", "hls"] = "srt"
    source_mode: Literal["listener", "caller"] = "listener"
    source_ip: str = Field(default="0.0.0.0", min_length=1)
    source_port: Optional[int] = Field(default=None, ge=1, le=65535)
    source_path: str = ""
    source_url: Optional[str] = None
    destination_url: str = ""

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
    hls_outputs: HlsOutputs = Field(default_factory=HlsOutputs)

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
        if not value:
            return value
        allowed_prefixes = ("rtmp://", "rtmps://", "srt://", "udp://", "rist://")
        if not value.startswith(allowed_prefixes):
            raise ValueError("destination_url must start with rtmp://, rtmps://, srt://, udp://, or rist://")
        return value

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: Optional[str]) -> Optional[str]:
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("source_url must start with http:// or https://")
        return value

    @model_validator(mode="after")
    def validate_protocol_and_outputs(self):
        if self.enable_hls_preview:
            self.hls_outputs.low_res.enabled = True

        hls_enabled = self.hls_outputs.low_res.enabled or self.hls_outputs.full_res.enabled
        if not self.destination_url and not hls_enabled:
            raise ValueError("destination_url is required unless low-res or full HLS output is enabled")

        if self.source_protocol == "hls":
            if not self.source_url:
                raise ValueError("source_url is required for HLS sources")
            return self

        if self.source_port is None:
            raise ValueError("source_port is required unless source_protocol is hls")
        return self
