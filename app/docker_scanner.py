from __future__ import annotations

import logging
from typing import Optional

from .models import Service, ServiceType

logger = logging.getLogger(__name__)


def scan_docker_containers() -> list[Service]:
    try:
        import docker
    except ImportError:
        return []

    try:
        client = docker.from_env(timeout=5)
        client.ping()
    except Exception:
        logger.debug("Docker daemon 不可用，跳过容器检测")
        return []

    services = []
    try:
        containers = client.containers.list()
    except Exception as e:
        logger.debug(f"获取容器列表失败: {e}")
        return []

    for container in containers:
        container_name = container.name
        image_name = ""
        try:
            image_tags = container.image.tags
            image_name = image_tags[0] if image_tags else str(container.image.id[:12])
        except Exception:
            pass

        ports = _extract_ports(container)
        for port_info in ports:
            host_port = port_info["host_port"]
            host_ip = port_info.get("host_ip", "0.0.0.0")
            container_port = port_info["container_port"]
            proto = port_info.get("proto", "tcp")

            if not host_port:
                continue

            svc_type, svc_name = _guess_service_from_image(image_name, container_port)

            svc = Service(
                port=host_port,
                host=host_ip,
                protocol=proto,
                name=svc_name or container_name,
                type=svc_type,
                process_name=f"docker:{image_name}",
                pid=0,
                is_docker=True,
                container_name=container_name,
                extra={
                    "image": image_name,
                    "container_port": container_port,
                    "container_status": container.status,
                },
            )
            services.append(svc)

    client.close()
    return services


def _extract_ports(container) -> list[dict]:
    result = []
    attrs = container.attrs
    network_settings = attrs.get("NetworkSettings", {})
    ports = network_settings.get("Ports", {})

    for container_port_spec, host_bindings in ports.items():
        parts = container_port_spec.split("/")
        container_port = int(parts[0])
        proto = parts[1] if len(parts) > 1 else "tcp"

        if host_bindings:
            for binding in host_bindings:
                host_port = binding.get("HostPort")
                host_ip = binding.get("HostIp", "0.0.0.0")
                if host_port:
                    try:
                        host_port = int(host_port)
                    except ValueError:
                        continue
                    result.append({
                        "host_port": host_port,
                        "host_ip": host_ip,
                        "container_port": container_port,
                        "proto": proto,
                    })

    return result


def _guess_service_from_image(image_name: str, container_port: int) -> tuple[ServiceType, str]:
    if not image_name:
        return ServiceType.UNKNOWN, ""

    lower = image_name.lower()

    if "mysql" in lower:
        return ServiceType.DATABASE, "MySQL"
    if "postgres" in lower:
        return ServiceType.DATABASE, "PostgreSQL"
    if "mongo" in lower:
        return ServiceType.DATABASE, "MongoDB"
    if "redis" in lower:
        return ServiceType.CACHE, "Redis"
    if "memcached" in lower:
        return ServiceType.CACHE, "Memcached"
    if "rabbitmq" in lower:
        return ServiceType.MESSAGE_QUEUE, "RabbitMQ"
    if "kafka" in lower:
        return ServiceType.MESSAGE_QUEUE, "Kafka"
    if "nginx" in lower:
        return ServiceType.HTTP, "Nginx"
    if "apache" in lower or "httpd" in lower:
        return ServiceType.HTTP, "Apache"
    if "node" in lower or "react" in lower or "vue" in lower or "next" in lower:
        return ServiceType.HTTP, ""
    if "elasticsearch" in lower:
        return ServiceType.HTTP, "Elasticsearch"
    if "nacos" in lower:
        return ServiceType.HTTP, "Nacos"
    if "minio" in lower:
        return ServiceType.HTTP, "MinIO"

    from .scanner import KNOWN_PORTS
    if container_port in KNOWN_PORTS:
        name, svc_type = KNOWN_PORTS[container_port]
        return svc_type, name

    return ServiceType.UNKNOWN, ""
