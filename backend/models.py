from pydantic import BaseModel, ConfigDict
from enum import Enum
from typing import Optional

class StreamStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"

class SourceProtocol(str, Enum):
    SRT = "srt"
    RTMP = "rtmp"
    UDP = "udp"
    RIST = "rist"

class NodeBinding(BaseModel):
    local_bind_ip: Optional[str] = None

class ServiceConfig(BaseModel):
    id: str
    name: str
    source_protocol: SourceProtocol = SourceProtocol.SRT
    source_ip: str = "0.0.0.0"
    source_port: int
    source_path: str = "" # for rtmp like /live/stream
    source_mode: str = "listener" # listener or caller
    
    # Phase 2: Advanced Network & SRT options
    local_bind_ip: Optional[str] = None # For UDP multicast bind or SRT explicit NIC binding
    node_bindings: dict[str, NodeBinding] = {}
    latency_ms: Optional[int] = None
    passphrase: Optional[str] = None
    pbkeylen: Optional[int] = None # 16, 24, 32
    streamid: Optional[str] = None

    destination_url: str
    main_input_ip: Optional[str] = None
    backup_input_ip: Optional[str] = None
    auto_failover: bool = False
    strict_probing: bool = False
    enable_hls_preview: bool = False
    target_node: str = "primary"
    ha_mode: str = "manual"
    failover_node: Optional[str] = None
    failover_after_seconds: int = 15
    failback_policy: str = "manual"
    enabled: bool = True

    model_config = ConfigDict(from_attributes=True)

class ServiceState(BaseModel):
    config: ServiceConfig
    status: StreamStatus = StreamStatus.STOPPED
    uptime: int = 0
    active_input: str = "main"  # 'main' or 'backup'
    pid: Optional[int] = None
    error_msg: Optional[str] = None
