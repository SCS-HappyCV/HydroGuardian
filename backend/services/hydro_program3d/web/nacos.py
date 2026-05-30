from __future__ import annotations

import asyncio
import json
import socket
from typing import Optional
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import ServiceSettings


class NacosRegistrar:
    def __init__(self, settings: ServiceSettings) -> None:
        self.settings = settings
        self.registered = False
        self._last_error: Optional[str] = None

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def resolve_ip(self) -> str:
        if self.settings.nacos_ip:
            return self.settings.nacos_ip
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"

    def base_url(self) -> str:
        addr = self.settings.nacos_server_addr
        if addr.startswith("http://") or addr.startswith("https://"):
            return addr
        return f"http://{addr}"

    def _instance_params(self) -> dict:
        return {
            "ip": self.resolve_ip(),
            "port": self.settings.port,
            "namespaceId": self.settings.nacos_namespace,
            "serviceName": self.settings.nacos_service_name,
            "groupName": self.settings.nacos_group,
            "clusterName": self.settings.nacos_cluster,
            "weight": 1.0,
            "healthy": "true",
            "enabled": "true",
            "ephemeral": "true",
        }

    def _request(self, method: str, path: str, params: dict) -> str:
        query = urlencode(params)
        url = f"{self.base_url()}{path}"
        if query:
            url = f"{url}?{query}"
        request = Request(url, method=method)
        try:
            with urlopen(request, timeout=10) as response:
                body = response.read().decode("utf-8", errors="replace")
                if response.status >= 300:
                    raise RuntimeError(f"{method} {path} failed: {response.status} {body}")
                return body
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed: {exc.code} {body}") from exc

    async def _request_async(self, method: str, path: str, params: dict) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._request, method, path, params)

    async def register(self) -> None:
        if not self.settings.nacos_enabled:
            return
        await self._request_async("POST", "/nacos/v1/ns/instance", self._instance_params())
        self.registered = True
        self._last_error = None

    async def deregister(self) -> None:
        if not self.settings.nacos_enabled:
            return
        params = {
            "ip": self.resolve_ip(),
            "port": self.settings.port,
            "namespaceId": self.settings.nacos_namespace,
            "serviceName": self.settings.nacos_service_name,
            "groupName": self.settings.nacos_group,
            "clusterName": self.settings.nacos_cluster,
            "ephemeral": "true",
        }
        await self._request_async("DELETE", "/nacos/v1/ns/instance", params)
        self.registered = False

    async def beat(self) -> None:
        if not self.settings.nacos_enabled:
            return
        beat = {
            "cluster": self.settings.nacos_cluster,
            "ip": self.resolve_ip(),
            "port": self.settings.port,
            "serviceName": self.settings.nacos_service_name,
            "scheduled": True,
            "weight": 1.0,
        }
        params = {
            "serviceName": self.settings.nacos_service_name,
            "groupName": self.settings.nacos_group,
            "namespaceId": self.settings.nacos_namespace,
            "ip": self.resolve_ip(),
            "port": self.settings.port,
            "beat": json.dumps(beat, ensure_ascii=False),
        }
        await self._request_async("PUT", "/nacos/v1/ns/instance/beat", params)
        self._last_error = None

    async def heartbeat_loop(self) -> None:
        while True:
            try:
                if not self.registered:
                    await self.register()
                    print(f"[hydro-program3d] registered to nacos as {self.settings.nacos_service_name}")
                else:
                    await self.beat()
            except Exception as exc:
                self.registered = False
                self._last_error = str(exc)
                print(f"[hydro-program3d] nacos heartbeat/register failed: {exc}")
            await asyncio.sleep(self.settings.nacos_heartbeat_interval_seconds)
