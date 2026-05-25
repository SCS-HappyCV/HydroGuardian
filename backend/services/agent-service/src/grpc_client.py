from __future__ import annotations

from contextlib import asynccontextmanager

import grpc


@asynccontextmanager
async def open_channel(target: str):
    channel = grpc.aio.insecure_channel(target)
    try:
        yield channel
    finally:
        await channel.close()
