import os
import json
import logging
import asyncio
import redis.asyncio as redis
from prometheus_client import start_http_server, Gauge

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

system_cpu_usage = Gauge('srt_system_cpu_usage', 'CPU', ['node'])
system_memory_usage = Gauge('srt_system_memory_usage', 'RAM', ['node'])
srt_active_services = Gauge('srt_active_services', 'Active', ['node'])
srt_error_services = Gauge('srt_error_services', 'Error', ['node'])
stream_bitrate_kbps = Gauge('srt_stream_bitrate_kbps', 'Bitrate', ['service_id', 'service_name', 'node'])
stream_cc_errors_total = Gauge('srt_stream_cc_errors_total', 'CC Errors Total (Migrated dynamically to Gauge for stateless Redis ingestion)', ['service_id', 'service_name', 'node'])

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost")

async def telemetry_loop():
    r = redis.from_url(REDIS_URL)
    pubsub = r.pubsub()
    await pubsub.subscribe("telemetry_metrics", "telemetry_hardware")
    
    logger.info("Telemetry Microservice online: Starting local Prometheus target on :9090")
    start_http_server(9090)
    
    global_states_by_node = {}
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                channel = message["channel"].decode()
                data = json.loads(message["data"])
                
                if channel == "telemetry_hardware":
                    node = data.get("node", "unknown")
                    system_cpu_usage.labels(node=node).set(data.get("cpu", 0))
                    system_memory_usage.labels(node=node).set(data.get("ram", 0))
                    
                elif channel == "telemetry_metrics":
                    sid = data["service_id"]
                    name = data["service_name"]
                    node = data["node"]
                    status = data["status"]
                    bitrate = data["bitrate"]
                    cc = data["cc"]
                    
                    if node not in global_states_by_node: global_states_by_node[node] = {}
                    global_states_by_node[node][sid] = status
                    
                    active = sum(1 for s in global_states_by_node[node].values() if s == "running")
                    errors = sum(1 for s in global_states_by_node[node].values() if s == "error")
                    
                    srt_active_services.labels(node=node).set(active)
                    srt_error_services.labels(node=node).set(errors)
                    stream_bitrate_kbps.labels(service_id=sid, service_name=name, node=node).set(bitrate)
                    stream_cc_errors_total.labels(service_id=sid, service_name=name, node=node).set(cc)
            except Exception as e:
                logger.error(f"Parse boundary failed: {e}")

if __name__ == '__main__':
    asyncio.run(telemetry_loop())
