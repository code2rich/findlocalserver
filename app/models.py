from __future__ import annotations

import hashlib
from enum import Enum
from dataclasses import dataclass, field


class ServiceType(str, Enum):
    HTTP = "http"
    DATABASE = "database"
    CACHE = "cache"
    MESSAGE_QUEUE = "mq"
    INFRASTRUCTURE = "infra"
    UNKNOWN = "unknown"


SERVICE_TYPE_ICONS = {
    ServiceType.HTTP: "🌐",
    ServiceType.DATABASE: "🗄️",
    ServiceType.CACHE: "⚡",
    ServiceType.MESSAGE_QUEUE: "📨",
    ServiceType.INFRASTRUCTURE: "🔧",
    ServiceType.UNKNOWN: "❓",
}


@dataclass
class Service:
    port: int
    host: str = "0.0.0.0"
    protocol: str = "tcp"
    name: str = ""
    type: ServiceType = ServiceType.UNKNOWN
    process_name: str = ""
    pid: int = 0
    is_docker: bool = False
    container_name: str = ""
    extra: dict = field(default_factory=dict)
    status: str = "up"
    group: str = ""
    favorite: bool = False

    def __post_init__(self):
        if not self.name:
            self.name = self._default_name()
        self.id = self._generate_id()

    def _generate_id(self) -> str:
        raw = f"{self.host}:{self.port}:{self.protocol}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def _default_name(self) -> str:
        if self.process_name:
            return self.process_name
        return f"Port {self.port}"

    def to_dict(self, display_host: str = "") -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "icon": SERVICE_TYPE_ICONS.get(self.type, "❓"),
            "port": self.port,
            "protocol": self.protocol,
            "host": self.host,
            "process_name": self.process_name,
            "pid": self.pid,
            "is_docker": self.is_docker,
            "container_name": self.container_name,
            "extra": self.extra,
            "status": self.status,
            "group": self.group,
            "favorite": self.favorite,
            "url": self._build_url_with_host(display_host),
        }

    def _build_url(self) -> str:
        return self._build_url_with_host("")

    def _build_url_with_host(self, display_host: str = "") -> str:
        if self.type == ServiceType.HTTP:
            scheme = "https" if self.port == 443 else "http"
            if self.host in ("127.0.0.1", "localhost"):
                host = "localhost"
            elif display_host:
                host = display_host
            else:
                host = "localhost" if self.host in ("0.0.0.0", "::", "*") else self.host
            return f"{scheme}://{host}:{self.port}"
        return ""
