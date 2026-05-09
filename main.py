from __future__ import annotations

import json
import time
import socket
import asyncio
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    load_config, get_manual_services, get_ignore_ports,
    get_ignore_processes, get_http_probe_config, get_refresh_interval,
    get_server_config,
)
from app.models import Service, ServiceType
from app.scanner import scan_ports, probe_http, probe_banners
from app.docker_scanner import scan_docker_containers
from app.health import check_health, check_health_batch

logger = logging.getLogger("findlocalserver")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PREFS_FILE = DATA_DIR / "preferences.json"

app = FastAPI(title="FindLocalServer")

config_cache: dict = {}
services_cache: list[Service] = []
services_cache_time: float = 0
preferences: dict = {"favorites": [], "groups": {}}


def load_preferences():
    global preferences
    if PREFS_FILE.exists():
        try:
            with open(PREFS_FILE, "r", encoding="utf-8") as f:
                preferences = json.load(f)
        except Exception:
            preferences = {"favorites": [], "groups": {}}


def save_preferences():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PREFS_FILE, "w", encoding="utf-8") as f:
        json.dump(preferences, f, ensure_ascii=False, indent=2)


def apply_preferences(services: list[Service]) -> list[Service]:
    fav_ids = set(preferences.get("favorites", []))
    groups = preferences.get("groups", {})
    for svc in services:
        svc.favorite = svc.id in fav_ids
        svc.group = groups.get(svc.id, "")
    return services


def apply_manual_services(services: list[Service], manual: list[dict]) -> list[Service]:
    manual_by_port: dict[int, dict] = {}
    for m in manual:
        port = m.get("port")
        if port:
            manual_by_port[port] = m

    result = list(services)
    existing_ports = {s.port for s in services}

    for port, manual_svc in manual_by_port.items():
        if port in existing_ports:
            for svc in result:
                if svc.port == port:
                    if manual_svc.get("name"):
                        svc.name = manual_svc["name"]
                    if manual_svc.get("type"):
                        try:
                            svc.type = ServiceType(manual_svc["type"])
                        except ValueError:
                            pass
                    if manual_svc.get("group"):
                        svc.group = manual_svc["group"]
                    break
        else:
            svc_type = ServiceType.UNKNOWN
            if manual_svc.get("type"):
                try:
                    svc_type = ServiceType(manual_svc["type"])
                except ValueError:
                    pass
            result.append(Service(
                port=port,
                name=manual_svc.get("name", f"Port {port}"),
                type=svc_type,
                group=manual_svc.get("group", ""),
            ))

    return result


async def do_scan() -> list[Service]:
    cfg = load_config()
    ignore_ports = get_ignore_ports(cfg)
    ignore_procs = get_ignore_processes(cfg)
    http_cfg = get_http_probe_config(cfg)

    services = scan_ports(ignore_ports, ignore_procs)

    docker_services = scan_docker_containers()
    existing_ports = {s.port for s in services}
    for ds in docker_services:
        if ds.port in existing_ports:
            for svc in services:
                if svc.port == ds.port:
                    svc.is_docker = True
                    svc.container_name = ds.container_name
                    # Docker name is better than lsof truncated name (com.docke)
                    if ds.name:
                        svc.name = ds.name
                    if ds.type != ServiceType.UNKNOWN and svc.type == ServiceType.UNKNOWN:
                        svc.type = ds.type
                    svc.extra.update(ds.extra)
                    break
        else:
            services.append(ds)

    if http_cfg.get("enabled", True):
        timeout = http_cfg.get("timeout", 2)
        await probe_http(services, timeout=timeout)

    await probe_banners(services)

    manual = get_manual_services(cfg)
    services = apply_manual_services(services, manual)

    # Final dedup by port (Docker may return same port with 0.0.0.0 and ::)
    self_port = get_server_config(cfg).get("port", 9999)
    seen_ports: set[int] = set()
    deduped: list[Service] = []
    for svc in services:
        if svc.port == self_port:
            continue
        if svc.port not in seen_ports:
            seen_ports.add(svc.port)
            deduped.append(svc)
    services = deduped

    services = apply_preferences(services)

    services.sort(key=lambda s: (not s.favorite, s.group, s.port))
    return services


@app.on_event("startup")
async def startup():
    global config_cache, services_cache, services_cache_time
    load_preferences()
    config_cache = load_config()
    services_cache = await do_scan()
    services_cache_time = time.time()


@app.get("/api/services")
async def get_services():
    return [s.to_dict() for s in services_cache]


@app.post("/api/services/refresh")
async def refresh_services():
    global services_cache, services_cache_time
    services_cache = await do_scan()
    services_cache_time = time.time()
    return [s.to_dict() for s in services_cache]


@app.get("/api/services/{svc_id}/health")
async def service_health(svc_id: str):
    svc = next((s for s in services_cache if s.id == svc_id), None)
    if not svc:
        raise HTTPException(status_code=404, detail="服务不存在")
    status = await check_health(svc)
    svc.status = status
    return {"id": svc_id, "status": status}


@app.post("/api/services/refresh-health")
async def refresh_health():
    if not services_cache:
        return {}
    results = await check_health_batch(services_cache)
    for svc in services_cache:
        if svc.id in results:
            svc.status = results[svc.id]
    return results


@app.get("/api/favorites")
async def get_favorites():
    return preferences.get("favorites", [])


@app.put("/api/favorites/{svc_id}")
async def toggle_favorite(svc_id: str):
    favs = preferences.get("favorites", [])
    if svc_id in favs:
        favs.remove(svc_id)
    else:
        favs.append(svc_id)
    preferences["favorites"] = favs
    save_preferences()

    global services_cache
    services_cache = apply_preferences(services_cache)
    return {"favorites": favs}


@app.get("/api/groups")
async def get_groups():
    groups = preferences.get("groups", {})
    active_groups = list(set(g for g in groups.values() if g))
    return active_groups


@app.put("/api/services/{svc_id}/group")
async def set_group(svc_id: str, body: dict):
    group = body.get("group", "")
    groups = preferences.get("groups", {})
    if group:
        groups[svc_id] = group
    else:
        groups.pop(svc_id, None)
    preferences["groups"] = groups
    save_preferences()

    global services_cache
    services_cache = apply_preferences(services_cache)
    return {"groups": groups}


@app.get("/api/config")
async def get_config():
    return load_config()


@app.get("/api/ips")
async def get_ips():
    ips = ["localhost", "127.0.0.1"]
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("fe80") and ":" not in ip:
                ips.append(ip)
    except Exception:
        pass
    # Also try UDP trick to get default route IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        route_ip = s.getsockname()[0]
        s.close()
        if route_ip not in ips:
            ips.append(route_ip)
    except Exception:
        pass
    return ips


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/")
async def index():
    return FileResponse(str(BASE_DIR / "static" / "index.html"))


def main():
    import uvicorn
    cfg = load_config()
    server_cfg = get_server_config(cfg)
    host = server_cfg.get("host", "0.0.0.0")
    port = server_cfg.get("port", 9999)
    print(f"FindLocalServer 启动: http://localhost:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
