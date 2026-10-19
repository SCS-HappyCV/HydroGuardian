from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator


class RedisPresence:
    def __init__(self, url: str, prefix: str = "hydro:worker", ttl_seconds: int = 45) -> None:
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("Redis integration requires redis") from exc
        self.client = redis.Redis.from_url(url, decode_responses=True)
        self.prefix = prefix.rstrip(":")
        self.ttl_seconds = max(int(ttl_seconds), 5)

    def _key(self, worker_id: str) -> str:
        return f"{self.prefix}:{worker_id}"

    def heartbeat(self, worker_id: str, payload: dict[str, Any]) -> None:
        self.client.set(self._key(worker_id), json.dumps(payload), ex=self.ttl_seconds)

    def remove(self, worker_id: str) -> None:
        self.client.delete(self._key(worker_id))

    def snapshot(self) -> list[dict[str, Any]]:
        result = []
        for key in self.client.scan_iter(match=f"{self.prefix}:*"):
            value = self.client.get(key)
            if value:
                try:
                    result.append(json.loads(value))
                except json.JSONDecodeError:
                    continue
        return result

    @contextmanager
    def lock(self, name: str, timeout: int = 60, blocking_timeout: int = 5) -> Iterator[bool]:
        lock = self.client.lock(f"{self.prefix}:lock:{name}", timeout=timeout, blocking_timeout=blocking_timeout)
        acquired = lock.acquire()
        try:
            yield acquired
        finally:
            if acquired:
                lock.release()


class RabbitEventBus:
    def __init__(self, url: str, exchange: str = "hydro.events") -> None:
        try:
            import pika
        except ImportError as exc:
            raise RuntimeError("RabbitMQ integration requires pika") from exc
        self.url = url
        self.exchange = exchange
        self._pika = pika
        self._local = threading.local()

    def _channel(self):
        connection = getattr(self._local, "connection", None)
        if connection is None or connection.is_closed:
            connection = self._pika.BlockingConnection(self._pika.URLParameters(self.url))
            self._local.connection = connection
        channel = connection.channel()
        channel.exchange_declare(exchange=self.exchange, exchange_type="topic", durable=True)
        return channel

    def publish(self, event: dict[str, Any]) -> None:
        channel = self._channel()
        channel.basic_publish(
            exchange=self.exchange,
            routing_key=f"job.{event.get('event_type', 'event')}",
            body=json.dumps(event, ensure_ascii=False).encode("utf-8"),
            properties=self._pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )

    def close(self) -> None:
        connection = getattr(self._local, "connection", None)
        if connection is not None and not connection.is_closed:
            connection.close()


class NullEventBus:
    def publish(self, event: dict[str, Any]) -> None:
        return None

    def close(self) -> None:
        return None


def event_payload(job_id: str, event: dict[str, Any]) -> dict[str, Any]:
    payload = dict(event)
    payload["job_id"] = job_id
    payload["published_at"] = time.time()
    return payload
