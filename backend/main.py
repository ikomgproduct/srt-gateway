from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import os
import asyncio
from backend.stream_manager import manager
from prometheus_client import make_asgi_app

app = FastAPI(title="SRT Gateway API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

import psutil
from prometheus_client import Gauge
system_cpu_usage = Gauge('srt_system_cpu_usage', 'CPU Tracker', ['node'])
system_memory_usage = Gauge('srt_system_memory_usage', 'Memory Tracker', ['node'])
srt_active_services = Gauge('srt_active_services', 'Total Running Pipelines', ['node'])
srt_error_services = Gauge('srt_error_services', 'Total Crashed Pipelines', ['node'])

async def hardware_metrics_loop():
    while True:
        try:
            system_cpu_usage.labels(node=manager.node_role).set(psutil.cpu_percent(interval=None))
            system_memory_usage.labels(node=manager.node_role).set(psutil.virtual_memory().percent)
            
            active=0
            errors=0
            for s in manager.services.values():
                if s.status == "running": active += 1
                elif s.status == "error": errors += 1
            srt_active_services.labels(node=manager.node_role).set(active)
            srt_error_services.labels(node=manager.node_role).set(errors)
        except Exception: pass
        await asyncio.sleep(4)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(manager.cluster_sync_loop())
    asyncio.create_task(manager.watchdog_loop())
    asyncio.create_task(hardware_metrics_loop())

@app.get("/api/node_role")
async def get_node_role():
    return {"role": manager.node_role}

from fastapi.staticfiles import StaticFiles

@app.get("/api/services")
async def list_services():
    return [s for s in manager.services.values()]

from backend.models import ServiceConfig

@app.post("/api/services")
async def create_service(config: ServiceConfig):
    import uuid
    if not config.id:
        config.id = str(uuid.uuid4())
    try:
        state = manager.add_service(config)
        return state
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/api/services/{service_id}")
async def update_service(service_id: str, config: ServiceConfig):
    state = manager.get_service(service_id)
    if not state:
        raise HTTPException(status_code=404, detail="Service not found")
    config.id = service_id
    state.config = config
    manager.save_configs()
    # Manual restart logic bypassed, the cluster loop will catch this naturally!
    await manager.stop_service(service_id)
    if config.enabled:
        await manager.start_service(service_id)
    return state

@app.delete("/api/services/{service_id}")
async def delete_service(service_id: str):
    await manager.stop_service(service_id)
    manager.delete_service(service_id)
    return {"status": "deleted"}

@app.post("/api/services/{service_id}/start")
async def start_service(service_id: str, use_backup: bool = False):
    state = manager.get_service(service_id)
    if not state:
        raise HTTPException(status_code=404, detail="Service not found")
    state.config.enabled = True
    manager.save_configs()
    await manager.start_service(service_id, use_backup)
    return {"status": "started"}

@app.post("/api/services/{service_id}/stop")
async def stop_service(service_id: str):
    state = manager.get_service(service_id)
    if not state:
        raise HTTPException(status_code=404, detail="Service not found")
    state.config.enabled = False
    manager.save_configs()
    await manager.stop_service(service_id)
    return {"status": "stopped"}

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
