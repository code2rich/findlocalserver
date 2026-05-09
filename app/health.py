from __future__ import annotations

import socket
import asyncio
from typing import Optional

import httpx

from .models import Service, ServiceType


async def check_health(svc: Service, timeout: float = 3.0) -> str:
    if svc.type == ServiceType.HTTP:
        return await _check_http(svc, timeout)
    else:
        return await _check_tcp(svc, timeout)


async def check_health_batch(services: list[Service], timeout: float = 3.0) -> dict[str, str]:
    results = {}
    tasks = {svc.id: check_health(svc, timeout) for svc in services}
    task_ids = list(tasks.keys())
    task_coros = list(tasks.values())
    task_results = await asyncio.gather(*task_coros, return_exceptions=True)
    for svc_id, result in zip(task_ids, task_results):
        results[svc_id] = result if isinstance(result, str) else "unhealthy"
    return results


async def _check_http(svc: Service, timeout: float) -> str:
    host = "localhost" if svc.host in ("0.0.0.0", "::", "*") else svc.host
    scheme = "https" if svc.port == 443 else "http"
    url = f"{scheme}://{host}:{svc.port}/"
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=False, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "FindLocalServer/1.0"})
            return "healthy" if resp.status_code < 500 else "unhealthy"
    except Exception:
        return "unhealthy"


async def _check_tcp(svc: Service, timeout: float) -> str:
    host = "localhost" if svc.host in ("0.0.0.0", "::", "*") else svc.host
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, svc.port),
            timeout=timeout,
        )
        writer.close()
        await writer.wait_closed()
        return "healthy"
    except Exception:
        return "unhealthy"
