import asyncio
import os
import json
import logging
import time
import re
import uuid
import redis.asyncio as redis
from backend.models import ServiceConfig
from backend.ffmpeg_builder import build_ffmpeg_command, build_input_url, cleanup_hls_outputs

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost")
NODE_ROLE = os.getenv("NODE_ROLE", "worker_1")
PREVIEW_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "previews")
os.makedirs(PREVIEW_DIR, exist_ok=True)
DESIRED_CONFIGS_KEY = "service_configs"
HEARTBEAT_PREFIX = "worker_heartbeat:"
LEASE_PREFIX = "stream_lease:"

def should_run_on_node(config: ServiceConfig, node_role: str) -> bool:
    if config.ha_mode == "active_passive":
        return node_role in [config.target_node, config.failover_node]
    return config.target_node in ["all", node_role]

class WorkerNode:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL)
        self.processes = {}
        self.state = {}
        self.lease_tokens = {}
        self.first_seen = {}
        
    async def run(self):
        pubsub = self.redis.pubsub()
        await pubsub.subscribe("stream_commands")
        asyncio.create_task(self.heartbeat_loop())
        asyncio.create_task(self.reconcile_loop())
        asyncio.create_task(self.lease_guard_loop())
        asyncio.create_task(self.metrics_loop())
        asyncio.create_task(self.watchdog_loop())
        asyncio.create_task(self.hardware_loop())
        logger.info(f"Worker Node {NODE_ROLE} initialized and listening to Redis.")
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    action = data.get("action")
                    
                    if action == "start":
                        config = ServiceConfig(**data["config"])
                        asyncio.create_task(self.reconcile_service(config, data.get("use_backup", False)))
                            
                    elif action == "stop":
                        service_id = data.get("id")
                        if service_id in self.state:
                            self.state[service_id]["enabled"] = False
                        asyncio.create_task(self.stop_service(service_id))
                except Exception as e:
                    logger.error(f"Worker Queue Error: {e}")

    async def heartbeat_loop(self):
        while True:
            try:
                await self.redis.set(f"{HEARTBEAT_PREFIX}{NODE_ROLE}", str(time.time()), ex=10)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            await asyncio.sleep(3)

    async def reconcile_loop(self):
        while True:
            try:
                configs = await self.redis.hgetall(DESIRED_CONFIGS_KEY)
                desired_ids = set()
                for raw_id, raw_config in configs.items():
                    service_id = raw_id.decode() if isinstance(raw_id, bytes) else raw_id
                    desired_ids.add(service_id)
                    payload = raw_config.decode() if isinstance(raw_config, bytes) else raw_config
                    config = ServiceConfig(**json.loads(payload))
                    await self.reconcile_service(config)

                for service_id in list(self.state.keys()):
                    if service_id not in desired_ids:
                        self.state[service_id]["enabled"] = False
                        await self.stop_service(service_id)
            except Exception as e:
                logger.error(f"Reconcile error: {e}")
            await asyncio.sleep(5)

    async def reconcile_service(self, config: ServiceConfig, use_backup: bool = False):
        self.first_seen.setdefault(config.id, time.time())
        if not config.enabled or not should_run_on_node(config, NODE_ROLE):
            if config.id in self.processes:
                await self.stop_service(config.id)
            return

        if config.ha_mode == "active_passive":
            owns_lease = await self.ensure_active_passive_lease(config)
            if not owns_lease:
                if config.id in self.processes:
                    await self.stop_service(config.id)
                return

        if config.id in self.processes and self.processes[config.id].returncode is None:
            self.state[config.id]["config"] = config
            self.state[config.id]["enabled"] = True
            return

        await self.start_service(config, use_backup)

    async def preferred_node_is_healthy(self, config: ServiceConfig) -> bool:
        if config.target_node == NODE_ROLE:
            return True
        return bool(await self.redis.exists(f"{HEARTBEAT_PREFIX}{config.target_node}"))

    async def ensure_active_passive_lease(self, config: ServiceConfig) -> bool:
        token = self.lease_tokens.get(config.id)
        lease_key = f"{LEASE_PREFIX}{config.id}"
        ttl = max(config.failover_after_seconds, 5)

        if token:
            current = await self.redis.get(lease_key)
            current = current.decode() if isinstance(current, bytes) else current
            if current == token:
                await self.redis.expire(lease_key, ttl)
                return True
            self.lease_tokens.pop(config.id, None)

        if NODE_ROLE != config.target_node:
            seen_for = time.time() - self.first_seen.get(config.id, time.time())
            if await self.preferred_node_is_healthy(config) or seen_for < ttl:
                return False

        token = f"{NODE_ROLE}:{uuid.uuid4()}"
        acquired = await self.redis.set(lease_key, token, nx=True, ex=ttl)
        if acquired:
            self.lease_tokens[config.id] = token
            logger.warning(f"[HA] {NODE_ROLE} acquired lease for {config.id}")
            return True
        return False

    async def owns_lease(self, service_id: str) -> bool:
        token = self.lease_tokens.get(service_id)
        if not token:
            return False
        current = await self.redis.get(f"{LEASE_PREFIX}{service_id}")
        current = current.decode() if isinstance(current, bytes) else current
        return current == token

    async def release_lease(self, service_id: str):
        token = self.lease_tokens.pop(service_id, None)
        if not token:
            return
        current = await self.redis.get(f"{LEASE_PREFIX}{service_id}")
        current = current.decode() if isinstance(current, bytes) else current
        if current == token:
            await self.redis.delete(f"{LEASE_PREFIX}{service_id}")

    async def lease_guard_loop(self):
        while True:
            try:
                for sid, details in list(self.state.items()):
                    config = details["config"]
                    if config.ha_mode == "active_passive" and sid in self.processes:
                        if not await self.owns_lease(sid):
                            logger.warning(f"[HA] Lease lost for {sid}; stopping local pipeline")
                            await self.stop_service(sid)
            except Exception as e:
                logger.error(f"Lease guard error: {e}")
            await asyncio.sleep(2)
                        
    async def watchdog_loop(self):
        while True:
            await asyncio.sleep(15)
            for sid, details in list(self.state.items()):
                if details.get("enabled") and details.get("status") in ["error", "stopped"]:
                    config = details["config"]
                    if config.ha_mode == "active_passive" and not await self.owns_lease(sid):
                        continue
                    logger.warning(f"[WATCHDOG] Recovering {sid}")
                    use_backup = (details["active_input"] == "backup")
                    asyncio.create_task(self.start_service(details["config"], use_backup))

    async def hardware_loop(self):
        import psutil
        while True:
            await asyncio.sleep(4)
            try:
                cpu = psutil.cpu_percent(interval=None)
                ram = psutil.virtual_memory().percent
                await self.redis.publish("telemetry_hardware", json.dumps({"node": NODE_ROLE, "cpu": cpu, "ram": ram}))
            except: pass

    async def metrics_loop(self):
        while True:
            await asyncio.sleep(2)
            try:
                for sid, details in self.state.items():
                    # Export dict cleanly
                    export = {
                        "status": details["status"],
                        "active_input": details["active_input"],
                        "bitrate": details["bitrate"],
                        "cc": details["cc"],
                        "error_msg": details["error_msg"]
                    }
                    await self.redis.hset("stream_metrics_cache", sid, json.dumps(export))
                    await self.redis.publish("telemetry_metrics", json.dumps({
                        "service_id": sid, 
                        "service_name": details["config"].name, 
                        "node": NODE_ROLE, 
                        "bitrate": details["bitrate"], 
                        "cc": details["cc"], 
                        "status": details["status"]
                    }))
            except Exception as e:
                logger.error(f"Metrics Pub Error: {e}")

    async def stop_service(self, service_id: str, release_lease: bool = True):
        if service_id in self.processes:
            p = self.processes[service_id]
            try:
                p.terminate()
            except: pass
            del self.processes[service_id]
            if service_id in self.state:
                self.state[service_id]["status"] = "stopped"
        cleanup_hls_outputs(os.path.join(PREVIEW_DIR, service_id))
        if release_lease:
            await self.release_lease(service_id)

    async def start_service(self, config: ServiceConfig, use_backup: bool = False):
        await self.stop_service(config.id, release_lease=False)
        
        self.state[config.id] = {
            "config": config,
            "status": "starting",
            "active_input": "backup" if use_backup else "main",
            "bitrate": 0,
            "cc": 0,
            "error_msg": "",
            "enabled": True
        }
        await self.publish_service_state(config.id)
        
        try:
            preview_dir = os.path.join(PREVIEW_DIR, config.id)
            os.makedirs(preview_dir, exist_ok=True)
            input_url = build_input_url(config, use_backup, NODE_ROLE)
            ffmpeg_cmd = build_ffmpeg_command(config, input_url, preview_dir, node_role=NODE_ROLE)
            self.processes[config.id] = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        except Exception as e:
            logger.error(f"Failed to prepare or launch FFmpeg for {config.id}: {e}")
            self.state[config.id]["status"] = "error"
            self.state[config.id]["error_msg"] = f"FFmpeg start failed: {e}"
            await self.publish_service_state(config.id)
            return

        self.state[config.id]["status"] = "running"
        await self.publish_service_state(config.id)
        asyncio.create_task(self.monitor_process(config.id, input_url))

    async def publish_service_state(self, service_id: str):
        details = self.state.get(service_id)
        if not details:
            return
        export = {
            "status": details["status"],
            "active_input": details["active_input"],
            "bitrate": details["bitrate"],
            "cc": details["cc"],
            "error_msg": details["error_msg"]
        }
        await self.redis.hset("stream_metrics_cache", service_id, json.dumps(export))

    async def monitor_process(self, service_id: str, input_url: str):
        process = self.processes.get(service_id)
        if not process: return
        
        last_error_line = ""
        start_time = time.time()
        found_video, probe_checked = False, False
        cc_errors, cc_window_start = 0, time.time()
        
        while True:
            try:
                line = await asyncio.wait_for(process.stderr.readline(), timeout=1.0)
                if not line: break
                line_str = line.decode('utf-8', errors='ignore').strip()
                line_lower = line_str.lower()

                if "stream #" in line_lower and ": video:" in line_lower: found_video = True

                b_match = re.search(r"bitrate=\s*([\d\.]+)", line_lower)
                if b_match: self.state[service_id]["bitrate"] = float(b_match.group(1))

                critical = ["pat found but no pmt", "could not find codec parameters", "non-existing pps"]
                if any(err in line_lower for err in critical):
                    last_error_line = line_str; process.kill(); break

                if "continuity check failed" in line_lower:
                    now = time.time()
                    if now - cc_window_start > 30: cc_errors = 0; cc_window_start = now
                    cc_errors += 1
                    self.state[service_id]["cc"] += 1
                    if cc_errors > 50: last_error_line = "Continuity Overload"; process.kill(); break
                
            except asyncio.TimeoutError:
                pass
            except: break
            
            if getattr(self.state[service_id]["config"], 'strict_probing', False) and not probe_checked:
                if time.time() - start_time > 8.0:
                    probe_checked = True
                    if not found_video:
                        last_error_line = "Strict Probing: Missing Video Track"; process.kill(); break
                        
        await process.wait()
        
        if process.returncode != 0:
            self.state[service_id]["status"] = "error"
            self.state[service_id]["error_msg"] = last_error_line or f"Failed code {process.returncode}"
            await self.publish_service_state(service_id)
            
            # Autonomic Load Balancing trigger!
            c = self.state[service_id]["config"]
            if c.auto_failover and c.backup_input_ip:
                use_backup = not (self.state[service_id]["active_input"] == "backup")
                asyncio.create_task(self.start_service(c, use_backup))
        else:
            self.state[service_id]["status"] = "stopped"
            await self.publish_service_state(service_id)

if __name__ == "__main__":
    w = WorkerNode()
    asyncio.run(w.run())
