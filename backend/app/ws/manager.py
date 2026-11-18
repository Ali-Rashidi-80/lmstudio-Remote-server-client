"""WebSocket connection manager for users and PC worker."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.db.redis import get_worker_state, set_worker_state

logger = logging.getLogger("ws")


class ConnectionManager:
    def __init__(self) -> None:
        self.pc_client: WebSocket | None = None
        self.pc_hw_mode = "CPU"
        self.available_models: list[dict[str, Any]] = []
        self.pc_lock = asyncio.Lock()
        self.user_clients: dict[str, WebSocket] = {}
        self.user_locks: dict[str, asyncio.Lock] = {}
        self.background_tasks: set[asyncio.Task] = set()
        self.dict_lock = asyncio.Lock()
        self._embed_waiters: dict[str, asyncio.Future] = {}
        # Last chat_id per user for persisting assistant finals from Worker
        self.active_chat_ids: dict[str, str] = {}
        # Accumulate streaming chunks until type=done
        self.stream_buffers: dict[str, str] = {}
        # RAG sources stashed until assistant message is persisted
        self.pending_sources: dict[str, list] = {}

    def create_safe_task(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    async def connect_pc(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self.pc_lock:
            if self.pc_client:
                try:
                    await self.pc_client.close(code=1000)
                except Exception as exc:
                    logger.debug("Closing prior PC websocket failed: %s", exc)
            self.pc_client = websocket
        await set_worker_state(True, self.pc_hw_mode, self.available_models)
        await self.broadcast_sys_status(True, self.pc_hw_mode)
        await self.route_to_pc({"v": 1, "type": "get_models", "client_id": "system", "payload": {}})
        logger.info("PC worker linked")

    async def connect_user(self, websocket: WebSocket, user_id: str) -> None:
        await websocket.accept()
        async with self.dict_lock:
            old = self.user_clients.get(user_id)
            if old:
                try:
                    await old.close(code=1000)
                except Exception as exc:
                    logger.debug("Closing prior user websocket failed: %s", exc)
            self.user_clients[user_id] = websocket
            self.user_locks[user_id] = asyncio.Lock()
        await self.send_sys_status(user_id, self.pc_client is not None, self.pc_hw_mode)
        if self.available_models:
            await self.route_to_user(
                user_id,
                {"v": 1, "type": "models_list", "payload": {"models": self.available_models}},
            )

    async def disconnect_pc(self) -> None:
        async with self.pc_lock:
            self.pc_client = None
            self.pc_hw_mode = "CPU"
            self.available_models = []
        for req_id in list(self._embed_waiters):
            fut = self._embed_waiters.pop(req_id, None)
            if fut and not fut.done():
                fut.set_exception(RuntimeError("PC Worker disconnected"))
        await set_worker_state(False, "CPU", [])
        self.create_safe_task(self.broadcast_sys_status(False, "CPU"))

    async def update_hw(self, hw: str) -> None:
        self.pc_hw_mode = hw or "CPU"
        await set_worker_state(True, self.pc_hw_mode, self.available_models)
        await self.broadcast_sys_status(True, self.pc_hw_mode)

    async def update_models(self, models: list[dict[str, Any]]) -> None:
        self.available_models = models
        await set_worker_state(True, self.pc_hw_mode, self.available_models)
        await self.broadcast_to_users(
            {"v": 1, "type": "models_list", "payload": {"models": models}}
        )

    async def touch_worker(self) -> None:
        await set_worker_state(True, self.pc_hw_mode, self.available_models)

    async def delayed_cancel(self, user_id: str) -> None:
        await asyncio.sleep(30.0)
        async with self.dict_lock:
            offline = user_id not in self.user_clients
        if offline:
            await self.route_to_pc(
                {
                    "v": 1,
                    "type": "sys_cancel",
                    "client_id": user_id,
                    "payload": {},
                }
            )

    async def disconnect_user(self, user_id: str) -> None:
        async with self.dict_lock:
            self.user_clients.pop(user_id, None)
            self.user_locks.pop(user_id, None)
        self.create_safe_task(self.delayed_cancel(user_id))

    async def send_json(self, websocket: WebSocket, data: dict) -> bool:
        if websocket.client_state != WebSocketState.CONNECTED:
            return False
        try:
            await websocket.send_json(data)
            return True
        except Exception as exc:
            logger.debug("WebSocket send_json failed: %s", exc)
            return False

    async def send_sys_status(self, user_id: str, online: bool, hw: str) -> None:
        async with self.dict_lock:
            ws = self.user_clients.get(user_id)
            lock = self.user_locks.get(user_id)
        if not ws:
            return
        msg = {"v": 1, "type": "sys_status", "payload": {"online": online, "hw": hw}}
        if lock:
            async with lock:
                await self.send_json(ws, msg)
        else:
            await self.send_json(ws, msg)

    async def broadcast_sys_status(self, online: bool, hw: str) -> None:
        async with self.dict_lock:
            user_ids = list(self.user_clients.keys())
        for uid in user_ids:
            await self.send_sys_status(uid, online, hw)

    async def broadcast_to_users(self, message: dict) -> None:
        async with self.dict_lock:
            user_ids = list(self.user_clients.keys())
        for uid in user_ids:
            await self.route_to_user(uid, message)

    async def route_to_pc(self, message: dict) -> bool:
        async with self.pc_lock:
            pc = self.pc_client
        if not pc or pc.client_state != WebSocketState.CONNECTED:
            return False
        try:
            await pc.send_json(message)
            return True
        except Exception as exc:
            logger.warning("Failed sending to PC worker: %s", exc)
            return False

    async def route_to_user(self, user_id: str, message: dict) -> bool:
        async with self.dict_lock:
            ws = self.user_clients.get(user_id)
            lock = self.user_locks.get(user_id)
        if not ws:
            return False
        if lock:
            async with lock:
                return await self.send_json(ws, message)
        return await self.send_json(ws, message)

    def status(self) -> dict[str, Any]:
        return {
            "worker_online": self.pc_client is not None
            and self.pc_client.client_state == WebSocketState.CONNECTED,
            "hw": self.pc_hw_mode,
            "connected_users": len(self.user_clients),
        }

    async def merged_status(self) -> dict[str, Any]:
        """Combine local WS presence with shared Redis worker heartbeat."""
        local = self.status()
        if local["worker_online"]:
            return {**local, "models": self.available_models}
        shared = await get_worker_state()
        if shared and shared.get("worker_online"):
            return {
                "worker_online": True,
                "hw": shared.get("hw", "CPU"),
                "connected_users": local["connected_users"],
                "models": shared.get("models", []),
            }
        return {**local, "models": self.available_models}

    def resolve_embeddings(self, request_id: str, payload: dict) -> None:
        fut = self._embed_waiters.pop(request_id, None)
        if not fut or fut.done():
            return
        err = payload.get("error")
        if err:
            fut.set_exception(RuntimeError(str(err)))
        else:
            fut.set_result(payload)

    async def request_embeddings(
        self, texts: list[str], model: str, timeout: float = 120.0
    ) -> dict:
        request_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._embed_waiters[request_id] = fut
        ok = await self.route_to_pc(
            {
                "v": 1,
                "type": "embeddings",
                "client_id": "system",
                "payload": {"input": texts, "model": model, "request_id": request_id},
            }
        )
        if not ok:
            self._embed_waiters.pop(request_id, None)
            raise RuntimeError("PC Worker offline for embeddings")
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._embed_waiters.pop(request_id, None)


manager = ConnectionManager()
