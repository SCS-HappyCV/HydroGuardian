from __future__ import annotations

from contextlib import asynccontextmanager

import grpc


@asynccontextmanager
async def open_channel(target: str, *, max_message_bytes: int | None = None):
    options = []
    if max_message_bytes is not None and max_message_bytes > 0:
        options = [
            ("grpc.max_send_message_length", max_message_bytes),
            ("grpc.max_receive_message_length", max_message_bytes),
        ]
    channel = grpc.aio.insecure_channel(target, options=options)
    try:
        yield channel
    finally:
        await channel.close()
