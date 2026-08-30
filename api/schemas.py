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


class RouteEndpoint(BaseModel):
    interface_id: Optional[str] = None
    bind_ip: Optional[str] = None
    address: str = Field(default="0.0.0.0", min_length=1)
    port: Optional[int] = Field(default=None, ge=1, le=65535)

    model_config = ConfigDict(extra="forbid")


class PathRedundancy(BaseModel):
    enabled: bool = False
    mode: Literal["none", "manual"] = "none"
    secondary_endpoint: Optional[RouteEndpoint] = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_redundancy_state(self):
        if self.enabled:
            if self.mode == "none":
                raise ValueError("path_redundancy.mode must be manual when path redundancy is enabled")
            if not self.secondary_endpoint or self.secondary_endpoint.port is None:
                raise ValueError("path_redundancy.secondary_endpoint with port is required when enabled")
        return self


class LinkParameters(BaseModel):
    mtu: Optional[int] = Field(default=None, ge=1)
    ttl: Optional[int] = Field(default=None, ge=0, le=255)
    tos: Optional[str] = None
    fec: Optional[str] = None
    max_bitrate_kbps: Optional[int] = Field(default=None, ge=1)
    traffic_shaping: bool = False

    model_config = ConfigDict(extra="forbid")


class StreamIdConfig(BaseModel):
    mode: Literal["default", "custom"] = "default"
    host_mode: Optional[str] = None
    resource_name: Optional[str] = None
    username: Optional[str] = None
    custom_value: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class SrtParameters(BaseModel):
    latency_ms: Optional[int] = Field(default=None, ge=1)
    receive_buffer_bytes: Optional[int] = Field(default=None, ge=1)
    retransmission_bandwidth_kbps: Optional[int] = Field(default=None, ge=1)
    encryption: Optional[str] = None
    passphrase: Optional[str] = None
    authentication: Optional[str] = None
    rtp_header: Optional[str] = None
    error_correction: Optional[str] = None
    stream_id: Optional[StreamIdConfig] = None

    model_config = ConfigDict(extra="forbid")


class SourceConfig(BaseModel):
    protocol: Literal["srt", "rtmp", "udp", "rist", "hls"]
    mode: Optional[Literal["listener", "caller"]] = None
    type: Optional[Literal["unicast", "multicast"]] = None
    primary_endpoint: Optional[RouteEndpoint] = None
    path_redundancy: Optional[PathRedundancy] = None
    link_parameters: Optional[LinkParameters] = None
    srt: Optional[SrtParameters] = None
    url: Optional[str] = None
    path: str = ""

    model_config = ConfigDict(extra="forbid")

    @field_validator("url")
    @classmethod
    def validate_source_config_url(cls, value: Optional[str]) -> Optional[str]:
        if value and not value.startswith(("http://", "https://", "rtmp://", "rtmps://", "rist://")):
            raise ValueError("source.url must use a supported URL prefix")
        return value


class DestinationConfig(BaseModel):
    protocol: Literal["srt", "udp", "rtmp", "rtmps", "rist", "raw"]
    mode: Optional[Literal["listener", "caller"]] = None
    type: Optional[Literal["unicast", "multicast"]] = None
    primary_endpoint: Optional[RouteEndpoint] = None
    path_redundancy: Optional[PathRedundancy] = None
    link_parameters: Optional[LinkParameters] = None
    srt: Optional[SrtParameters] = None
    url: Optional[str] = None
    enabled: bool = True

    model_config = ConfigDict(extra="forbid")

    @field_validator("url")
    @classmethod
    def validate_destination_config_url(cls, value: Optional[str]) -> Optional[str]:
        if value and not value.startswith(("rtmp://", "rtmps://", "srt://", "udp://", "rist://")):
            raise ValueError("destination.url must start with rtmp://, rtmps://, srt://, udp://, or rist://")
        return value

    @model_validator(mode="after")
    def validate_enabled_destination_target(self):
        if not self.enabled:
            return self

        has_endpoint = (
            self.primary_endpoint is not None
            and bool(self.primary_endpoint.address)
            and self.primary_endpoint.port is not None
        )
        if self.protocol == "raw":
            if not self.url:
                raise ValueError("raw structured destination requires url")
            return self

        if not self.url and not has_endpoint:
            raise ValueError("structured destination requires url or primary endpoint address and port")
        return self


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
    source: Optional[SourceConfig] = None
    destinations: list[DestinationConfig] = Field(default_factory=list)

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
        has_enabled_destination = any(destination.enabled for destination in self.destinations)
        if not self.destination_url and not hls_enabled and not has_enabled_destination:
            raise ValueError("destination_url is required unless low-res or full HLS output is enabled")

        source_protocol = self.source.protocol if self.source else self.source_protocol
        source_url = self.source.url if self.source and self.source.protocol == "hls" else self.source_url
        source_endpoint = self.source.primary_endpoint if self.source else None
        source_port = source_endpoint.port if source_endpoint else self.source_port

        if source_protocol == "hls":
            if not source_url:
                raise ValueError("source_url is required for HLS sources")
            return self

        if source_port is None:
            raise ValueError("source_port is required unless source_protocol is hls")
        return self
