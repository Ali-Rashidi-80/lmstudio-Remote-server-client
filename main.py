"""AI Bridge Enterprise Server Module."""

import asyncio
import json
import logging
import os
from typing import Dict, Set

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from starlette.websockets import WebSocketState

from cipher_utils import encrypt_message

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - BRIDGE - %(message)s"
)
logger = logging.getLogger("Bridge")

app = FastAPI(title="AI Bridge (Enterprise V17.4 Ultimate)")
os.makedirs("templates", exist_ok=True)
templates = Jinja2Templates(directory="templates")


class ConnectionManager:
    """Manages WebSocket connections for users and PC nodes."""

    def __init__(self):
        self.pc_client: WebSocket | None = None
        self.pc_hw_mode = "CPU"
        self.pc_lock = asyncio.Lock()
        self.user_clients: Dict[str, WebSocket] = {}
        self.user_locks: Dict[str, asyncio.Lock] = {}
        self.background_tasks: Set[asyncio.Task] = set()
        self.dict_lock = asyncio.Lock()

    def create_safe_task(self, coro):
        """Run tasks securely in the background."""
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    async def connect_pc(self, websocket: WebSocket):
        """Accept and register the PC node connection."""
        await websocket.accept()
        async with self.pc_lock:
            if self.pc_client:
                try:
                    await self.pc_client.close(code=1000)
                except Exception:
                    pass
            self.pc_client = websocket
        logger.info("🟢 PC Node Linked.")

    async def connect_user(self, websocket: WebSocket, client_id: str):
        """Accept and register a new user connection."""
        await websocket.accept()
        async with self.dict_lock:
            if client_id in self.user_clients:
                try:
                    await self.user_clients[client_id].close(code=1000)
                except Exception:
                    pass
            self.user_clients[client_id] = websocket
            self.user_locks[client_id] = asyncio.Lock()

        await self.send_sys_status(
            client_id,
            self.pc_client is not None,
            self.pc_hw_mode
        )
        logger.info("👤 User %s Connected.", client_id)

    async def disconnect_pc(self):
        """Unregister the PC node connection."""
        async with self.pc_lock:
            if self.pc_client is None:
                return
            self.pc_client = None
            self.pc_hw_mode = "CPU"
        logger.warning("🔴 PC Node Offline.")
        self.create_safe_task(self.broadcast_sys_status(False, "CPU"))

    async def delayed_cancel(self, client_id: str):
        """Wait 30s before cancelling to survive page refreshes/network drops."""
        await asyncio.sleep(30.0)
        is_offline = False
        async with self.dict_lock:
            if client_id not in self.user_clients:
                is_offline = True
        
        if is_offline:
            cancel_msg = json.dumps({
                "type": "sys_cancel",
                "content": "user_left"
            })
            enc_msg = encrypt_message(cancel_msg)
            await self.send_to_pc_raw(client_id, enc_msg)

    async def disconnect_user(self, client_id: str):
        """Unregister a user connection securely with grace period."""
        ws = None
        async with self.dict_lock:
            ws = self.user_clients.pop(client_id, None)
            self.user_locks.pop(client_id, None)

        logger.info("👤 User %s Disconnected.", client_id)

        if ws and self.pc_client:
            if self.pc_client.client_state == WebSocketState.CONNECTED:
                # Trigger a delayed cancel to survive micro-drops / F5 refreshes
                self.create_safe_task(self.delayed_cancel(client_id))

    async def broadcast_sys_status(self, is_online: bool, hw_mode: str):
        """Broadcast system status to all connected users."""
        status_str = "online" if is_online else "offline"
        packet = json.dumps({
            "type": "sys_status",
            "content": status_str,
            "hw": hw_mode
        })
        enc = encrypt_message(packet)
        async with self.dict_lock:
            active_users = list(self.user_clients.keys())

        for uid in active_users:
            self.create_safe_task(self.send_to_user_safe(uid, enc))

    async def send_sys_status(
        self, client_id: str, is_online: bool, hw_mode: str
    ):
        """Send current system status to a specific user."""
        status_str = "online" if is_online else "offline"
        packet = json.dumps({
            "type": "sys_status",
            "content": status_str,
            "hw": hw_mode
        })
        await self.send_to_user_safe(client_id, encrypt_message(packet))

    async def send_to_pc_raw(self, client_id: str, encrypted_payload: str):
        """Send raw encrypted payload directly to PC."""
        pc = self.pc_client
        if pc and pc.client_state == WebSocketState.CONNECTED:
            async with self.pc_lock:
                try:
                    await pc.send_json({
                        "client_id": client_id,
                        "payload": encrypted_payload
                    })
                except Exception as e:
                    logger.warning("Failed sending to PC: %s", e)
                    self.create_safe_task(self.disconnect_pc())
        else:
            err = json.dumps({
                "type": "error",
                "content": "سرور پردازشی خاموش است."
            })
            self.create_safe_task(
                self.send_to_user_safe(client_id, encrypt_message(err))
            )

    async def send_to_user_safe(self, client_id: str, encrypted_payload: str):
        """Send payload securely to a specific user by client_id."""
        async with self.dict_lock:
            ws = self.user_clients.get(client_id)
            lock = self.user_locks.get(client_id)

        if ws and lock and ws.client_state == WebSocketState.CONNECTED:
            async with lock:
                try:
                    await ws.send_json({"payload": encrypted_payload})
                except Exception:
                    self.create_safe_task(self.disconnect_user(client_id))


manager = ConnectionManager()


@app.get("/")
async def index(request: Request):
    """Serve the main web UI."""
    env_key = os.getenv("ENCRYPTION_KEY")
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "env_key": env_key}
    )


@app.get("/favicon.ico")
async def favicon():
    """Handle favicon requests cleanly without throwing 404 errors."""
    return Response(status_code=204)


@app.websocket("/ws/pc")
async def pc_ws(websocket: WebSocket):
    """WebSocket endpoint for the PC worker node."""
    await manager.connect_pc(websocket)
    ping_interval = 45.0
    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=ping_interval
                )
                data = json.loads(raw)

                if data.get("type") == "ping":
                    async with manager.pc_lock:
                        if websocket.client_state == WebSocketState.CONNECTED:
                            await websocket.send_json({"type": "pong"})
                    continue

                if data.get("type") == "pong":
                    continue

                if "client_id" in data and "payload" in data:
                    manager.create_safe_task(
                        manager.send_to_user_safe(
                            data["client_id"], data["payload"]
                        )
                    )

                elif data.get("type") == "hw_info":
                    manager.pc_hw_mode = data.get("content", "CPU")
                    manager.create_safe_task(
                        manager.broadcast_sys_status(True, manager.pc_hw_mode)
                    )

            except asyncio.TimeoutError:
                logger.warning("PC Node: Heartbeat timeout, closing.")
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.close(code=1000)
                break
    except WebSocketDisconnect:
        logger.info("PC Node disconnected cleanly.")
    except Exception as e:
        logger.error("PC Connection Dropped: %s", e)
    finally:
        await manager.disconnect_pc()


@app.websocket("/ws/client/{client_id}")
async def user_ws(websocket: WebSocket, client_id: str):
    """WebSocket endpoint for user clients."""
    await manager.connect_user(websocket, client_id)
    try:
        while True:
            raw = await asyncio.wait_for(
                websocket.receive_text(), timeout=600.0
            )
            data = json.loads(raw)
            if "payload" in data:
                manager.create_safe_task(
                    manager.send_to_pc_raw(client_id, data["payload"])
                )
            elif data.get("type") == "ping":
                async with manager.dict_lock:
                    lock = manager.user_locks.get(client_id)
                if lock and websocket.client_state == WebSocketState.CONNECTED:
                    async with lock:
                        await websocket.send_json({"type": "pong"})
    except asyncio.TimeoutError:
        logger.info("User %s timed out.", client_id)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("User %s connection dropped: %s", client_id, e)
    finally:
        await manager.disconnect_user(client_id)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )