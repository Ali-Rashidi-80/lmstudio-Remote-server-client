import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import Response
from starlette.websockets import WebSocketState
from fastapi.templating import Jinja2Templates
import logging
import json
import os
import asyncio
from typing import Dict, Set
from dotenv import load_dotenv
from cipher_utils import encrypt_message

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - BRIDGE - %(message)s")
logger = logging.getLogger("Bridge")

app = FastAPI(title="AI Bridge (Enterprise V17)")
os.makedirs("templates", exist_ok=True)
templates = Jinja2Templates(directory="templates")

class ConnectionManager:
    def __init__(self):
        self.pc_client: WebSocket | None = None
        self.pc_hw_mode = "CPU"
        self.pc_lock = asyncio.Lock()
        self.user_clients: Dict[str, WebSocket] = {}
        self.user_locks: Dict[str, asyncio.Lock] = {}
        self.background_tasks: Set[asyncio.Task] = set()
        self.dict_lock = asyncio.Lock()

    def create_safe_task(self, coro):
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    async def connect_pc(self, websocket: WebSocket):
        await websocket.accept()
        if self.pc_client:
            try: await self.pc_client.close(code=1000)
            except: pass
        self.pc_client = websocket
        logger.info("🟢 PC Node Linked.")

    async def connect_user(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        async with self.dict_lock:
            if client_id in self.user_clients:
                try: await self.user_clients[client_id].close(code=1000)
                except: pass
            self.user_clients[client_id] = websocket
            self.user_locks[client_id] = asyncio.Lock()
        
        await self.send_sys_status(client_id, self.pc_client is not None, self.pc_hw_mode)
        logger.info(f"👤 User {client_id} Connected.")

    async def disconnect_pc(self):
        if self.pc_client is None: return 
        self.pc_client = None
        self.pc_hw_mode = "CPU"
        logger.warning("🔴 PC Node Offline.")
        self.create_safe_task(self.broadcast_sys_status(False, "CPU"))

    async def disconnect_user(self, client_id: str):
        ws = None
        async with self.dict_lock:
            ws = self.user_clients.pop(client_id, None)
            self.user_locks.pop(client_id, None)
            
        logger.info(f"👤 User {client_id} Disconnected.")
        if ws and self.pc_client and self.pc_client.client_state == WebSocketState.CONNECTED:
            cancel_msg = json.dumps({"type": "sys_cancel", "content": "user_left"})
            self.create_safe_task(self.send_to_pc_raw(client_id, encrypt_message(cancel_msg)))

    async def broadcast_sys_status(self, is_online: bool, hw_mode: str):
        packet = json.dumps({"type": "sys_status", "content": "online" if is_online else "offline", "hw": hw_mode})
        enc = encrypt_message(packet)
        async with self.dict_lock:
            active_users = list(self.user_clients.keys())
            
        for uid in active_users:
            self.create_safe_task(self.send_to_user_safe(uid, enc))

    async def send_sys_status(self, client_id: str, is_online: bool, hw_mode: str):
        packet = json.dumps({"type": "sys_status", "content": "online" if is_online else "offline", "hw": hw_mode})
        await self.send_to_user_safe(client_id, encrypt_message(packet))

    async def send_to_pc_raw(self, client_id: str, encrypted_payload: str):
        if self.pc_client and self.pc_client.client_state == WebSocketState.CONNECTED:
            async with self.pc_lock:
                try:
                    await self.pc_client.send_json({"client_id": client_id, "payload": encrypted_payload})
                except Exception as e:
                    logger.error(f"Failed sending to PC: {e}")
                    self.create_safe_task(self.disconnect_pc())
        else:
            err = json.dumps({"type": "error", "content": "سرور پردازشی خاموش است."})
            self.create_safe_task(self.send_to_user_safe(client_id, encrypt_message(err)))

    async def send_to_user_safe(self, client_id: str, encrypted_payload: str):
        async with self.dict_lock:
            ws = self.user_clients.get(client_id)
            lock = self.user_locks.get(client_id)
            
        if ws and lock and ws.client_state == WebSocketState.CONNECTED:
            async with lock:
                try:
                    await ws.send_json({"payload": encrypted_payload})
                except:
                    self.create_safe_task(self.disconnect_user(client_id))

manager = ConnectionManager()

@app.get("/")
async def index(request: Request):
    env_key = os.getenv("ENCRYPTION_KEY")
    return templates.TemplateResponse("index.html", {"request": request, "env_key": env_key})

@app.get("/favicon.ico")
async def favicon():
    # رفع باگ اتمیک: بازگرداندن شیء Response معتبر برای FastAPI
    return Response(status_code=404)

@app.websocket("/ws/pc")
async def pc_ws(websocket: WebSocket):
    await manager.connect_pc(websocket)
    loop = asyncio.get_running_loop()
    last_ping = loop.time()
    ping_interval = 30.0  
    pong_timeout = 10.0   
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=ping_interval)
                data = json.loads(raw)
                
                if data.get("type") == "ping":
                    async with manager.pc_lock:
                        await websocket.send_json({"type": "pong"})
                    continue
                    
                if data.get("type") == "pong":
                    last_ping = loop.time()
                    continue
                    
                elif "client_id" in data and "payload" in data:
                    manager.create_safe_task(manager.send_to_user_safe(data["client_id"], data["payload"]))
                    
                elif data.get("type") == "hw_info":
                    manager.pc_hw_mode = data.get("content", "CPU")
                    manager.create_safe_task(manager.broadcast_sys_status(True, manager.pc_hw_mode))
                    
            except asyncio.TimeoutError:
                if websocket.client_state == WebSocketState.CONNECTED:
                    async with manager.pc_lock:
                        await websocket.send_json({"type": "ping"})
                    try:
                        pong_data = await asyncio.wait_for(websocket.receive_text(), timeout=pong_timeout)
                        pong_json = json.loads(pong_data)
                        if pong_json.get("type") == "pong":
                            last_ping = loop.time()
                        else:
                            raise ValueError("Unexpected response")
                    except (asyncio.TimeoutError, ValueError):
                        logger.warning("Pong not received, closing connection")
                        await websocket.close(code=1000)
                        break
    except WebSocketDisconnect:
        logger.warning("PC Node disconnected normally.")
        await manager.disconnect_pc()
    except Exception as e:
        logger.error(f"PC Connection Dropped: {e}")
        await manager.disconnect_pc()

@app.websocket("/ws/client/{client_id}")
async def user_ws(websocket: WebSocket, client_id: str):
    await manager.connect_user(websocket, client_id)
    try:
        while True:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=600.0)
            data = json.loads(raw)
            if "payload" in data:
                manager.create_safe_task(manager.send_to_pc_raw(client_id, data["payload"]))
            elif data.get("type") == "ping":
                async with manager.dict_lock:
                    lock = manager.user_locks.get(client_id)
                if lock and websocket.client_state == WebSocketState.CONNECTED:
                    async with lock: 
                        await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        logger.info(f"User {client_id} disconnected normally.")
        await manager.disconnect_user(client_id)
    except Exception as e:
        logger.warning(f"User {client_id} disconnected with error: {e}")
        await manager.disconnect_user(client_id)

if __name__ == "__main__":
    uvicorn.run("main:app", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", 8000)), log_level="info")