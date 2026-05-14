import asyncio
import json
import logging
import ssl
import os
import random
import subprocess
import platform
import ast
import operator
import websockets
import httpx
import traceback
import urllib.request
from typing import Dict, List, Any
from urllib.parse import urlparse, urljoin
from pathlib import Path
from dotenv import load_dotenv

# ==========================================
# گارد امنیتی مطلق ضد پروکسی (Ultimate Proxy Kill-Switch)
# ==========================================
for _env_var in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
    os.environ.pop(_env_var, None)
urllib.request.getproxies = lambda: {}

from cipher_utils import encrypt_message, decrypt_message

# ==========================================
# تنظیمات پایه، لاگینگ و بارگذاری دقیق محیط
# ==========================================
current_dir = Path(__file__).parent
env_path = current_dir / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv() 

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - [%(levelname)s] - PC_CORE - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("Core")

# ==========================================
# تشخیص سخت افزار پایه سیستم
# ==========================================
def detect_hardware() -> str:
    try:
        if platform.system() in ["Windows", "Linux"]:
            res = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0: return "GPU"
        elif platform.system() == "Darwin":
            if platform.machine() in ['arm64', 'aarch64']: return "GPU"
    except Exception as e:
        logger.warning(f"Hardware detection skipped or failed: {e}")
    return "CPU"

HW_MODE = detect_hardware()
CONFIG_FILE = current_dir / "app_config.json"
_cached_cfg = None

# ==========================================
# مدیریت تنظیمات
# ==========================================
def init_config():
    global _cached_cfg
    
    NEW_SYSTEM_PROMPT = (
        "شما یک دستیار هوش مصنوعی فوق‌هوشمند، دقیق و حرفه‌ای هستید. "
        "پاسخ‌های شما باید همواره به زبان فارسی سلیس و روان باشد، مگر اینکه کاربر صراحتاً زبان دیگری را درخواست کند. "
        "در پاسخ‌گویی به سوالات فنی و برنامه‌نویسی، کدهای خود را همواره داخل بلاک‌های استاندارد Markdown همراه با ذکر نام زبان قرار دهید. "
        "در صورت عدم اطمینان از یک پاسخ، با صداقت آن را بیان کنید و از ارائه اطلاعات نادرست (Hallucination) مطلقاً بپرهیزید. "
        "همواره لحنی محترمانه، یاری‌رسان، مستقیم و بدون حاشیه داشته باشید."
    )
    
    if not CONFIG_FILE.exists():
        d_cfg = {
            "lmstudio": {
                "host": "127.0.0.1:1234", 
                "model_key": "default-model", 
                "system_prompt": NEW_SYSTEM_PROMPT,
                "temperature": 0.7
            },
            "features": { 
                "use_streaming": True, 
                "max_history_messages": 12 if HW_MODE == "CPU" else 20, 
                "max_concurrent_requests": 2 if HW_MODE == "CPU" else 4, 
                "llm_timeout_seconds": 900 
            }
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(d_cfg, f, indent=4, ensure_ascii=False)
        _cached_cfg = d_cfg
    else:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f: 
            _cached_cfg = json.load(f)
            
        old_prompt = "شما یک دستیار هوش مصنوعی فوق‌هوشمند هستید. به زبان فارسی پاسخ دهید. کدهای برنامه‌نویسی را درون بلاک‌های استاندارد قرار دهید."
        if _cached_cfg.get("lmstudio", {}).get("system_prompt") == old_prompt:
            logger.info("Auto-upgrading system prompt to the new professional version.")
            _cached_cfg["lmstudio"]["system_prompt"] = NEW_SYSTEM_PROMPT
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(_cached_cfg, f, indent=4, ensure_ascii=False)

init_config()

active_chats: Dict[str, list] = {}
active_tasks: Dict[str, asyncio.Task] = {}
ws_send_lock = asyncio.Lock()
global_http_client: httpx.AsyncClient = None

# ==========================================
# توابع ارتباطی پایه
# ==========================================
async def send_packet(ws: websockets.WebSocketClientProtocol, client_id: str, msg_type: str, content: str, extra_data: dict = None):
    if ws.closed: 
        return
        
    p = {"type": msg_type, "content": content}
    if extra_data: 
        p.update(extra_data)
        
    try:
        async with asyncio.timeout(5.0):
            async with ws_send_lock:
                encrypted_payload = encrypt_message(json.dumps(p))
                await ws.send(json.dumps({"client_id": client_id, "payload": encrypted_payload}))
    except asyncio.TimeoutError:
        logger.error(f"Timeout sending packet to {client_id}")
    except websockets.exceptions.ConnectionClosed:
        pass 
    except Exception as e:
        logger.error(f"Failed to send packet to {client_id}: {e}")

# ==========================================
# سیستم امنیت اجرایی ابزارها (Safe Tools)
# ==========================================
class SafeMathEvaluator:
    operators = {
        ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, 
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg,
        ast.UAdd: operator.pos
    }

    @classmethod
    def evaluate(cls, expr: str) -> str:
        try:
            node = ast.parse(expr, mode='eval').body
            result = cls._eval_node(node)
            return str(result)
        except ZeroDivisionError:
            return "Math Error: Division by zero."
        except ValueError as ve:
            return f"Math Error: {ve}"
        except Exception as e:
            return f"Math Error: Invalid expression syntax. ({e})"

    @classmethod
    def _eval_node(cls, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        elif isinstance(node, ast.BinOp):
            left = cls._eval_node(node.left)
            right = cls._eval_node(node.right)
            
            if type(node.op) == ast.Pow:
                if abs(right) > 100 or abs(left) > 100000:
                    raise ValueError("Base or Exponent too large. Refused to calculate to prevent DoS.")
                    
            return cls.operators[type(node.op)](left, right)
            
        elif isinstance(node, ast.UnaryOp):
            return cls.operators[type(node.op)](cls._eval_node(node.operand))
        else:
            raise TypeError(f"Unsupported mathematical operation or character.")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "انجام محاسبات ریاضی پیچیده و ساده (جمع، تفریق، ضرب، تقسیم، توان). برای اطمینان از صحت محاسبات عددی حتما از این ابزار استفاده کنید.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string", 
                        "description": "عبارت ریاضی معتبر. مثال: (25 * 4) / 2"
                    }
                },
                "required": ["expression"]
            }
        }
    }
]

def execute_tool(name: str, args: dict) -> str:
    if name == "calculate":
        expr = args.get("expression", "")
        if not expr: return "Error: No expression provided."
        return SafeMathEvaluator.evaluate(expr)
    return f"Error: The tool '{name}' does not exist or is unauthorized."

# ==========================================
# هرس ایمن تاریخچه
# ==========================================
def prune_chat_history(chat_history: List[Dict[str, Any]], max_length: int) -> List[Dict[str, Any]]:
    if len(chat_history) <= max_length:
        return chat_history

    system_prompt = chat_history[0] if chat_history and chat_history[0].get("role") == "system" else None
    
    while len(chat_history) > max_length:
        if len(chat_history) <= 2: break 
        
        idx_to_check = 1 if system_prompt else 0
        msg_to_remove = chat_history[idx_to_check]
        
        if msg_to_remove.get("role") == "assistant" and "tool_calls" in msg_to_remove:
            chat_history.pop(idx_to_check) 
            while len(chat_history) > idx_to_check and chat_history[idx_to_check].get("role") == "tool":
                chat_history.pop(idx_to_check)
        elif msg_to_remove.get("role") == "tool":
            chat_history.pop(idx_to_check)
        else:
            chat_history.pop(idx_to_check)

    if system_prompt and (not chat_history or chat_history[0].get("role") != "system"):
        chat_history.insert(0, system_prompt)
        
    return chat_history

# ==========================================
# مانیتورینگ دقیق سخت افزار
# ==========================================
def _is_gpu_active(obj: Any) -> bool:
    if isinstance(obj, dict):
        for k, v in obj.items():
            k_low = str(k).lower()
            if k_low in ['gpu', 'hardware', 'acceleration', 'gpu_offload', 'gpu_layers', 'is_gpu']:
                if str(v).lower() in ['false', '0', 'none', 'cpu', 'null']:
                    continue
                if v: 
                    return True
            if _is_gpu_active(v):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if _is_gpu_active(item):
                return True
    return False

async def hw_monitor(ws: websockets.WebSocketClientProtocol):
    c = _cached_cfg
    # گارد امنیتی: حذف اسلش اضافی برای جلوگیری از Double Slash Bug
    lm_host = str(c["lmstudio"]["host"]).strip().rstrip("/")
    last_status = None
    
    while not ws.closed:
        try:
            current_status = "OFF"
            resp = await global_http_client.get(f"http://{lm_host}/v1/models", timeout=3.0)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    models = data.get("data", []) if isinstance(data, dict) else []
                    if models:
                        current_status = "CPU" 
                        if _is_gpu_active(models):
                            current_status = "GPU"
                except ValueError:
                    pass
            
            if current_status != last_status:
                last_status = current_status
                try:
                    async with asyncio.timeout(2.0):
                        async with ws_send_lock:
                            await ws.send(json.dumps({"type": "hw_info", "content": current_status}))
                except Exception:
                    pass
        except Exception:
            if last_status != "OFF":
                last_status = "OFF"
                try:
                    async with asyncio.timeout(2.0):
                        async with ws_send_lock:
                            await ws.send(json.dumps({"type": "hw_info", "content": "OFF"}))
                except:
                    pass
        
        await asyncio.sleep(5) 

# ==========================================
# وظیفه تپش قلب (Active Heartbeat)
# ==========================================
async def heartbeat_task(ws: websockets.WebSocketClientProtocol):
    while not ws.closed:
        try:
            async with asyncio.timeout(2.0):
                async with ws_send_lock:
                    await ws.send(json.dumps({"type": "ping"}))
        except Exception:
            pass
        await asyncio.sleep(15) 

# ==========================================
# توابع مدیریتی RAM / VRAM
# ==========================================
async def handle_unload_models(ws, client_id):
    c = _cached_cfg
    lm_host = str(c["lmstudio"]["host"]).strip().rstrip("/")
    try:
        resp = await global_http_client.get(f"http://{lm_host}/v1/models", timeout=10.0)
        if resp.status_code == 200:
            try:
                data = resp.json()
                models = data.get("data", []) if isinstance(data, dict) else []
            except ValueError:
                models = []
                
            unloaded_count = 0
            for m in models:
                mid = m["id"]
                try:
                    unload_resp = await global_http_client.post(f"http://{lm_host}/v1/models/unload", json={"model": mid}, timeout=10.0)
                    if unload_resp.status_code in [200, 204]: unloaded_count += 1
                except Exception as e:
                    pass
            
            await send_packet(ws, client_id, "queue", f"✅ عملیات موفق: {unloaded_count} مدل از حافظه VRAM/RAM تخلیه شد.")
        else:
            err_msg = (await resp.aread()).decode('utf-8', errors='replace')[:150]
            await send_packet(ws, client_id, "error", f"خطای سرور: {resp.status_code} - {err_msg}")
    except httpx.ConnectError:
        await send_packet(ws, client_id, "error", "ارتباط با LM Studio برقرار نشد. آیا برنامه روشن است؟")
    except Exception as e:
        await send_packet(ws, client_id, "error", "نرم‌افزار LM Studio پاسخگو نیست.")

async def handle_get_models(ws, client_id):
    c = _cached_cfg
    lm_host = str(c["lmstudio"]["host"]).strip().rstrip("/")
    try:
        resp = await global_http_client.get(f"http://{lm_host}/v1/models", timeout=5.0)
        if resp.status_code == 200:
            try:
                data = resp.json()
                models = data.get("data", []) if isinstance(data, dict) else []
            except ValueError:
                models = []
            await send_packet(ws, client_id, "models_list", "success", {"models": models})
        else:
            await send_packet(ws, client_id, "error", "خطا در دریافت لیست مدل‌ها")
    except Exception as e:
        await send_packet(ws, client_id, "error", "عدم دسترسی به نرم‌افزار LM Studio")

# ==========================================
# هسته هوش مصنوعی (Agentic Loop & Vision)
# ==========================================
async def run_ai(ws, client_id, user_text, requested_model, image_b64=None, use_tools=False):
    c = _cached_cfg
    LM = c["lmstudio"]
    did_start = False
    sem_acquired = False
    
    try:
        try:
            await asyncio.wait_for(llm_semaphore.acquire(), timeout=0.1)
            sem_acquired = True
        except asyncio.TimeoutError:
            await send_packet(ws, client_id, "queue", "⏳ ترافیک بالاست. در صف پردازش قرار گرفتید...")
            await llm_semaphore.acquire()
            sem_acquired = True
    
        await send_packet(ws, client_id, "status", "thinking")
        
        llm_timeout = float(c["features"].get("llm_timeout_seconds", 900))
        lm_host = str(LM["host"]).strip().rstrip("/")
        url = f"http://{lm_host}/v1/chat/completions"
        
        async with asyncio.timeout(llm_timeout):
            m_key = requested_model if requested_model else LM.get("model_key")
            
            if client_id not in active_chats: 
                sys_prompt = LM.get("system_prompt", "")
                if use_tools: sys_prompt += "\nشما یک عامل خودمختار هستید. از ابزارهای (Tools) در دسترس برای حل دقیق مشکلات استفاده کنید."
                active_chats[client_id] = [{"role": "system", "content": sys_prompt}]
            
            if image_b64:
                if not image_b64.startswith("data:image"):
                    image_b64 = f"data:image/jpeg;base64,{image_b64}"
                active_chats[client_id].append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text if user_text else "لطفاً این تصویر را به دقت بررسی کن."},
                        {"type": "image_url", "image_url": {"url": image_b64}}
                    ]
                })
            else:
                active_chats[client_id].append({"role": "user", "content": user_text[:10000]})
            
            max_hist = c["features"]["max_history_messages"]
            active_chats[client_id] = prune_chat_history(active_chats[client_id], max_hist)
            
            MAX_TOOL_ROUNDS = 5 
            round_count = 0
            
            while round_count < MAX_TOOL_ROUNDS:
                round_count += 1
                
                has_history_tools = any("tool_calls" in m or m.get("role") == "tool" for m in active_chats[client_id])
                
                payload = {
                    "model": m_key,
                    "messages": active_chats[client_id],
                    "temperature": LM["temperature"],
                    "stream": c["features"]["use_streaming"]
                }
                
                if use_tools or has_history_tools:
                    payload["tools"] = TOOLS
                
                tool_calls_accumulator = {}
                full_r = ""
                
                if c["features"]["use_streaming"]:
                    async with global_http_client.stream("POST", url, json=payload, timeout=llm_timeout) as response:
                        if response.status_code != 200:
                            err = await response.aread()
                            raise ValueError(f"API Error {response.status_code}: {err.decode('utf-8', errors='replace')[:150]}")
                            
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data = line[6:].strip()
                                if data == "[DONE]": 
                                    break
                                if not data: continue
                                
                                try:
                                    chunk = json.loads(data)
                                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                                    
                                    if "tool_calls" in delta:
                                        for tc in delta["tool_calls"]:
                                            idx = tc["index"]
                                            if idx not in tool_calls_accumulator:
                                                tool_calls_accumulator[idx] = {
                                                    "id": tc.get("id", f"call_{random.randint(100000,999999)}"), 
                                                    "type": "function", 
                                                    "function": {"name": "", "arguments": ""}
                                                }
                                            func = tc.get("function", {})
                                            
                                            f_name = func.get("name")
                                            if f_name: tool_calls_accumulator[idx]["function"]["name"] += str(f_name)
                                                
                                            f_args = func.get("arguments")
                                            if f_args: tool_calls_accumulator[idx]["function"]["arguments"] += str(f_args)
                                    
                                    content = delta.get("content")
                                    if content:
                                        did_start = True
                                        full_r += content
                                        await send_packet(ws, client_id, "chunk", content)
                                except json.JSONDecodeError:
                                    continue
                else:
                    response = await global_http_client.post(url, json=payload, timeout=llm_timeout)
                    if response.status_code != 200: raise ValueError(f"API error: {response.status_code}")
                    
                    data = response.json()
                    msg = data.get("choices", [{}])[0].get("message", {})
                    
                    if "tool_calls" in msg:
                        for i, tc in enumerate(msg["tool_calls"]):
                            tool_calls_accumulator[i] = tc
                    
                    full_r = msg.get("content") or ""
                    if full_r:
                        await send_packet(ws, client_id, "full", full_r)
                
                # --- اجرای ابزارها ---
                if tool_calls_accumulator:
                    assistant_msg = {
                        "role": "assistant",
                        "content": full_r if full_r else "", 
                        "tool_calls": list(tool_calls_accumulator.values())
                    }
                    active_chats[client_id].append(assistant_msg)
                    
                    for idx, tc in tool_calls_accumulator.items():
                        func_name = tc["function"]["name"]
                        arg_str = tc["function"]["arguments"]
                        
                        try:
                            if not arg_str.strip(): args = {}
                            else: args = json.loads(arg_str)
                                
                            if not isinstance(args, dict):
                                raise ValueError("Invalid argument type (expected JSON object).")
                                
                            logger.info(f"Executing tool [{func_name}] with args: {args}")
                            await send_packet(ws, client_id, "tool_event", f"در حال اجرای ابزار: {func_name}")
                            
                            raw_result = str(execute_tool(func_name, args))
                            result_str = raw_result[:1995] + "..." if len(raw_result) > 2000 else raw_result
                            
                        except (json.JSONDecodeError, ValueError) as ve:
                            logger.warning(f"Self-Correcting: Model failed args syntax for tool {func_name}. Exception: {ve}")
                            result_str = "Error: Invalid JSON arguments or Type. Please fix the JSON syntax to a valid dictionary and try again."
                        
                        active_chats[client_id].append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "name": func_name,
                            "content": result_str
                        })
                    
                    await send_packet(ws, client_id, "status", "thinking")
                    continue
                    
                else:
                    if full_r:
                        active_chats[client_id].append({"role": "assistant", "content": full_r})
                    
                    await send_packet(ws, client_id, "done", "")
                    break
            
            if round_count >= MAX_TOOL_ROUNDS:
                logger.warning(f"Client {client_id} hit Max Tool Rounds limit.")
                await send_packet(ws, client_id, "error", "عملیات متوقف شد (تکرار بیش از حد ابزارها).")
                
    except asyncio.CancelledError: 
        logger.info(f"Task for {client_id} gracefully cancelled.")
    except asyncio.TimeoutError:
        logger.error("AI processing timed out.")
        await send_packet(ws, client_id, "error", "تایم‌اوت در پردازش هوش مصنوعی.")
    except Exception as e:
        logger.error(f"Fatal AI Error:\n{traceback.format_exc()}")
        if did_start: 
            try:
                await send_packet(ws, client_id, "chunk", "\n\n[⚠️ پردازش با خطای سرور متوقف شد]")
                await send_packet(ws, client_id, "done", "")
            except: pass
        else: 
            try: await send_packet(ws, client_id, "error", f"خطای پردازش: {str(e)[:80]}")
            except: pass
    finally: 
        if sem_acquired: llm_semaphore.release()
        if active_tasks.get(client_id) == asyncio.current_task(): active_tasks.pop(client_id, None)

# ==========================================
# کارگر اصلی ارتباطات (Websocket PC Worker)
# ==========================================
async def pc_worker():
    global global_http_client
    
    raw_url = os.getenv("BRIDGE_WS_URL", "ws://127.0.0.1:8000").strip().rstrip("/")
    logger.info(f"Raw URL from Environment: {raw_url}")
    
    if raw_url.startswith("http://"):
        raw_url = raw_url.replace("http://", "ws://", 1)
    elif raw_url.startswith("https://"):
        raw_url = raw_url.replace("https://", "wss://", 1)
        
    if raw_url.endswith("/ws/pc"):
        uri = raw_url
    elif raw_url.endswith("/ws"):
        uri = f"{raw_url}/pc"
    else:
        uri = f"{raw_url}/ws/pc"
        
    logger.info(f"Normalized Bridge Endpoint: {uri}")
    
    ssl_ctx = ssl.create_default_context() if uri.startswith("wss://") else None
    if ssl_ctx:
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
    
    reconnect_attempts = 0
    
    limits = httpx.Limits(max_keepalive_connections=20, max_connections=40, keepalive_expiry=30.0)
    http_timeout = httpx.Timeout(float(_cached_cfg["features"].get("llm_timeout_seconds", 900)), connect=10.0)
    
    async with httpx.AsyncClient(limits=limits, timeout=http_timeout, trust_env=False) as client:
        global_http_client = client
        
        while True:
            try:
                async with websockets.connect(
                    uri, 
                    ssl=ssl_ctx, 
                    ping_interval=20, 
                    ping_timeout=40,
                    max_size=20_971_520  
                ) as ws:
                    logger.info("🟢 Linked to Bridge Successfully.")
                    reconnect_attempts = 0
                    
                    monitor_task = asyncio.create_task(hw_monitor(ws))
                    hb_task = asyncio.create_task(heartbeat_task(ws))
                    
                    try:
                        async for raw in ws:
                            msg = json.loads(raw)
                            
                            if msg.get("type") == "ping":
                                try:
                                    async with asyncio.timeout(2.0):
                                        async with ws_send_lock: 
                                            await ws.send(json.dumps({"type": "pong"}))
                                except Exception:
                                    pass
                                continue
                                
                            if msg.get("type") == "pong":
                                continue
                                
                            if msg.get("client_id") and msg.get("payload"):
                                decrypted_raw = decrypt_message(msg["payload"])
                                if "خطای امنیتی" in decrypted_raw:
                                    logger.error(f"Security mismatch from {msg['client_id']}")
                                    continue
                                    
                                dec = json.loads(decrypted_raw)
                                msg_type = dec.get("type")
                                
                                if msg_type == "sys_cancel":
                                    if msg["client_id"] in active_tasks: 
                                        active_tasks[msg["client_id"]].cancel()
                                    active_chats.pop(msg["client_id"], None)
                                    
                                elif msg_type == "get_models":
                                    asyncio.create_task(handle_get_models(ws, msg["client_id"]))
                                    
                                elif msg_type == "unload_models":
                                    asyncio.create_task(handle_unload_models(ws, msg["client_id"]))
                                    
                                elif msg_type == "chat" and (dec.get("text") or dec.get("image")):
                                    if msg["client_id"] in active_tasks: 
                                        active_tasks[msg["client_id"]].cancel()
                                        await asyncio.sleep(0.05) 
                                        
                                    active_tasks[msg["client_id"]] = asyncio.create_task(
                                        run_ai(
                                            ws=ws, 
                                            client_id=msg["client_id"], 
                                            user_text=dec.get("text", ""), 
                                            requested_model=dec.get("model", ""),
                                            image_b64=dec.get("image"), 
                                            use_tools=dec.get("use_tools", False)
                                        )
                                    )
                    finally:
                        monitor_task.cancel()
                        hb_task.cancel()
                        try:
                            await monitor_task
                            await hb_task
                        except asyncio.CancelledError:
                            pass
                                
            except Exception as e:
                logger.error(f"🔴 Connection Dropped: {e}")
                for t in active_tasks.values(): 
                    t.cancel()
                active_tasks.clear()
                
                delay = min(60.0, (2 ** reconnect_attempts) + random.random())
                reconnect_attempts += 1
                logger.info(f"Reconnecting in {delay:.2f} seconds...")
                await asyncio.sleep(delay)

# ==========================================
# نقطه ورود
# ==========================================
if __name__ == "__main__":
    init_config()
    max_reqs = _cached_cfg["features"]["max_concurrent_requests"]
    llm_semaphore = asyncio.Semaphore(max_reqs)
    
    logger.info(f"Starting PC Core | Hardware: {HW_MODE} | Max Concurrency: {max_reqs}")
    try: 
        asyncio.run(pc_worker())
    except KeyboardInterrupt: 
        logger.info("Process interrupted by user. Shutting down gracefully.")
    except Exception as e:
        logger.critical(f"Critical System Failure: {e}")