import asyncio
import json
import logging
import ssl
import os
import random
import subprocess
import platform
import websockets
import httpx
import traceback
from typing import Dict
from urllib.parse import urlparse, urljoin
from dotenv import load_dotenv
#import lmstudio as lms
from cipher_utils import encrypt_message, decrypt_message


load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - PC_CORE - %(message)s")
logger = logging.getLogger("Core")

def detect_hardware():
    has_gpu = False
    try:
        if platform.system() in ["Windows", "Linux"]:
            res = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0: has_gpu = True
        elif platform.system() == "Darwin":
            if platform.machine() in ['arm64', 'aarch64']: has_gpu = True
    except Exception as e:
        logger.warning(f"Hardware detection failed: {e}")
    return "GPU" if has_gpu else "CPU"

HW_MODE = detect_hardware()
logger.info(f"Hardware detection completed: {HW_MODE}")

CONFIG_FILE = "app_config.json"
_cached_cfg = None


def init_config():
    global _cached_cfg
    if not os.path.exists(CONFIG_FILE):
        d_cfg = {
            "lmstudio": {
                "host": "127.0.0.1:1234", "model_key": "gemma-4-e4b-it-ud",
                "system_prompt": "شما دستیار هوش مصنوعی هستید. پاسخ‌های دقیق به زبان فارسی ارائه دهید و کدهای برنامه‌نویسی را در بلاک قرار دهید.",
                "temperature": 0.7,
                "force_context_length": false

            },
            "features": { 
                "use_streaming": True, 
                "max_history_messages": 8 if HW_MODE == "CPU" else 15, 
                "max_concurrent_requests": 2 if HW_MODE == "CPU" else 4, 
                "llm_timeout_seconds": 900 
            }
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(d_cfg, f, indent=4, ensure_ascii=False)
        _cached_cfg = d_cfg
        logger.info("Default config created.")
    else:
        logger.info("Config file exists.")

def load_config():
    global _cached_cfg
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f: _cached_cfg = json.load(f)
        logger.info("Config loaded from file.")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
    return _cached_cfg

init_config()
logger.info("Configuration loaded successfully.")
active_chats: Dict[str, list] = {}
active_tasks: Dict[str, asyncio.Task] = {}
ws_send_lock = asyncio.Lock()
#lms_client = None

def get_pruned_chat(client_id: str, new_text: str, cfg: dict, actual_context_len: int) -> lms.Chat:
    if client_id not in active_chats: active_chats[client_id] = []
    limit_chars = int((actual_context_len * 4) * 0.75) 
    if limit_chars < 2000: limit_chars = 4000
    
    safe_text = new_text[:6000]
    active_chats[client_id].append({"role": "user", "content": safe_text})
    
    while sum(len(m["content"]) for m in active_chats[client_id]) > limit_chars and len(active_chats[client_id]) > 1:
        active_chats[client_id].pop(0)
        if active_chats[client_id] and active_chats[client_id][0].get("role") == "assistant":
            active_chats[client_id].pop(0)
            
    hist = [{"role": "system", "content": cfg["lmstudio"].get("system_prompt", "")}] + active_chats[client_id]
    logger.debug(f"Chat history for {client_id} pruned to {len(hist)} messages.")
    return lms.Chat.from_history({"messages": hist})

async def send_packet(ws, client_id, msg_type, content):
    p = {"type": msg_type, "content": content}
    try:
        async with asyncio.timeout(5.0):
            async with ws_send_lock:
                await ws.send(json.dumps({"client_id": client_id, "payload": encrypt_message(json.dumps(p))}))
        logger.debug(f"Packet sent to {client_id}: {msg_type}")
    except Exception as e:
        logger.error(f"Failed to send packet to Bridge: {e}")
        raise 

async def run_ai(ws, client_id, user_text):
    c = load_config()
    LM = c["lmstudio"]
    did_start = False
    sem_acquired = False
    
    logger.info(f"Starting AI processing for client {client_id} with text: {user_text[:50]}...")
    
    try:
        try:
            await asyncio.wait_for(llm_semaphore.acquire(), timeout=0.1)
            sem_acquired = True
        except asyncio.TimeoutError:
            await send_packet(ws, client_id, "queue", "⏳ ترافیک بالاست. در صف پردازش قرار گرفتید...")
            await llm_semaphore.acquire()
            sem_acquired = True
    
        await send_packet(ws, client_id, "status", "thinking")
        async with asyncio.timeout(c["features"]["llm_timeout_seconds"]):
            
            logger.info(f"Checking LM Studio connection at {LM['host']}...")
            try:
                check_url = f"http://{LM['host']}/v1/models"
                async with httpx.AsyncClient() as http_client:
                    resp = await http_client.get(check_url, timeout=3.0)
                    if resp.status_code != 200:
                        raise ValueError("LM Studio returned non-200 status")
                    models = resp.json().get("data", [])
                    if not models:
                        raise ValueError("No models available")
                logger.info(f"LM Studio is online at {LM['host']}.")
            except Exception as e:
                logger.error(f"LM Studio is DOWN at {LM['host']}: {e}")
                await send_packet(ws, client_id, "error", "نرم‌افزار LM Studio خاموش است یا پورت اشتباه است.")
                return

            m_key = LM.get("model_key") or models[0]["id"] if models else "default"
            logger.info(f"Using model: {m_key}")
            
            # ساخت تاریخچه چت
            active_chats[client_id] = active_chats.get(client_id, [])
            limit_chars = 6000  # ساده‌سازی
            safe_text = user_text[:6000]
            active_chats[client_id].append({"role": "user", "content": safe_text})
            while sum(len(m["content"]) for m in active_chats[client_id]) > limit_chars and len(active_chats[client_id]) > 1:
                active_chats[client_id].pop(0)
            messages = [{"role": "system", "content": LM.get("system_prompt", "")}] + active_chats[client_id]
            
            url = f"http://{LM['host']}/v1/chat/completions"
            payload = {
                "model": m_key,
                "messages": messages,
                "temperature": LM["temperature"],
                "stream": c["features"]["use_streaming"]
            }
            
            async with httpx.AsyncClient() as client:
                if c["features"]["use_streaming"]:
                    async with client.stream("POST", url, json=payload, timeout=60.0) as response:
                        if response.status_code != 200:
                            raise ValueError(f"API error: {response.status_code}")
                        full_r = ""
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data = line[6:]
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                    if content:
                                        did_start = True
                                        full_r += content
                                        await send_packet(ws, client_id, "chunk", content)
                                except:
                                    pass
                        active_chats[client_id].append({"role": "assistant", "content": full_r})
                        await send_packet(ws, client_id, "done", "")
                        logger.info(f"Streaming completed for {client_id}.")
                else:
                    response = await client.post(url, json=payload, timeout=60.0)
                    if response.status_code != 200:
                        raise ValueError(f"API error: {response.status_code}")
                    data = response.json()
                    resp = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    active_chats[client_id].append({"role": "assistant", "content": resp})
                    await send_packet(ws, client_id, "full", resp)
                    logger.info(f"Full response sent for {client_id}.")
                
    except asyncio.CancelledError: 
        logger.info(f"Task for {client_id} gracefully cancelled.")
    except asyncio.TimeoutError:
        logger.error("AI processing timed out.")
        await send_packet(ws, client_id, "error", "تایم‌اوت در پردازش هوش مصنوعی.")
    except Exception as e:
        logger.error(f"Fatal error in AI processing:\n{traceback.format_exc()}")
        if did_start: 
            try:
                await send_packet(ws, client_id, "chunk", "\n\n[⚠️ پردازش متوقف شد]")
                await send_packet(ws, client_id, "done", "")
            except: pass
        else: 
            try: await send_packet(ws, client_id, "error", f"خطای سرور: {str(e)}")
            except: pass
    finally: 
        if sem_acquired:
            llm_semaphore.release()
        
        if active_tasks.get(client_id) == asyncio.current_task():
            active_tasks.pop(client_id, None)

async def pc_worker():
    # خواندن آدرس از تنظیمات
    base_url = os.getenv("BRIDGE_WS_URL", "wss://lmstudio.chbk.dev")
    
    # تصحیح هوشمند پروتکل و آدرس (تبدیل HTTP به WS و HTTPS به WSS)
    if base_url.startswith("https://"):
        base_url = "wss://" + base_url[8:]
    elif base_url.startswith("http://"):
        base_url = "ws://" + base_url[7:]
    
    # پردازش URL برای افزودن پورت و مدیریت مسیر
    parsed = urlparse(base_url)
    if not parsed.port:
        if parsed.scheme == "wss":
            port = 443
        else:
            port = 80
        netloc = f"{parsed.hostname}:{port}"
        base_url = f"{parsed.scheme}://{netloc}{parsed.path}"
    
    # ساخت URI نهایی با استفاده از urljoin برای جلوگیری از مسیر تکراری
    uri = urljoin(base_url, "/ws/pc")
    
    logger.info(f"Attempting to connect to Bridge Server at: {uri}")
    
    # تنظیمات SSL برای دور زدن خطاهای Cloudflare و گواهینامه‌ها
    ssl_context = None
    if uri.startswith("wss://"):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
    
    reconnect_attempts = 0
    heartbeat_task = None
    
    async def send_heartbeat(ws):
        while True:
            try:
                async with ws_send_lock:
                    await ws.send(json.dumps({"type": "ping"}))
                await asyncio.sleep(15)  # Heartbeat every 15 seconds
            except Exception:
                break
    
    while True:
        try:
            connect_kwargs = {"ping_interval": 20, "ping_timeout": 40, "close_timeout": 10}
            if ssl_context:
                connect_kwargs["ssl"] = ssl_context
                
            async with websockets.connect(uri, **connect_kwargs) as ws:
                logger.info("🟢 Linked to Bridge Successfully.")
                reconnect_attempts = 0
                await ws.send(json.dumps({"type": "hw_info", "content": HW_MODE}))
                
                # Start heartbeat
                if heartbeat_task:
                    heartbeat_task.cancel()
                heartbeat_task = asyncio.create_task(send_heartbeat(ws))
                
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("type") == "ping":
                        async with ws_send_lock: 
                            await ws.send(json.dumps({"type": "pong"}))
                        continue
                        
                    if msg.get("client_id") and msg.get("payload"):
                        decrypted_raw = decrypt_message(msg["payload"])
                        if "خطای امنیتی" in decrypted_raw:
                            logger.error("Security Key Mismatch! Payload decryption failed.")
                            continue
                            
                        dec = json.loads(decrypted_raw)
                        if dec.get("type") == "sys_cancel":
                            if msg["client_id"] in active_tasks: 
                                active_tasks[msg["client_id"]].cancel()
                            active_chats.pop(msg["client_id"], None)
                        elif dec.get("text"):
                            if msg["client_id"] in active_tasks: 
                                active_tasks[msg["client_id"]].cancel()
                                await asyncio.sleep(0.05)
                            active_tasks[msg["client_id"]] = asyncio.create_task(run_ai(ws, msg["client_id"], dec["text"]))
                            
        except Exception as e:
            logger.error(f"🔴 Connection to Bridge dropped or failed: {e}")
            if heartbeat_task:
                heartbeat_task.cancel()
                heartbeat_task = None
            if active_tasks:
                for t in active_tasks.values(): 
                    t.cancel()
                active_tasks.clear()
            delay = min(30.0, (2 ** reconnect_attempts) + random.random())
            reconnect_attempts += 1
            await asyncio.sleep(delay)

if __name__ == "__main__":
    llm_semaphore = asyncio.Semaphore(load_config()["features"]["max_concurrent_requests"])
    logger.info(f"Detected hardware mode: {HW_MODE}")
    try: 
        logger.info("Starting PC Node Core...")
        asyncio.run(pc_worker())
    except KeyboardInterrupt:
        logger.info("Shutting down safely.")
    except Exception as e:
        logger.critical(f"Process crashed: {e}")
        



