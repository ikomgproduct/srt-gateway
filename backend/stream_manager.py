import asyncio
import logging
import json
import os
from typing import Dict, Optional
from backend.models import ServiceConfig, ServiceState, StreamStatus
from backend.ffmpeg_builder import build_ffmpeg_command, build_input_url
from prometheus_client import Gauge, Counter
import re

logger = logging.getLogger(__name__)

stream_bitrate_kbps = Gauge('srt_stream_bitrate_kbps', 'Current Muxer processing bitrate', ['service_id', 'service_name', 'node'])
stream_cc_errors_total = Counter('srt_stream_cc_errors_total', 'Continuity packet dropping aggregate', ['service_id', 'service_name', 'node'])
CONFIG_FILE = "config.json"

class StreamManager:
    def __init__(self):
        self.services: Dict[str, ServiceState] = {}
        self.processes: Dict[str, asyncio.subprocess.Process] = {}
        self.node_role = os.getenv("NODE_ROLE", "primary")
        self.last_mtime = 0
        self.load_configs()

    def save_configs(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                data = [s.config.model_dump() for s in self.services.values()]
                json.dump(data, f, indent=2)
            if os.path.exists(CONFIG_FILE):
                self.last_mtime = os.path.getmtime(CONFIG_FILE)
        except Exception as e:
            logger.error(f"Failed to save configs: {e}")

    def load_configs(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                for item in data:
                    if "listen_port" in item:
                        item["source_port"] = item.pop("listen_port")
                        item["source_protocol"] = "srt"
                        item["source_ip"] = "0.0.0.0"
                    c = ServiceConfig(**item)
                    self.services[c.id] = ServiceState(config=c)
        except Exception as e:
            logger.error(f"Failed to load configs: {e}")

    async def cluster_sync_loop(self):
        while True:
            await asyncio.sleep(2)
            if os.path.exists(CONFIG_FILE):
                try:
                    mtime = os.path.getmtime(CONFIG_FILE)
                    if mtime > self.last_mtime:
                        self.last_mtime = mtime
                        # Safely deserialize external JSON array edits from peer nodes
                        with open(CONFIG_FILE, "r") as f:
                            data = json.load(f)
                        
                        incoming_ids = []
                        for item in data:
                            c = ServiceConfig(**item)
                            incoming_ids.append(c.id)
                            if c.id not in self.services:
                                self.services[c.id] = ServiceState(config=c)
                            else:
                                self.services[c.id].config = c
                                
                        for sid in list(self.services.keys()):
                            if sid not in incoming_ids:
                                if sid in self.processes:
                                    await self.stop_service(sid)
                                del self.services[sid]
                                
                        # Orchestrate hardware load-balances per Role identity
                        for sid, state in self.services.items():
                            should_run = state.config.enabled and (state.config.target_node in ["all", self.node_role] or self.node_role == "standalone")
                            is_running = state.status in [StreamStatus.RUNNING, StreamStatus.STARTING]
                            
                            if should_run and state.status == StreamStatus.STOPPED:
                                logger.warning(f"Cluster Identity: Assuming process control out of {sid} on {self.node_role.upper()} node.")
                                asyncio.create_task(self.start_service(sid))
                            elif not should_run and is_running:
                                logger.warning(f"Cluster Identity: Relinquishing hardware process of {sid} from {self.node_role.upper()} node.")
                                asyncio.create_task(self.stop_service(sid))
                except Exception as e:
                    logger.error(f"Cluster synchronization failure: {e}")

    async def watchdog_loop(self):
        """Monitors explicitly enabled pipelines and autonomously recovers them if they crashed."""
        while True:
            await asyncio.sleep(15)
            for service_id, state in list(self.services.items()):
                if getattr(state.config, 'enabled', False):
                    if state.config.target_node in ["all", self.node_role] or self.node_role == "standalone":
                        if state.status in ["error", "stopped"]:
                            logger.warning(f"[WATCHDOG] Pipeline {service_id} connection dropped or crashed! Executing graceful auto-recovery...")
                            use_backup = (state.active_input == "backup")
                            asyncio.create_task(self.start_service(service_id, use_backup))

    def add_service(self, config: ServiceConfig) -> ServiceState:
        if config.id in self.services:
            raise ValueError("Service ID already exists")
        state = ServiceState(config=config)
        self.services[config.id] = state
        self.save_configs()
        return state

    def get_service(self, service_id: str) -> Optional[ServiceState]:
        return self.services.get(service_id)

    def delete_service(self, service_id: str):
        if service_id in self.processes:
            pass
        if service_id in self.services:
            del self.services[service_id]
            self.save_configs()

    async def start_service(self, service_id: str, use_backup: bool = False):
        state = self.services.get(service_id)
        if not state:
            raise ValueError("Service not found")
            
        if service_id in self.processes and self.processes[service_id].returncode is None:
            logger.warning(f"Service {service_id} is already running.")
            return

        state.status = StreamStatus.STARTING
        state.active_input = "backup" if use_backup else "main"
        
        preview_dir = os.path.join("frontend", "previews", service_id)
        os.makedirs(preview_dir, exist_ok=True)
        for file_name in os.listdir(preview_dir):
            if file_name.endswith(".ts") or file_name.endswith(".m3u8") or file_name.endswith(".jpg"):
                os.remove(os.path.join(preview_dir, file_name))
                
        preview_path = os.path.join(preview_dir, "preview.jpg")

        input_url = build_input_url(state.config, use_backup, self.node_role)

        logger.info(f"Connecting Active {state.active_input.upper()} Feed to stream orchestrator: {input_url}")

        ffmpeg_cmd = build_ffmpeg_command(state.config, input_url, preview_dir)
            
        try:
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            self.processes[service_id] = process
            state.pid = process.pid
            state.status = StreamStatus.RUNNING
            state.error_msg = None
            
            asyncio.create_task(self.monitor_process(service_id))
        except Exception as e:
            state.status = StreamStatus.ERROR
            state.error_msg = str(e)
            logger.error(f"Failed to start pipeline {service_id}: {e}")

    async def stop_service(self, service_id: str):
        state = self.services.get(service_id)
        if state:
            state.status = StreamStatus.STOPPED
            state.pid = None
            
        process = self.processes.get(service_id)
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
            
        if state:
            try:
                stream_bitrate_kbps.labels(service_id=service_id, service_name=state.config.name, node=self.node_role).set(0)
            except Exception: pass

        if service_id in self.processes:
            del self.processes[service_id]

    async def monitor_process(self, service_id: str):
        process = self.processes.get(service_id)
        state = self.services.get(service_id)
        if not process or not state:
            return
            
        import time
        start_time = time.time()
        found_video = False
        found_audio = False
        try:
            stream_cc_errors_total.labels(service_id=service_id, service_name=state.config.name, node=self.node_role).inc(0)
            stream_bitrate_kbps.labels(service_id=service_id, service_name=state.config.name, node=self.node_role).set(0)
        except: pass
        probe_checked = False
        cc_errors = 0
        cc_window_start = time.time()
        
        last_error_line = ""
        while True:
            try:
                line = await asyncio.wait_for(process.stderr.readline(), timeout=1.0)
                if not line:
                    break
                line_str = line.decode('utf-8', errors='ignore').strip()
                if line_str:
                    logger.info(f"[FFMPEG] {line_str}")
                    line_lower = line_str.lower()
                    
                    if "error" in line_lower or "invalid" in line_lower or "no such file" in line_lower or "timeout" in line_lower:
                        last_error_line = line_str
                    elif not last_error_line:
                        last_error_line = line_str
                        
                    b_match = re.search(r"bitrate=\s*([\d\.]+)", line_lower)
                    if b_match:
                        try:
                            stream_bitrate_kbps.labels(service_id=service_id, service_name=state.config.name, node=self.node_role).set(float(b_match.group(1)))
                        except: pass

                    if getattr(state.config, 'strict_probing', False):
                        if "stream #" in line_lower and ": video:" in line_lower:
                            found_video = True
                        if "stream #" in line_lower and ": audio:" in line_lower:
                            found_audio = True
                            
                        critical_errors = ["pat found but no pmt", "could not find codec parameters", "non-existing pps"]
                        if any(err in line_lower for err in critical_errors):
                            logger.error(f"Piping corrupted! Strict format failure: {line_str}")
                            last_error_line = line_str
                            process.kill()
                            break
                            
                        if "continuity check failed" in line_lower:
                            stream_cc_errors_total.labels(service_id=service_id, service_name=state.config.name, node=self.node_role).inc()
                            now = time.time()
                            if now - cc_window_start > 30:
                                cc_errors = 0
                                cc_window_start = now
                            cc_errors += 1
                            if cc_errors > 50:
                                logger.error(f"Excessive CC packet dropping! Strict format threshold breached.")
                                last_error_line = "Continuity check threshold exceeded (Bad line health)"
                                process.kill()
                                break
                                
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                break
                
            if getattr(state.config, 'strict_probing', False) and not probe_checked:
                if time.time() - start_time > 8.0:
                    probe_checked = True
                    if not found_video:
                        last_error_line = "Strict Probing Failed: Missing Video Track within 8s"
                        logger.error(f"Service {service_id} blocked: {last_error_line}")
                        try:
                            process.kill()
                        except: pass
                        break
            
        await process.wait()
        
        try:
            stream_bitrate_kbps.labels(service_id=service_id, service_name=state.config.name, node=self.node_role).set(0)
        except: pass

        if state.status == StreamStatus.RUNNING:
            state.status = StreamStatus.ERROR
            err_msg = last_error_line if last_error_line else f"Code {process.returncode} (Timeout/Data Loss)"
            state.error_msg = err_msg
            logger.error(f"Pipeline crashed. Failure trace: {state.error_msg}")
            
            asyncio.create_task(self.auto_restart(service_id))

    async def auto_restart(self, service_id: str, delay: int = 5):
        await asyncio.sleep(delay)
        state = self.get_service(service_id)
        if state and state.config.enabled and state.status == StreamStatus.ERROR:
            logger.info(f"Auto-restarting pipeline {service_id}...")
            
            use_backup = (state.active_input == "backup")
            if getattr(state.config, 'auto_failover', False):
                use_backup = not use_backup
                logger.warning(f"AUTO-FAILOVER TRIGGERED on starvation. Switching connection pointer.")
                
            await self.start_service(service_id, use_backup=use_backup)

manager = StreamManager()
