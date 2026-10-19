from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any, Mapping


PROTOCOL_VERSION = 1
MESSAGE_TYPES = {
    "register",
    "registered",
    "task",
    "task_ack",
    "progress",
    "heartbeat",
    "completed",
    "failed",
    "cancel",
    "cancel_ack",
    "cancelled",
    "ack",
}


class ProtocolError(ValueError):
    pass


def make_message(message_type: str, **payload: Any) -> dict[str, Any]:
    if message_type not in MESSAGE_TYPES:
        raise ProtocolError(f"Unsupported message type: {message_type}")
    message = {
        "protocol_version": PROTOCOL_VERSION,
        "type": message_type,
        "message_id": f"msg_{uuid.uuid4().hex}",
        "timestamp": time.time(),
    }
    message.update(payload)
    return message


def parse_message(raw: str | bytes | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(raw, (str, bytes)):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProtocolError("Message must be valid JSON") from exc
    else:
        payload = dict(raw)
    if not isinstance(payload, dict):
        raise ProtocolError("Message must be a JSON object")
    if payload.get("protocol_version") != PROTOCOL_VERSION:
        raise ProtocolError("Unsupported protocol version")
    message_type = payload.get("type")
    if message_type not in MESSAGE_TYPES:
        raise ProtocolError("Unknown message type")
    for field in ("message_id", "timestamp"):
        if field not in payload:
            raise ProtocolError(f"Missing message field: {field}")
    return payload


def sign_worker_payload(worker_id: str, timestamp: int, nonce: str, secret: str) -> str:
    value = f"{worker_id}:{timestamp}:{nonce}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), value, hashlib.sha256).hexdigest()


def verify_worker_auth(message: Mapping[str, Any], secret: str, max_age: float = 120.0) -> bool:
    worker_id = message.get("worker_id")
    timestamp = message.get("auth_timestamp")
    nonce = message.get("auth_nonce")
    signature = message.get("auth_signature")
    if not all(isinstance(value, str) for value in (worker_id, nonce, signature)):
        return False
    try:
        timestamp_value = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(time.time() - timestamp_value) > max_age:
        return False
    expected = sign_worker_payload(worker_id, timestamp_value, nonce, secret)
    return hmac.compare_digest(signature, expected)
