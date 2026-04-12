from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import os
import json
import asyncio
import redis.asyncio as redis
from api.database import engine, Base, get_db
from api.models import ServiceModel

app = FastAPI(title="SRT API Gateway (Control Plane)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

redis_client = None

@app.on_event("startup")
async def startup():
    global redis_client
    # Automatically generate Database Tables natively avoiding Alembic migrations for standalone deployments
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost"))
    asyncio.create_task(hardware_metrics_loop())

@app.on_event("shutdown")
async def shutdown():
    if redis_client:
        await redis_client.close()

import psutil

async def hardware_metrics_loop():
    while True:
        try:
            if redis_client:
                cpu = psutil.cpu_percent(interval=None)
                ram = psutil.virtual_memory().percent
                await redis_client.publish("telemetry_hardware", json.dumps({"node": "cluster", "cpu": cpu, "ram": ram}))
        except: pass
        await asyncio.sleep(4)

# --- Microservices REST API ---
# Injects logic entirely into Redis instead of locking the Python Process!

@app.get("/api/services")
async def get_services(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ServiceModel))
    services = result.scalars().all()
    out = []
    for s in services:
        d = s.__dict__.copy()
        d.pop("_sa_instance_state", None)
        
        # Real-time state is stored externally globally in Redis by the active tracking Workers
        stats_raw = await redis_client.hget("stream_metrics_cache", s.id)
        stats = json.loads(stats_raw) if stats_raw else {"status": "stopped", "active_input": "main"}
        
        out.append({
            "config": d,
            "status": stats.get("status", "stopped"),
            "active_input": stats.get("active_input", "main"),
            "error_msg": stats.get("error_msg")
        })
    return out

@app.post("/api/services")
async def create_service(config: dict, db: AsyncSession = Depends(get_db)):
    import uuid
    if not config.get("id"):
        config["id"] = str(uuid.uuid4())
    db_item = ServiceModel(**config)
    db.add(db_item)
    await db.commit()
    
    if config.get("enabled"):
        await redis_client.publish("stream_commands", json.dumps({"action": "start", "config": config}))
    return config

@app.put("/api/services/{service_id}")
async def update_service(service_id: str, config: dict, db: AsyncSession = Depends(get_db)):
    config["id"] = service_id
    await db.merge(ServiceModel(**config))
    await db.commit()
    
    await redis_client.publish("stream_commands", json.dumps({"action": "stop", "id": service_id}))
    if config.get("enabled"):
        await redis_client.publish("stream_commands", json.dumps({"action": "start", "config": config}))
    return config

@app.delete("/api/services/{service_id}")
async def delete_service(service_id: str, db: AsyncSession = Depends(get_db)):
    item = await db.get(ServiceModel, service_id)
    if item:
        await db.delete(item)
        await db.commit()
    await redis_client.publish("stream_commands", json.dumps({"action": "stop", "id": service_id}))
    return {"status": "deleted"}

@app.post("/api/services/{service_id}/start")
async def start_service(service_id: str, use_backup: bool = False, db: AsyncSession = Depends(get_db)):
    item = await db.get(ServiceModel, service_id)
    if not item: raise HTTPException(404)
    item.enabled = True
    await db.commit()
    
    d = item.__dict__.copy()
    d.pop("_sa_instance_state", None)
    await redis_client.publish("stream_commands", json.dumps({
        "action": "start", 
        "config": d, 
        "use_backup": use_backup
    }))
    return {"status": "started"}

@app.post("/api/services/{service_id}/stop")
async def stop_service(service_id: str, db: AsyncSession = Depends(get_db)):
    item = await db.get(ServiceModel, service_id)
    if not item: raise HTTPException(404)
    item.enabled = False
    await db.commit()
    
    await redis_client.publish("stream_commands", json.dumps({"action": "stop", "id": service_id}))
    return {"status": "stopped"}

@app.get("/api/node_role")
async def get_node_role():
    # Distributed logic masks the Web Server safely behind 'cluster'
    return {"role": "cluster"}

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
os.makedirs(os.path.join(FRONTEND_DIR, "previews"), exist_ok=True)
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
