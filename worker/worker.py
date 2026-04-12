import asyncio
import os
import json
import logging
import time
import re
import redis.asyncio as redis
from backend.models import ServiceConfig

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost")
NODE_ROLE = os.getenv("NODE_ROLE", "worker_1")
PREVIEW_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "previews")
os.makedirs(PREVIEW_DIR, exist_ok=True)

class WorkerNode:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL)
        self.processes = {}
        self.state = {}
        
    async def run(self):
        pubsub = self.redis.pubsub()
        await pubsub.subscribe("stream_commands")
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
                        if config.target_node in ["all", NODE_ROLE] or NODE_ROLE.startswith("worker"):
                            use_backup = data.get("use_backup", False)
                            asyncio.create_task(self.start_service(config, use_backup))
                            
                    elif action == "stop":
                        service_id = data.get("id")
                        if service_id in self.processes:
                            # Un-track locally
                            if service_id in self.state:
                                self.state[service_id]["enabled"] = False
                            asyncio.create_task(self.stop_service(service_id))
                except Exception as e:
                    logger.error(f"Worker Queue Error: {e}")
                        
    async def watchdog_loop(self):
        while True:
            await asyncio.sleep(15)
            for sid, details in list(self.state.items()):
                if details.get("enabled") and details.get("status") in ["error", "stopped"]:
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

    async def stop_service(self, service_id: str):
        if service_id in self.processes:
            p = self.processes[service_id]
            try:
                p.terminate()
            except: pass
            del self.processes[service_id]
            if service_id in self.state:
                self.state[service_id]["status"] = "stopped"

    async def start_service(self, config: ServiceConfig, use_backup: bool = False):
        await self.stop_service(config.id)
        
        self.state[config.id] = {
            "config": config,
            "status": "starting",
            "active_input": "backup" if use_backup else "main",
            "bitrate": 0,
            "cc": 0,
            "error_msg": "",
            "enabled": True
        }
        
        input_ip = config.backup_input_ip if use_backup and config.backup_input_ip else config.source_ip
        
        if config.source_protocol == "srt":
            input_url = f"srt://{input_ip}:{config.source_port}?mode={config.source_mode}&timeout=5000000"
            if config.local_bind_ip: input_url += f"&localbind={config.local_bind_ip}"
            if config.latency_ms: input_url += f"&latency={config.latency_ms}"
            if config.passphrase: input_url += f"&passphrase={config.passphrase}"
            if config.pbkeylen: input_url += f"&pbkeylen={config.pbkeylen}"
            if config.streamid: input_url += f"&streamid={config.streamid}"
        elif config.source_protocol == "udp":
            input_url = f"udp://{input_ip}:{config.source_port}?timeout=5000000"
        elif config.source_protocol == "rist":
            input_url = f"rist://{input_ip}:{config.source_port}?timeout=5"
        else:
            input_url = f"rtmp://{input_ip}:{config.source_port}{config.source_path or ''}"

        preview_dir = os.path.join(PREVIEW_DIR, config.id)
        os.makedirs(preview_dir, exist_ok=True)
        preview_path = os.path.join(preview_dir, "preview.jpg")

        ffmpeg_cmd = [
            "ffmpeg", "-hide_banner", "-y", "-progress", "pipe:2",
            "-i", input_url,
            "-map", "0:v?", "-map", "0:a?", "-c:v", "copy", "-c:a", "copy", "-f", "mpegts", config.destination_url,
            "-map", "0:v:0?", "-r", "1", "-update", "1", preview_path
        ]

        if getattr(config, 'enable_hls_preview', False):
            ffmpeg_cmd.extend(["-map", "0:v:0?", "-map", "0:a:0?"])
            hw_accel = os.getenv("HW_ACCEL", "cpu")
            if hw_accel == "nvidia":
                ffmpeg_cmd.extend(["-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ll"])
            else:
                ffmpeg_cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-threads", "auto"])
                
            ffmpeg_cmd.extend([
                "-b:v", "400k", "-maxrate", "400k", "-bufsize", "800k", "-vf", "scale=-2:360",
                "-c:a", "aac", "-b:a", "64k", "-f", "hls", "-hls_time", "2", "-hls_list_size", "3", "-hls_flags", "delete_segments",
                os.path.join(preview_dir, "stream.m3u8")
            ])

        if ffmpeg_cmd[-9] == "auto" or ffmpeg_cmd[-9] == "-f":
            pass # Keep offsets aligned cleanly

        self.processes[config.id] = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        self.state[config.id]["status"] = "running"
        asyncio.create_task(self.monitor_process(config.id, input_url))

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
            
            # Autonomic Load Balancing trigger!
            c = self.state[service_id]["config"]
            if c.auto_failover and c.backup_input_ip:
                use_backup = not (self.state[service_id]["active_input"] == "backup")
                asyncio.create_task(self.start_service(c, use_backup))
        else:
            self.state[service_id]["status"] = "stopped"

if __name__ == "__main__":
    w = WorkerNode()
    asyncio.run(w.run())
