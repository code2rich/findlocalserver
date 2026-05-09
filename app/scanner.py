from __future__ import annotations

import os
import re
import sys
import socket
import asyncio
import subprocess
from typing import Optional

import psutil
import httpx

from .models import Service, ServiceType


KNOWN_PORTS: dict[int, tuple[str, ServiceType]] = {
    22: ("SSH", ServiceType.INFRASTRUCTURE),
    21: ("FTP", ServiceType.INFRASTRUCTURE),
    25: ("SMTP", ServiceType.INFRASTRUCTURE),
    53: ("DNS", ServiceType.INFRASTRUCTURE),
    80: ("HTTP", ServiceType.HTTP),
    443: ("HTTPS", ServiceType.HTTP),
    3000: ("HTTP", ServiceType.HTTP),
    4000: ("HTTP", ServiceType.HTTP),
    5000: ("HTTP", ServiceType.HTTP),
    5173: ("Vite Dev", ServiceType.HTTP),
    5174: ("Vite Dev", ServiceType.HTTP),
    8000: ("HTTP", ServiceType.HTTP),
    8080: ("HTTP", ServiceType.HTTP),
    8443: ("HTTPS", ServiceType.HTTP),
    8888: ("HTTP", ServiceType.HTTP),
    9000: ("HTTP", ServiceType.HTTP),
    9090: ("HTTP", ServiceType.HTTP),
    19000: ("React Native", ServiceType.HTTP),
    19006: ("React Native", ServiceType.HTTP),
    3306: ("MySQL", ServiceType.DATABASE),
    5432: ("PostgreSQL", ServiceType.DATABASE),
    27017: ("MongoDB", ServiceType.DATABASE),
    27018: ("MongoDB", ServiceType.DATABASE),
    1433: ("SQL Server", ServiceType.DATABASE),
    1521: ("Oracle DB", ServiceType.DATABASE),
    6379: ("Redis", ServiceType.CACHE),
    11211: ("Memcached", ServiceType.CACHE),
    5672: ("RabbitMQ", ServiceType.MESSAGE_QUEUE),
    15672: ("RabbitMQ Management", ServiceType.HTTP),
    9092: ("Kafka", ServiceType.MESSAGE_QUEUE),
    2181: ("ZooKeeper", ServiceType.MESSAGE_QUEUE),
    9876: ("RocketMQ", ServiceType.MESSAGE_QUEUE),
}

HTTP_PROBE_PORTS = set(range(3000, 3100)) | {
    80, 443, 4000, 5000, 5173, 5174, 8000, 8080, 8443, 8888,
    9000, 9090, 15672, 19000, 19006, 2368, 3001, 4001, 5500, 6006,
    7000, 7070, 7474, 8001, 8081, 8082, 8181, 8383, 8800, 9091,
    9200, 9300, 9443, 9966,
}


def scan_ports(ignore_ports: list[int] | None = None,
               ignore_processes: list[str] | None = None) -> list[Service]:
    ignore_ports = set(ignore_ports or [])
    ignore_processes = set(p.lower() for p in (ignore_processes or []))

    raw_connections = _scan_psutil()
    if not raw_connections:
        raw_connections = _platform_fallback()

    # Deduplicate by port, prefer 0.0.0.0 over ::
    services: dict[tuple[int, str], Service] = {}

    for host, port, proto, pid, pname in raw_connections:
        if port in ignore_ports:
            continue
        if pname.lower() in ignore_processes:
            continue

        key = (port, proto)

        if key in services:
            existing = services[key]
            if existing.host == "0.0.0.0" and host == "::":
                continue

        known_name, known_type = KNOWN_PORTS.get(port, ("", ServiceType.UNKNOWN))

        services[key] = Service(
            port=port,
            host=host,
            protocol=proto,
            name=known_name or pname or f"Port {port}",
            type=known_type,
            process_name=pname,
            pid=pid,
        )

    return list(services.values())


def _scan_psutil() -> list[tuple[str, int, str, int, str]]:
    """Returns list of (host, port, proto, pid, process_name)"""
    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError):
        return []

    results = []
    pid_cache: dict[int, str] = {}

    for conn in connections:
        if conn.status != "LISTEN" or not conn.laddr:
            continue
        host, port = conn.laddr
        proto = "tcp" if conn.type == socket.SOCK_STREAM else "udp"
        pid = conn.pid or 0
        pname = ""
        if pid and pid not in pid_cache:
            try:
                pid_cache[pid] = psutil.Process(pid).name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pid_cache[pid] = ""
        pname = pid_cache.get(pid, "")
        results.append((host, port, proto, pid, pname))

    return results


def _scan_lsof() -> list[tuple[str, int, str, int, str]]:
    """Fallback: parse lsof output. Returns list of (host, port, proto, pid, process_name)"""
    try:
        env = dict(os.environ, LC_ALL="C")
        proc = subprocess.run(
            ["lsof", "-i", "-P", "-n", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=10, env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    results = []
    seen = set()

    for line in proc.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 9:
            continue
        pname = parts[0]
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        addr = parts[8]  # e.g. *:8080 or 127.0.0.1:6379 or [::1]:6379

        # Parse host:port
        if addr.startswith("["):
            # IPv6 [::1]:port
            bracket_end = addr.index("]")
            host = addr[1:bracket_end]
            port_str = addr[bracket_end + 2:]  # skip "]:"
        elif ":" in addr:
            last_colon = addr.rfind(":")
            host = addr[:last_colon]
            port_str = addr[last_colon + 1:]

            # Handle -> (connected state, skip)
            if "->" in addr:
                continue
        else:
            continue

        try:
            port = int(port_str)
        except ValueError:
            continue

        # Normalize host
        if host == "*":
            host = "0.0.0.0"

        dedup_key = (host, port)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        results.append((host, port, "tcp", pid, pname))

    return results


def _platform_fallback() -> list[tuple[str, int, str, int, str]]:
    """根据平台选择回退扫描方式。"""
    if sys.platform == "win32":
        return _scan_netstat()
    elif sys.platform == "linux":
        return _scan_ss() or _scan_lsof()
    else:
        return _scan_lsof()


def _parse_net_addr(addr: str) -> tuple[str, int | None]:
    """解析网络地址，如 '0.0.0.0:8080' 或 '[::]:8080' → (host, port)。"""
    if addr.startswith("["):
        bracket_end = addr.index("]")
        host = addr[1:bracket_end]
        port_str = addr[bracket_end + 2:]
    elif ":" in addr:
        if "->" in addr:
            return "", None
        last_colon = addr.rfind(":")
        host = addr[:last_colon]
        port_str = addr[last_colon + 1:]
    else:
        return "", None

    try:
        port = int(port_str)
    except ValueError:
        return "", None

    if host == "*":
        host = "0.0.0.0"

    return host, port


def _scan_netstat() -> list[tuple[str, int, str, int, str]]:
    """Windows 回退：解析 netstat -ano 输出。"""
    try:
        proc = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    results = []
    seen = set()

    for line in proc.stdout.splitlines():
        if "LISTENING" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue

        addr = parts[1]
        try:
            pid = int(parts[4])
        except ValueError:
            pid = 0

        host, port = _parse_net_addr(addr)
        if port is None:
            continue

        dedup_key = (host, port)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        pname = ""
        if pid:
            try:
                pname = psutil.Process(pid).name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        results.append((host, port, "tcp", pid, pname))

    return results


def _scan_ss() -> list[tuple[str, int, str, int, str]]:
    """Linux 回退：解析 ss -tlnp 输出。"""
    try:
        env = dict(os.environ, LC_ALL="C")
        proc = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True, text=True, timeout=10, env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    results = []
    seen = set()

    for line in proc.stdout.splitlines():
        if "LISTEN" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue

        local_addr = parts[3]

        rest = " ".join(parts[5:]) if len(parts) > 5 else ""
        pid = 0
        pname = ""
        pid_m = re.search(r'pid=(\d+)', rest)
        if pid_m:
            pid = int(pid_m.group(1))
        name_m = re.search(r'"([^"]+)"', rest)
        if name_m:
            pname = name_m.group(1)

        host, port = _parse_net_addr(local_addr)
        if port is None:
            continue

        dedup_key = (host, port)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        results.append((host, port, "tcp", pid, pname))

    return results


async def probe_http(services: list[Service], timeout: float = 2.0) -> list[Service]:
    async def _probe(svc: Service):
        host = "localhost" if svc.host in ("0.0.0.0", "::", "*") else svc.host
        scheme = "https" if svc.port == 443 else "http"
        url = f"{scheme}://{host}:{svc.port}/"

        try:
            async with httpx.AsyncClient(timeout=timeout, verify=False, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "FindLocalServer/1.0"})
                content_type = resp.headers.get("content-type", "")
                server = resp.headers.get("server", "")
                body = resp.text[:4096]

                svc.type = ServiceType.HTTP
                svc.extra["http_status"] = resp.status_code
                svc.extra["http_server"] = server

                has_html = "text/html" in content_type or "<html" in body.lower() or "<!doctype html" in body.lower()
                is_json = "application/json" in content_type or body.strip().startswith("{")

                if has_html:
                    title = ""
                    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
                    if m:
                        title = m.group(1).strip()[:100]
                    svc.extra["http_title"] = title
                    svc.extra["page_type"] = "webpage"
                    if not svc.name or svc.name == f"Port {svc.port}":
                        svc.name = title or server or f"HTTP ({svc.port})"
                elif is_json:
                    svc.extra["page_type"] = "api"
                    if not svc.name or svc.name == f"Port {svc.port}":
                        svc.name = server or f"API ({svc.port})"
                else:
                    svc.extra["page_type"] = "service"
                    if not svc.name or svc.name == f"Port {svc.port}":
                        svc.name = server or f"HTTP ({svc.port})"

        except httpx.ConnectError:
            svc.extra["page_type"] = "unreachable"
        except httpx.TimeoutException:
            svc.extra["page_type"] = "timeout"
        except Exception:
            pass

    candidates = [s for s in services
                  if s.type == ServiceType.HTTP
                  or s.port in HTTP_PROBE_PORTS
                  or s.type == ServiceType.UNKNOWN]
    if candidates:
        await asyncio.gather(*[_probe(s) for s in candidates])

    return services


async def probe_banners(services: list[Service], timeout: float = 2.0) -> list[Service]:
    async def _probe(svc: Service):
        host = "localhost" if svc.host in ("0.0.0.0", "::", "*") else svc.host
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, svc.port),
                timeout=timeout,
            )
            try:
                banner = await asyncio.wait_for(reader.read(1024), timeout=timeout)
                text = banner.decode("utf-8", errors="replace").strip()[:200]
                if text:
                    svc.extra["banner"] = text
                    _identify_from_banner(svc, text)
            finally:
                writer.close()
                await writer.wait_closed()
        except Exception:
            pass

    non_http = [s for s in services if s.type != ServiceType.HTTP]
    if non_http:
        await asyncio.gather(*[_probe(s) for s in non_http])

    return services


def _identify_from_banner(svc: Service, banner: str):
    lower = banner.lower()
    if "mysql" in lower:
        svc.name = "MySQL"
        svc.type = ServiceType.DATABASE
    elif "postgres" in lower:
        svc.name = "PostgreSQL"
        svc.type = ServiceType.DATABASE
    elif "mongodb" in lower:
        svc.name = "MongoDB"
        svc.type = ServiceType.DATABASE
    elif "redis" in lower or banner.startswith("-ERR") or banner.startswith("+"):
        svc.name = "Redis"
        svc.type = ServiceType.CACHE
        if banner.startswith("$"):
            svc.extra["redis_info"] = "Redis Sentinel"
    elif "amqp" in lower:
        svc.name = "RabbitMQ"
        svc.type = ServiceType.MESSAGE_QUEUE
    elif "ssh" in lower:
        svc.name = "SSH"
        svc.type = ServiceType.INFRASTRUCTURE
    elif "ftp" in lower:
        svc.name = "FTP"
        svc.type = ServiceType.INFRASTRUCTURE
    elif "smtp" in lower:
        svc.name = "SMTP"
        svc.type = ServiceType.INFRASTRUCTURE
