from __future__ import annotations

import asyncio
import time
import unittest
import tempfile
from pathlib import Path

from hydro_remote_agent.service.websocket_hub import WorkerHub
from hydro_remote_agent.service.websocket_protocol import (
    ProtocolError,
    make_message,
    parse_message,
    sign_worker_payload,
    verify_worker_auth,
)
from hydro_remote_agent.service.store import JobStore
from hydro_remote_agent.service.contracts import JobSubmission


class _Socket:
    def __init__(self) -> None:
        self.messages = []
        self.closed = False

    async def send_json(self, message):
        self.messages.append(message)

    async def close(self, **_):
        self.closed = True


class WebSocketProtocolTest(unittest.TestCase):
    def test_message_round_trip_and_validation(self) -> None:
        message = make_message("heartbeat", worker_id="worker-1")
        self.assertEqual(parse_message(message)["type"], "heartbeat")
        self.assertEqual(parse_message(make_message("cancel_ack"))["type"], "cancel_ack")
        self.assertEqual(parse_message(make_message("cancelled"))["type"], "cancelled")
        with self.assertRaises(ProtocolError):
            parse_message({"protocol_version": 99, "type": "heartbeat"})

    def test_hmac_authentication(self) -> None:
        timestamp = int(time.time())
        message = {
            "worker_id": "worker-1",
            "auth_timestamp": str(timestamp),
            "auth_nonce": "nonce",
            "auth_signature": sign_worker_payload("worker-1", timestamp, "nonce", "secret"),
        }
        self.assertTrue(verify_worker_auth(message, "secret"))
        self.assertFalse(verify_worker_auth(message, "wrong"))

    def test_register_dispatch_and_complete(self) -> None:
        async def scenario() -> None:
            hub = WorkerHub(worker_secret="secret")
            socket = _Socket()
            timestamp = int(time.time())
            register = make_message(
                "register",
                worker_id="worker-1",
                worker_version="test",
                capabilities=["point_semantic_segmentation"],
                gpus=[],
                auth_timestamp=str(timestamp),
                auth_nonce="nonce",
                auth_signature=sign_worker_payload("worker-1", timestamp, "nonce", "secret"),
            )
            session = await hub.register(socket, register)
            task = asyncio.create_task(hub.invoke(
                "point_semantic_segmentation",
                {"point_cloud_path": "tile.txt"},
                task_id="task-1",
                timeout=1,
            ))
            await asyncio.sleep(0)
            self.assertEqual(socket.messages[-1]["type"], "task")
            await hub.receive(session, make_message(
                "task_ack", worker_id="worker-1", task_id="task-1"
            ))
            self.assertEqual((await hub.snapshot())[0]["pending_tasks"], ["task-1"])
            await hub.receive(session, make_message(
                "completed", worker_id="worker-1", task_id="task-1", result={"status": "succeeded"}
            ))
            self.assertEqual((await task)["status"], "succeeded")
            self.assertEqual((await hub.snapshot())[0]["worker_id"], "worker-1")

        asyncio.run(scenario())

    def test_disconnect_fails_active_task(self) -> None:
        async def scenario() -> None:
            hub = WorkerHub()
            socket = _Socket()
            session = await hub.register(socket, make_message(
                "register", worker_id="worker-1", capabilities=["tool"], gpus=[]
            ))
            task = asyncio.create_task(hub.invoke("tool", {}, task_id="task-1", timeout=2))
            await asyncio.sleep(0)
            await hub.unregister("worker-1", socket)
            with self.assertRaises(ConnectionError):
                await task

        asyncio.run(scenario())

    def test_worker_progress_updates_step(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as temp_dir:
                store = JobStore(Path(temp_dir) / "jobs.sqlite")
                job = store.create_job(JobSubmission("request:ws-step", "query", {}, planned_request={}))
                hub = WorkerHub(store=store)
                socket = _Socket()
                session = await hub.register(socket, make_message(
                    "register", worker_id="worker-1", capabilities=["tool"], gpus=[]
                ))
                task = asyncio.create_task(hub.invoke(
                    "tool", {"point_cloud_path": "tile.txt"},
                    task_id="task-1", job_id=job.job_id, timeout=2,
                ))
                for _ in range(100):
                    if socket.messages and socket.messages[-1]["type"] == "task":
                        break
                    await asyncio.sleep(0)
                self.assertEqual(socket.messages[-1]["type"], "task")
                await hub.receive(session, make_message(
                    "progress", worker_id="worker-1", task_id="task-1", progress=0.4, phase="infer"
                ))
                self.assertEqual(store.step("task-1").status, "running")
                await hub.receive(session, make_message(
                    "completed", worker_id="worker-1", task_id="task-1", result={"status": "succeeded"}
                ))
                await task
                self.assertEqual(store.step("task-1").status, "succeeded")
                self.assertEqual(store.step("task-1").arguments, {"point_cloud_path": "tile.txt"})

        asyncio.run(scenario())

    def test_worker_disconnect_marks_steps_lost(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as temp_dir:
                store = JobStore(Path(temp_dir) / "jobs.sqlite")
                job = store.create_job(JobSubmission("request:disconnect", "query", {}, planned_request={}))
                store.upsert_step("task-1", job.job_id, "tool", status="running", worker_id="worker-1")
                hub = WorkerHub(store=store)
                socket = _Socket()
                await hub.register(socket, make_message("register", worker_id="worker-1", capabilities=["tool"], gpus=[]))
                await hub.unregister("worker-1", socket)
                self.assertEqual(store.step("task-1").status, "lost")

        asyncio.run(scenario())

    def test_reconnect_recovers_lost_step(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as temp_dir:
                store = JobStore(Path(temp_dir) / "jobs.sqlite")
                job = store.create_job(JobSubmission("request:recover-ws", "query", {}))
                store.upsert_step("task-1", job.job_id, "tool", status="lost", attempt=2, arguments={"x": 1})
                hub = WorkerHub(store=store)
                socket = _Socket()
                await hub.register(socket, make_message("register", worker_id="worker-1", capabilities=["tool"], gpus=[]))
                self.assertEqual(socket.messages[-1]["type"], "task")
                self.assertEqual(socket.messages[-1]["attempt"], 3)
                self.assertEqual(store.step("task-1").status, "dispatched")

        asyncio.run(scenario())

    def test_reconnect_does_not_recover_step_for_terminal_job(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as temp_dir:
                store = JobStore(Path(temp_dir) / "jobs.sqlite")
                job = store.create_job(JobSubmission(
                    "request:terminal-recover-ws", "query", {}, planned_request={"schema_version": "1.0"}
                ))
                store.transition(job.job_id, "queued_execution", "executing")
                store.upsert_step(
                    "task-1", job.job_id, "tool", status="lost", attempt=2, arguments={"x": 1}
                )
                store.transition(job.job_id, "executing", "failed", error={"code": "failed"})
                hub = WorkerHub(store=store)
                socket = _Socket()
                await hub.register(socket, make_message(
                    "register", worker_id="worker-1", capabilities=["tool"], gpus=[]
                ))
                self.assertEqual(socket.messages[-1]["type"], "registered")
                self.assertEqual(store.step("task-1").status, "lost")

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
