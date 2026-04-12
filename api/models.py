from sqlalchemy import Column, String, Integer, Boolean
from api.database import Base

class ServiceModel(Base):
    __tablename__ = "services"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    source_protocol = Column(String, default="srt")
    source_mode = Column(String, default="listener")
    source_ip = Column(String, default="0.0.0.0")
    source_port = Column(Integer)
    source_path = Column(String, nullable=True)
    destination_url = Column(String)
    
    local_bind_ip = Column(String, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    passphrase = Column(String, nullable=True)
    pbkeylen = Column(Integer, nullable=True)
    streamid = Column(String, nullable=True)
    
    backup_input_ip = Column(String, nullable=True)
    auto_failover = Column(Boolean, default=False)
    strict_probing = Column(Boolean, default=False)
    enable_hls_preview = Column(Boolean, default=False)
    
    target_node = Column(String, default="worker_1")
    enabled = Column(Boolean, default=True)
