from __future__ import annotations

import asyncio
import json
import random
import socket
from typing import Any, Dict

import httpx

from config import (
    AGENT_GRPC_PORT,
    NACOS_CLUSTER,
    NACOS_DISCOVERY_CACHE_TTL_SECONDS,
    NACOS_ENABLED,
    NACOS_GROUP,
    NACOS_IP,
    NACOS_NAMESPACE,
    NACOS_SERVER_ADDR,
    NACOS_SERVICE_NAME,
)


service_target_cache: Dict[str, tuple[str, float]] = {}
service_url_cache: Dict[str, tuple[str, float]] = {}


def resolve_service_ip() -> str:
    if NACOS_IP:
        return NACOS_IP
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def nacos_base_url() -> str:
    if NACOS_SERVER_ADDR.startswith("http://") or NACOS_SERVER_ADDR.startswith("https://"):
        return NACOS_SERVER_ADDR
    return f"http://{NACOS_SERVER_ADDR}"


def pick_instance(instances: list[Dict[str, Any]]) -> Dict[str, Any]:
    enabled_instances = [item for item in instances if item.get("enabled", True)]
    healthy_instances = [item for item in enabled_instances if item.get("healthy", True)]
    candidates = healthy_instances or enabled_instances
    if not candidates:
        raise RuntimeError("Nacos has no enabled instances")

    weighted: list[tuple[Dict[str, Any], float]] = []
    total_weight = 0.0
    for item in candidates:
        try:
            weight = max(float(item.get("weight", 1.0)), 0.0)
        except (TypeError, ValueError):
            weight = 1.0
        weighted.append((item, weight))
        total_weight += weight

    if total_weight <= 0:
        return random.choice(candidates)

    threshold = random.uniform(0.0, total_weight)
    running = 0.0
    for item, weight in weighted:
        running += weight
        if running >= threshold:
            return item
    return weighted[-1][0]


async def discover_service_instance(service_name: str) -> Dict[str, Any]:
    if not NACOS_ENABLED:
        raise RuntimeError(
            f"Nacos discovery is disabled and no direct address is configured for {service_name}"
        )
    params = {
        "serviceName": service_name,
        "groupName": NACOS_GROUP,
        "namespaceId": NACOS_NAMESPACE,
        "clusters": NACOS_CLUSTER,
        "healthyOnly": "true",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{nacos_base_url()}/nacos/v1/ns/instance/list", params=params)
        if resp.status_code >= 300:
            raise RuntimeError(
                f"Nacos discover failed for {service_name}: {resp.status_code} {resp.text}"
            )
        payload = resp.json()

    hosts = payload.get("hosts")
    if not isinstance(hosts, list) or not hosts:
        raise RuntimeError(f"Nacos has no instance for service: {service_name}")
    return pick_instance(hosts)


async def resolve_grpc_target(service_name: str, explicit_target: str = "") -> str:
    if explicit_target:
        return explicit_target

    now = asyncio.get_running_loop().time()
    cached = service_target_cache.get(service_name)
    if cached and now - cached[1] < NACOS_DISCOVERY_CACHE_TTL_SECONDS:
        return cached[0]

    instance = await discover_service_instance(service_name)
    ip = str(instance.get("ip", "")).strip()
    try:
        port = int(instance.get("port", 0))
    except (TypeError, ValueError):
        port = 0

    if not ip or port <= 0:
        raise RuntimeError(f"Nacos returned invalid instance for {service_name}: {instance}")

    target = f"{ip}:{port}"
    service_target_cache[service_name] = (target, now)
    return target


async def resolve_http_base_url(service_name: str, explicit_url: str = "") -> str:
    if explicit_url:
        return explicit_url.rstrip("/")

    now = asyncio.get_running_loop().time()
    cached = service_url_cache.get(service_name)
    if cached and now - cached[1] < NACOS_DISCOVERY_CACHE_TTL_SECONDS:
        return cached[0]

    instance = await discover_service_instance(service_name)
    ip = str(instance.get("ip", "")).strip()
    try:
        port = int(instance.get("port", 0))
    except (TypeError, ValueError):
        port = 0

    if not ip or port <= 0:
        raise RuntimeError(f"Nacos returned invalid instance for {service_name}: {instance}")

    url = f"http://{ip}:{port}"
    service_url_cache[service_name] = (url, now)
    return url


async def register_nacos_instance() -> None:
    if not NACOS_ENABLED:
        return
    params = {
        "ip": resolve_service_ip(),
        "port": AGENT_GRPC_PORT,
        "namespaceId": NACOS_NAMESPACE,
        "serviceName": NACOS_SERVICE_NAME,
        "groupName": NACOS_GROUP,
        "clusterName": NACOS_CLUSTER,
        "weight": 1.0,
        "healthy": "true",
        "enabled": "true",
        "ephemeral": "true",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{nacos_base_url()}/nacos/v1/ns/instance", params=params)
        if resp.status_code >= 300:
            raise RuntimeError(f"Nacos register failed: {resp.status_code} {resp.text}")


async def deregister_nacos_instance() -> None:
    if not NACOS_ENABLED:
        return
    params = {
        "ip": resolve_service_ip(),
        "port": AGENT_GRPC_PORT,
        "namespaceId": NACOS_NAMESPACE,
        "serviceName": NACOS_SERVICE_NAME,
        "groupName": NACOS_GROUP,
        "clusterName": NACOS_CLUSTER,
        "ephemeral": "true",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        await client.delete(f"{nacos_base_url()}/nacos/v1/ns/instance", params=params)


async def send_nacos_beat() -> None:
    if not NACOS_ENABLED:
        return
    beat = {
        "cluster": NACOS_CLUSTER,
        "ip": resolve_service_ip(),
        "port": AGENT_GRPC_PORT,
        "serviceName": NACOS_SERVICE_NAME,
        "scheduled": True,
        "weight": 1.0,
    }
    params = {
        "serviceName": NACOS_SERVICE_NAME,
        "groupName": NACOS_GROUP,
        "namespaceId": NACOS_NAMESPACE,
        "ip": resolve_service_ip(),
        "port": AGENT_GRPC_PORT,
        "beat": json.dumps(beat, ensure_ascii=False),
    }
    async with httpx.AsyncClient(timeout=10) as client:
        await client.put(f"{nacos_base_url()}/nacos/v1/ns/instance/beat", params=params)


async def nacos_heartbeat_loop() -> None:
    while True:
        try:
            await send_nacos_beat()
        except Exception as exc:
            print(f"[agent-service] nacos heartbeat failed: {exc}")
        await asyncio.sleep(5)
