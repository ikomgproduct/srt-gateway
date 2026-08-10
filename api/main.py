from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text
import os
import json
import asyncio
import redis.asyncio as redis
from api.database import engine, Base, get_db, AsyncSessionLocal
from api.models import ServiceModel
from api.schemas import ServiceConfigRequest

app = FastAPI(title="SRT API Gateway (Control Plane)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

redis_client = None

DESIRED_CONFIGS_KEY = "service_configs"
HEARTBEAT_PREFIX = "worker_heartbeat:"

async def ensure_schema_columns():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if conn.dialect.name == "postgresql":
            await conn.execute(text("ALTER TABLE services ADD COLUMN IF NOT EXISTS ha_mode VARCHAR DEFAULT 'manual'"))
            await conn.execute(text("ALTER TABLE services ADD COLUMN IF NOT EXISTS failover_node VARCHAR"))
            await conn.execute(text("ALTER TABLE services ADD COLUMN IF NOT EXISTS failover_after_seconds INTEGER DEFAULT 15"))
            await conn.execute(text("ALTER TABLE services ADD COLUMN IF NOT EXISTS failback_policy VARCHAR DEFAULT 'manual'"))
            await conn.execute(text("ALTER TABLE services ADD COLUMN IF NOT EXISTS node_bindings JSONB"))

def service_to_dict(service: ServiceModel) -> dict:
    data = service.__dict__.copy()
    data.pop("_sa_instance_state", None)
    return data

async def sync_desired_config(service_id: str, config: dict | None):
    if not redis_client:
        return
    if config is None:
        await redis_client.hdel(DESIRED_CONFIGS_KEY, service_id)
    else:
        await redis_client.hset(DESIRED_CONFIGS_KEY, service_id, json.dumps(config))

async def get_worker_roles() -> set[str]:
    if not redis_client:
        return set()
    roles = set()
    async for key in redis_client.scan_iter(f"{HEARTBEAT_PREFIX}*"):
        key_text = key.decode() if isinstance(key, bytes) else key
        roles.add(key_text.replace(HEARTBEAT_PREFIX, "", 1))
    return roles

def eligible_worker_roles(config: dict) -> set[str]:
    target_node = config.get("target_node")
    failover_node = config.get("failover_node")
    ha_mode = config.get("ha_mode", "manual")

    if target_node == "all":
        return {"all"}
    if ha_mode == "active_passive":
        return {role for role in [target_node, failover_node] if role}
    return {target_node} if target_node else set()

def service_has_eligible_worker(config: dict, worker_roles: set[str]) -> bool:
    eligible = eligible_worker_roles(config)
    if "all" in eligible:
        return bool(worker_roles)
    return bool(eligible.intersection(worker_roles))

@app.on_event("startup")
async def startup():
    global redis_client
    # Automatically generate Database Tables natively avoiding Alembic migrations for standalone deployments
    await ensure_schema_columns()
    redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost"))
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ServiceModel))
        for service in result.scalars().all():
            await sync_desired_config(service.id, service_to_dict(service))
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
    worker_roles = await get_worker_roles()
    out = []
    for s in services:
        d = s.__dict__.copy()
        d.pop("_sa_instance_state", None)
        
        # Real-time state is stored externally globally in Redis by the active tracking Workers
        stats_raw = await redis_client.hget("stream_metrics_cache", s.id)
        stats = json.loads(stats_raw) if stats_raw else {"status": "stopped", "active_input": "main"}
        status = stats.get("status", "stopped")
        error_msg = stats.get("error_msg")

        if d.get("enabled") and status == "stopped" and not service_has_eligible_worker(d, worker_roles):
            status = "pending_worker"
            expected = ", ".join(sorted(eligible_worker_roles(d))) or "none"
            online = ", ".join(sorted(worker_roles)) or "none"
            error_msg = f"No eligible worker online. Service targets: {expected}. Online workers: {online}."
        
        out.append({
            "config": d,
            "status": status,
            "active_input": stats.get("active_input", "main"),
            "error_msg": error_msg,
            "online_workers": sorted(worker_roles)
        })
    return out

@app.get("/api/workers")
async def get_workers():
    return {"workers": sorted(await get_worker_roles())}

@app.post("/api/services")
async def create_service(config: ServiceConfigRequest, db: AsyncSession = Depends(get_db)):
    import uuid
    data = config.model_dump()
    if not data.get("id"):
        data["id"] = str(uuid.uuid4())
    db_item = ServiceModel(**data)
    db.add(db_item)
    await db.commit()
    
    if data.get("enabled"):
        await sync_desired_config(data["id"], data)
        await redis_client.publish("stream_commands", json.dumps({"action": "start", "config": data}))
    else:
        await sync_desired_config(data["id"], data)
    return data

@app.put("/api/services/{service_id}")
async def update_service(service_id: str, config: ServiceConfigRequest, db: AsyncSession = Depends(get_db)):
    data = config.model_dump()
    data["id"] = service_id
    await db.merge(ServiceModel(**data))
    await db.commit()
    
    await sync_desired_config(service_id, data)
    await redis_client.publish("stream_commands", json.dumps({"action": "stop", "id": service_id}))
    if data.get("enabled"):
        await redis_client.publish("stream_commands", json.dumps({"action": "start", "config": data}))
    return data

@app.delete("/api/services/{service_id}")
async def delete_service(service_id: str, db: AsyncSession = Depends(get_db)):
    item = await db.get(ServiceModel, service_id)
    if item:
        await db.delete(item)
        await db.commit()
    await sync_desired_config(service_id, None)
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
    await sync_desired_config(service_id, d)
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
    await sync_desired_config(service_id, service_to_dict(item))
    
    await redis_client.publish("stream_commands", json.dumps({"action": "stop", "id": service_id}))
    return {"status": "stopped"}

@app.get("/api/node_role")
async def get_node_role():
    # Distributed logic masks the Web Server safely behind 'cluster'
    return {"role": "cluster"}

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
os.makedirs(os.path.join(FRONTEND_DIR, "previews"), exist_ok=True)
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
