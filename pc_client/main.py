"""Main PC Worker process for AI Workspace Enterprise."""

import ast
import asyncio
import json
import logging
import operator
import os
import platform
import random
import ssl
import subprocess
import traceback
import urllib.request
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import httpx
import websockets
from dotenv import load_dotenv

try:
    from pc_client.cipher_utils import decrypt_message
except ImportError:
    from cipher_utils import decrypt_message

# ==========================================
# گارد امنیتی مطلق ضد پروکسی
# ==========================================
_PROXY_VARS = [
    "http_proxy", "https_proxy", "all_proxy",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"
]
for _env_var in _PROXY_VARS:
    os.environ.pop(_env_var, None)


def _empty_proxies() -> dict:
    """Return an empty dictionary to bypass system proxies safely."""
    return {}


urllib.request.getproxies = _empty_proxies

# ==========================================
# تنظیمات پایه و لاگینگ
# ==========================================
current_dir = Path(__file__).parent
env_path = current_dir / ".env"
_should_override = os.getenv("PYTEST_CURRENT_TEST") is None
if env_path.exists():
    # override=True in normal runtime so pc_client/.env wins over stale shell env vars
    load_dotenv(dotenv_path=env_path, override=_should_override)
else:
    load_dotenv(override=_should_override)

_log_handlers: list[logging.Handler] = [logging.StreamHandler()]
_pc_log_file = os.getenv("PC_LOG_FILE", "").strip()
if _pc_log_file:
    _log_path = Path(_pc_log_file)
    _log_path.parent.mkdir(parents=True, exist_ok=True)
    _log_handlers.append(
        RotatingFileHandler(
            _log_path,
            maxBytes=int(os.getenv("PC_LOG_MAX_BYTES", str(10 * 1024 * 1024))),
            backupCount=int(os.getenv("PC_LOG_BACKUP_COUNT", "5")),
            encoding="utf-8",
        )
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - PC_CORE - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=_log_handlers,
)
logger = logging.getLogger("Core")

# مسدود کردن لاگ‌های اسپم‌گونه و تکراری (درخواست‌های ۵ ثانیه‌ای مانیتورینگ)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


# ==========================================
# تشخیص سخت افزار پایه سیستم
# ==========================================
def detect_hardware() -> str:
    """Detect the available hardware (CPU/GPU)."""
    try:
        if platform.system() in ["Windows", "Linux"]:
            res = subprocess.run(
                ["nvidia-smi"],
                capture_output=True,
                check=False
            )
            if res.returncode == 0:
                return "GPU"
        elif platform.system() == "Darwin":
            if platform.machine() in ['arm64', 'aarch64']:
                return "GPU"
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Hardware detection skipped or failed: %s", e)
    return "CPU"


HW_MODE = detect_hardware()
CONFIG_FILE = current_dir / "app_config.json"
_CACHED_CFG: Any = None


# ==========================================
# مدیریت تنظیمات
# ==========================================
def init_config():
    """Initialize and load the application configuration."""
    global _CACHED_CFG  # pylint: disable=global-statement

    new_system_prompt = (
        "شما یک دستیار هوش مصنوعی فوق‌هوشمند، دقیق و حرفه‌ای هستید. "
        "پاسخ‌های شما باید همواره به زبان فارسی سلیس و روان باشد، مگر اینکه "
        "کاربر صراحتاً زبان دیگری را درخواست کند. در پاسخ‌گویی به سوالات "
        "فنی و برنامه‌نویسی، کدهای خود را همواره داخل بلاک‌های استاندارد "
        "Markdown همراه با ذکر نام زبان قرار دهید. در صورت عدم اطمینان "
        "از یک پاسخ، با صداقت آن را بیان کنید."
    )

    if not CONFIG_FILE.exists():
        d_cfg = {
            "lmstudio": {
                "host": "127.0.0.1:1234",
                "model_key": "default-model",
                "system_prompt": new_system_prompt,
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
        _CACHED_CFG = d_cfg
    else:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            _CACHED_CFG = json.load(f)

        old_prompt = (
            "شما یک دستیار هوش مصنوعی فوق‌هوشمند هستید. به زبان فارسی "
            "پاسخ دهید. کدهای برنامه‌نویسی را درون بلاک‌های استاندارد قرار دهید."
        )
        lm_cfg = _CACHED_CFG.get("lmstudio", {})
        if lm_cfg.get("system_prompt") == old_prompt:
            logger.info("Auto-upgrading system prompt.")
            _CACHED_CFG["lmstudio"]["system_prompt"] = new_system_prompt
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(_CACHED_CFG, f, indent=4, ensure_ascii=False)


init_config()

active_chats: dict[str, list] = {}
active_tasks: dict[str, asyncio.Task] = {}
ws_send_lock = asyncio.Lock()
global_http_client: Any = None
llm_semaphore: Any = None


# ==========================================
# توابع کمکی امن
# ==========================================
def get_lm_host() -> str:
    """Get the LM Studio host URL safely."""
    env_host = os.getenv("LMSTUDIO_HOST", "").strip()
    raw_host = env_host or str(_CACHED_CFG["lmstudio"]["host"]).strip().rstrip("/")
    if not raw_host.startswith("http://") and \
       not raw_host.startswith("https://"):
        return f"http://{raw_host}"
    return raw_host


async def send_packet(
    ws: Any,
    client_id: str,
    msg_type: str,
    content: str,
    extra_data: dict = None
):
    """Send a v1 protocol packet through the WebSocket to the Bridge."""
    if ws is None:
        return

    payload_dict = {"content": content}
    if extra_data:
        payload_dict.update(extra_data)

    packet = {
        "v": 1,
        "type": msg_type,
        "client_id": client_id,
        "payload": payload_dict,
        "content": content,
    }

    try:
        async with asyncio.timeout(5.0):
            async with ws_send_lock:
                await ws.send(json.dumps(packet, ensure_ascii=False))
    except TimeoutError:
        logger.error("Timeout sending packet to %s", client_id)
    except websockets.exceptions.ConnectionClosed:
        logger.debug("WebSocket closed while sending %s to %s", msg_type, client_id)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Failed to send packet to %s: %s", client_id, e)


# ==========================================
# سیستم امنیت اجرایی ابزارها
# ==========================================
class SafeMathEvaluator:
    """Safe mathematical expression evaluator."""
    operators = {
        ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg,
        ast.UAdd: operator.pos
    }

    @classmethod
    def evaluate(cls, expr: str) -> str:
        """Evaluate a mathematical expression safely."""
        try:
            node = ast.parse(expr, mode='eval').body
            result = cls._eval_node(node)
            return str(result)
        except ZeroDivisionError:
            return "Math Error: Division by zero."
        except ValueError as ve:
            return f"Math Error: {ve}"
        except Exception as e:  # pylint: disable=broad-exception-caught
            return f"Math Error: Invalid expression syntax. ({e})"

    @classmethod
    def _eval_node(cls, node):
        """Evaluate a single AST node recursively."""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, int | float):
                return node.value

        if isinstance(node, ast.BinOp):
            left = cls._eval_node(node.left)
            right = cls._eval_node(node.right)

            if isinstance(node.op, ast.Pow):
                if abs(right) > 100 or abs(left) > 100000:
                    raise ValueError("Base or Exponent too large.")

            return cls.operators[type(node.op)](left, right)

        if isinstance(node, ast.UnaryOp):
            return cls.operators[type(node.op)](cls._eval_node(node.operand))

        raise TypeError("Unsupported mathematical operation or character.")


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "انجام محاسبات ریاضی",
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
    """Execute a requested tool by name securely."""
    if name == "calculate":
        expr = args.get("expression", "")
        if not expr:
            return "Error: No expression provided."
        return SafeMathEvaluator.evaluate(expr)
    return f"Error: The tool '{name}' does not exist."


def prune_chat_history(
    chat_history: list[dict[str, Any]], max_length: int
) -> list[dict[str, Any]]:
    """Prune chat history to maintain max length."""
    if len(chat_history) <= max_length:
        return chat_history

    sys_prompt = None
    if chat_history and chat_history[0].get("role") == "system":
        sys_prompt = chat_history[0]

    while len(chat_history) > max_length:
        if len(chat_history) <= 2:
            break

        idx_to_check = 1 if sys_prompt else 0
        msg_to_remove = chat_history[idx_to_check]

        if (
            msg_to_remove.get("role") == "assistant" and
            "tool_calls" in msg_to_remove
        ):
            chat_history.pop(idx_to_check)
            while (
                len(chat_history) > idx_to_check and
                chat_history[idx_to_check].get("role") == "tool"
            ):
                chat_history.pop(idx_to_check)
        elif msg_to_remove.get("role") == "tool":
            chat_history.pop(idx_to_check)
        else:
            chat_history.pop(idx_to_check)

    if sys_prompt and (
        not chat_history or chat_history[0].get("role") != "system"
    ):
        chat_history.insert(0, sys_prompt)

    return chat_history


# ==========================================
# مانیتورینگ سخت افزار
# ==========================================
def _is_gpu_active(obj: Any) -> bool:
    """Check recursively if GPU is marked active in API response."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            k_low = str(k).lower()
            if k_low in ['gpu', 'hardware', 'acceleration']:
                v_str = str(v).lower()
                if v_str in ['false', '0', 'none', 'cpu', 'null']:
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


async def hw_monitor(ws: Any):
    """Monitor hardware status and report to server."""
    lm_host = get_lm_host()
    poll_sec = max(float(os.getenv("HW_POLL_SECONDS", "30")), 5.0)
    last_status = None

    while True:
        try:
            current_status = "OFF"
            resp = await global_http_client.get(
                f"{lm_host}/v1/models",
                timeout=3.0
            )
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    models = []
                    if isinstance(data, dict):
                        models = data.get("data", [])

                    if models:
                        current_status = "CPU"
                        if _is_gpu_active(models):
                            current_status = "GPU"
                except ValueError:
                    logger.debug("Invalid JSON from /v1/models during hw_monitor")

            if current_status != last_status:
                last_status = current_status
                try:
                    async with asyncio.timeout(2.0):
                        async with ws_send_lock:
                            await ws.send(json.dumps({
                                "v": 1,
                                "type": "hw_info",
                                "payload": {"hw": current_status},
                                "hw": current_status,
                                "content": current_status,
                            }))
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logger.debug("Failed to push hw_info (%s): %s", current_status, exc)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.debug("hw_monitor probe failed: %s", exc)
            if last_status != "OFF":
                last_status = "OFF"
                try:
                    async with asyncio.timeout(2.0):
                        async with ws_send_lock:
                            await ws.send(json.dumps({
                                "v": 1,
                                "type": "hw_info",
                                "payload": {"hw": "OFF"},
                                "hw": "OFF",
                                "content": "OFF",
                            }))
                except Exception as send_exc:  # pylint: disable=broad-exception-caught
                    logger.debug("Failed to push OFF hw_info: %s", send_exc)

        await asyncio.sleep(poll_sec)


# ==========================================
# تپش قلب (Active Heartbeat)
# ==========================================
async def heartbeat_task(ws: Any):
    """Keep the WebSocket connection alive."""
    interval = max(float(os.getenv("WS_HEARTBEAT_SECONDS", "15")), 5.0)
    while True:
        try:
            async with asyncio.timeout(2.0):
                async with ws_send_lock:
                    await ws.send(json.dumps({"v": 1, "type": "ping"}))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.debug("Heartbeat ping failed: %s", exc)
        await asyncio.sleep(interval)


# ==========================================
# مدیریت مدل‌ها
# ==========================================
async def handle_unload_models(ws: Any, client_id: str):
    """Unload models from LM Studio."""
    lm_host = get_lm_host()
    try:
        resp = await global_http_client.get(
            f"{lm_host}/v1/models", timeout=10.0
        )
        if resp.status_code == 200:
            try:
                data = resp.json()
                models = data.get("data", []) if isinstance(data, dict) else []
            except ValueError:
                models = []

            for m in models:
                mid = m["id"]
                try:
                    await global_http_client.post(
                        f"{lm_host}/api/v1/models/unload",
                        json={"model": mid},
                        timeout=10.0
                    )
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logger.warning("Failed to unload model %s: %s", mid, exc)

            await send_packet(
                ws, client_id, "queue",
                "✅ عملیات موفق: درخواست تخلیه ارسال شد."
            )
        else:
            raw_err = await resp.aread()
            err_msg = raw_err.decode('utf-8', errors='replace')[:150]
            await send_packet(
                ws, client_id, "error", f"خطای سرور: {err_msg}"
            )
    except Exception:  # pylint: disable=broad-exception-caught
        await send_packet(
            ws, client_id, "error", "ارتباط با LM Studio برقرار نشد."
        )


async def handle_embeddings(ws: Any, client_id: str, payload: dict):
    """Proxy embeddings to local LM Studio OpenAI-compatible API."""
    host = get_lm_host().rstrip("/")
    model = payload.get("model") or _CACHED_CFG.get("lmstudio", {}).get(
        "embedding_model_key", "text-embedding-embeddinggemma-300m"
    )
    inputs = payload.get("input") or payload.get("texts") or []
    if isinstance(inputs, str):
        inputs = [inputs]
    try:
        resp = await global_http_client.post(
            f"{host}/v1/embeddings",
            json={"model": model, "input": inputs},
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        await send_packet(
            ws,
            client_id,
            "embeddings_result",
            "ok",
            extra_data={
                "data": data.get("data", []),
                "model": model,
                "request_id": payload.get("request_id"),
            },
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Embeddings failed: %s", exc)
        # Always return embeddings_result so Bridge waiters do not hang until timeout
        await send_packet(
            ws,
            client_id,
            "embeddings_result",
            "error",
            extra_data={
                "error": f"Embeddings failed: {exc}",
                "data": [],
                "request_id": payload.get("request_id"),
            },
        )


async def handle_get_models(ws: Any, client_id: str):
    """Get loaded models from LM Studio."""
    lm_host = get_lm_host()
    try:
        resp = await global_http_client.get(
            f"{lm_host}/v1/models", timeout=5.0
        )
        if resp.status_code == 200:
            try:
                data = resp.json()
                models = data.get("data", []) if isinstance(data, dict) else []
            except ValueError:
                models = []
            await send_packet(
                ws, client_id, "models_list", "success", {"models": models}
            )
        else:
            await send_packet(
                ws, client_id, "error", "خطا در دریافت مدل‌ها"
            )
    except Exception:  # pylint: disable=broad-exception-caught
        await send_packet(ws, client_id, "error", "عدم دسترسی به LM Studio")


# ==========================================
# هسته هوش مصنوعی
# ==========================================
def build_chat_messages(
    system_prompt: str,
    user_text: str,
    image_b64: str | None = None,
    use_tools: bool = False,
    req_history: list[dict[str, Any]] | None = None,
    prior_messages: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build OpenAI-format chat history, preserving assistant turns and the current user turn."""
    sys_str = system_prompt or ""
    if use_tools:
        sys_str += "\nشما مجاز به استفاده از ابزارها هستید."

    messages: list[dict[str, Any]] = [{"role": "system", "content": sys_str}]

    if req_history and isinstance(req_history, list):
        for m in req_history:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            if role == "user":
                if m.get("image"):
                    img_url = str(m["image"])
                    if not img_url.startswith("data:image"):
                        img_url = f"data:image/jpeg;base64,{img_url}"
                    messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": str(m.get("content") or "تصویر را بررسی کن.")},
                            {"type": "image_url", "image_url": {"url": img_url}},
                        ],
                    })
                else:
                    messages.append({"role": "user", "content": str(m.get("content") or "")})
            elif role in {"assistant", "ai"}:
                messages.append({"role": "assistant", "content": str(m.get("content") or "")})
    elif prior_messages:
        for m in prior_messages:
            if isinstance(m, dict) and m.get("role") != "system":
                messages.append(m)

    if image_b64:
        img_url = image_b64 if image_b64.startswith("data:image") else f"data:image/jpeg;base64,{image_b64}"
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_text if user_text else "تصویر را بررسی کن."},
                {"type": "image_url", "image_url": {"url": img_url}},
            ],
        })
    elif user_text:
        trimmed = user_text[:20000]
        already_last = (
            len(messages) > 1
            and messages[-1].get("role") == "user"
            and messages[-1].get("content") == trimmed
        )
        if not already_last:
            messages.append({"role": "user", "content": trimmed})

    return messages


async def run_ai(
    ws: Any,
    client_id: str,
    user_text: str,
    requested_model: str,
    image_b64: str | None = None,
    use_tools: bool = False,
    req_history: list | None = None,
):
    """Run the main AI chat loop."""
    cfg = _CACHED_CFG
    lm_cfg = cfg["lmstudio"]
    did_start = False
    sem_acquired = False

    try:
        try:
            await asyncio.wait_for(llm_semaphore.acquire(), timeout=0.1)
            sem_acquired = True
        except TimeoutError:
            await send_packet(ws, client_id, "queue", "⏳ در صف پردازش...")
            await llm_semaphore.acquire()
            sem_acquired = True

        await send_packet(ws, client_id, "status", "thinking")

        llm_timeout = float(cfg["features"].get("llm_timeout_seconds", 900))
        lm_host = get_lm_host()
        url = f"{lm_host}/v1/chat/completions"

        async with asyncio.timeout(llm_timeout):
            m_key = requested_model if requested_model else lm_cfg.get("model_key")

            active_chats[client_id] = build_chat_messages(
                system_prompt=lm_cfg.get("system_prompt", ""),
                user_text=user_text,
                image_b64=image_b64,
                use_tools=use_tools,
                req_history=req_history,
                prior_messages=active_chats.get(client_id),
            )

            max_hist = cfg["features"]["max_history_messages"]
            active_chats[client_id] = prune_chat_history(
                active_chats[client_id], max_hist
            )

            max_tool_rounds = 5
            round_count = 0

            while round_count < max_tool_rounds:
                round_count += 1
                has_tools = any(
                    "tool_calls" in m or m.get("role") == "tool"
                    for m in active_chats[client_id]
                )

                payload = {
                    "model": m_key,
                    "messages": active_chats[client_id],
                    "temperature": lm_cfg["temperature"],
                    "stream": cfg["features"]["use_streaming"]
                }
                if lm_cfg.get("force_context_length") and lm_cfg.get("max_tokens"):
                    payload["max_tokens"] = lm_cfg["max_tokens"]

                if use_tools or has_tools:
                    payload["tools"] = TOOLS

                tool_calls_accumulator = {}
                full_r = ""

                if cfg["features"]["use_streaming"]:
                    async with global_http_client.stream(
                        "POST", url, json=payload, timeout=llm_timeout
                    ) as response:
                        if response.status_code != 200:
                            err = await response.aread()
                            dec_err = err.decode('utf-8', errors='replace')
                            raise ValueError(
                                f"API Error {response.status_code}: {dec_err}"
                            )

                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data = line[6:].strip()
                                if data == "[DONE]":
                                    break
                                if not data:
                                    continue

                                try:
                                    chunk = json.loads(data)
                                    choices = chunk.get("choices", [{}])
                                    delta = choices[0].get("delta", {})

                                    if "tool_calls" in delta:
                                        for tc in delta["tool_calls"]:
                                            idx = tc["index"]
                                            if idx not in tool_calls_accumulator:
                                                r_id = random.randint(
                                                    100000, 999999
                                                )
                                                tool_calls_accumulator[idx] = {
                                                    "id": tc.get(
                                                        "id", f"call_{r_id}"
                                                    ),
                                                    "type": "function",
                                                    "function": {
                                                        "name": "",
                                                        "arguments": ""
                                                    }
                                                }

                                            func = tc.get("function", {})
                                            f_name = func.get("name")
                                            if f_name:
                                                tool_calls_accumulator[idx][
                                                    "function"
                                                ]["name"] += str(f_name)
                                            f_args = func.get("arguments")
                                            if f_args:
                                                tool_calls_accumulator[idx][
                                                    "function"
                                                ]["arguments"] += str(f_args)

                                    content = delta.get("content")
                                    if content:
                                        did_start = True
                                        full_r += content
                                        await send_packet(
                                            ws, client_id, "chunk", content
                                        )
                                except json.JSONDecodeError:
                                    continue
                else:
                    response = await global_http_client.post(
                        url, json=payload, timeout=llm_timeout
                    )
                    if response.status_code != 200:
                        raise ValueError(f"API error: {response.status_code}")

                    data = response.json()
                    msg = data.get("choices", [{}])[0].get("message", {})

                    if "tool_calls" in msg:
                        for i, tc in enumerate(msg["tool_calls"]):
                            tool_calls_accumulator[i] = tc

                    full_r = msg.get("content") or ""
                    if full_r:
                        did_start = True
                        await send_packet(ws, client_id, "full", full_r)

                if tool_calls_accumulator:
                    assistant_msg = {
                        "role": "assistant",
                        "content": full_r if full_r else "",
                        "tool_calls": list(tool_calls_accumulator.values())
                    }
                    active_chats[client_id].append(assistant_msg)

                    for _idx, tc in tool_calls_accumulator.items():
                        func_name = tc["function"]["name"]
                        arg_str = tc["function"]["arguments"]

                        try:
                            if not arg_str.strip():
                                args = {}
                            else:
                                args = json.loads(arg_str)

                            if not isinstance(args, dict):
                                raise ValueError("Invalid argument type.")

                            logger.info("Tool [%s] args: %s", func_name, args)
                            await send_packet(
                                ws, client_id, "tool_event",
                                f"در حال اجرای ابزار: {func_name}"
                            )

                            raw_result = str(execute_tool(func_name, args))
                            if len(raw_result) > 2000:
                                result_str = raw_result[:1995] + "..."
                            else:
                                result_str = raw_result

                        except (json.JSONDecodeError, ValueError):
                            result_str = "Error: Invalid JSON arguments."

                        active_chats[client_id].append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "name": func_name,
                            "content": result_str
                        })

                    await send_packet(ws, client_id, "status", "thinking")
                    continue

                if full_r:
                    active_chats[client_id].append({
                        "role": "assistant",
                        "content": full_r
                    })
                await send_packet(ws, client_id, "done", "")
                break

            if round_count >= max_tool_rounds:
                logger.warning("Max Tool Rounds limit.")
                await send_packet(ws, client_id, "error", "تکرار بیش از حد.")

    except asyncio.CancelledError:
        logger.info("Task for %s gracefully cancelled.", client_id)
    except TimeoutError:
        logger.error("AI processing timed out.")
        await send_packet(ws, client_id, "error", "تایم‌اوت در پردازش.")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Fatal AI Error:\n%s", traceback.format_exc())
        if did_start:
            try:
                await send_packet(
                    ws, client_id, "chunk", "\n\n[⚠️ توقف با خطا]"
                )
                await send_packet(ws, client_id, "done", "")
            except Exception as send_exc:  # pylint: disable=broad-exception-caught
                logger.warning("Failed sending error termination packet: %s", send_exc)
        else:
            try:
                await send_packet(
                    ws, client_id, "error", f"خطای پردازش: {str(e)[:80]}"
                )
            except Exception as send_exc:  # pylint: disable=broad-exception-caught
                logger.warning("Failed sending AI error packet: %s", send_exc)
    finally:
        if sem_acquired:
            llm_semaphore.release()
        if active_tasks.get(client_id) == asyncio.current_task():
            active_tasks.pop(client_id, None)


# ==========================================
# کارگر اصلی ارتباطات
# ==========================================
async def pc_worker():
    """Main worker to connect to the Bridge server."""
    global global_http_client  # pylint: disable=global-statement

    raw_url = os.getenv(
        "BRIDGE_WS_URL", "ws://127.0.0.1:8010"
    ).strip().rstrip("/")

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

    worker_token = os.getenv("WORKER_TOKEN", "").strip()
    if not worker_token:
        raise RuntimeError("WORKER_TOKEN is required in pc_client/.env")
    sep = "&" if "?" in uri else "?"
    uri = f"{uri}{sep}token={worker_token}"

    logger.info("Normalized Bridge Endpoint: %s", uri.split("token=")[0] + "token=***")

    tls_verify = os.getenv("TLS_VERIFY", "true").strip().lower() in {"1", "true", "yes"}
    if uri.startswith("wss://"):
        ssl_ctx = ssl.create_default_context()
        if not tls_verify:
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            logger.warning("TLS_VERIFY=false — certificate verification disabled")
    else:
        ssl_ctx = None

    reconnect_attempts = 0

    limits = httpx.Limits(
        max_keepalive_connections=20,
        max_connections=40,
        keepalive_expiry=30.0
    )
    llm_timeout = float(
        _CACHED_CFG["features"].get("llm_timeout_seconds", 900)
    )
    http_timeout = httpx.Timeout(llm_timeout, connect=10.0)

    async with httpx.AsyncClient(
        limits=limits, timeout=http_timeout, trust_env=False
    ) as client:
        global_http_client = client

        while True:
            try:
                async with websockets.connect(
                    uri,
                    ssl=ssl_ctx,
                    ping_interval=None,
                    max_size=20_971_520
                ) as ws:
                    logger.info("🟢 Linked to Bridge Successfully.")
                    reconnect_attempts = 0

                    monitor_task = asyncio.create_task(hw_monitor(ws))
                    hb_task = asyncio.create_task(heartbeat_task(ws))
                    asyncio.create_task(handle_get_models(ws, "system"))

                    try:
                        async for raw in ws:
                            msg = json.loads(raw)

                            if msg.get("type") == "ping":
                                try:
                                    async with asyncio.timeout(2.0):
                                        async with ws_send_lock:
                                            await ws.send(
                                                json.dumps({"v": 1, "type": "pong"})
                                            )
                                except Exception as exc:  # pylint: disable=broad-exception-caught
                                    logger.debug("Failed sending pong: %s", exc)
                                continue

                            if msg.get("type") == "pong":
                                continue

                            # Protocol v1: plaintext JSON from Bridge
                            if msg.get("v") == 1 and msg.get("client_id"):
                                msg_type = msg.get("type")
                                cid = msg["client_id"]
                                dec = msg.get("payload") or {}
                                if isinstance(dec, str):
                                    try:
                                        dec = json.loads(dec)
                                    except json.JSONDecodeError:
                                        dec = {"content": dec}
                                if msg_type == "chat" and isinstance(dec, dict):
                                    rag_ctx = dec.get("rag_context")
                                    if rag_ctx:
                                        user_text = dec.get("content") or dec.get("message") or ""
                                        dec["content"] = (
                                            "Use the following retrieved context when helpful.\n"
                                            f"CONTEXT:\n{rag_ctx}\n\nUSER:\n{user_text}"
                                        )

                                if msg_type == "sys_cancel":
                                    if cid in active_tasks:
                                        active_tasks[cid].cancel()
                                    active_chats.pop(cid, None)
                                elif msg_type == "clear_history":
                                    if cid in active_tasks:
                                        active_tasks[cid].cancel()
                                    active_chats.pop(cid, None)
                                    await send_packet(
                                        ws, cid, "queue",
                                        "✅ تاریخچه سرور پردازشی پاک شد."
                                    )
                                elif msg_type == "get_models":
                                    asyncio.create_task(handle_get_models(ws, cid))
                                elif msg_type == "unload_models":
                                    asyncio.create_task(handle_unload_models(ws, cid))
                                elif msg_type == "embeddings":
                                    asyncio.create_task(
                                        handle_embeddings(ws, cid, dec)
                                    )
                                elif msg_type == "chat":
                                    if cid in active_tasks:
                                        active_tasks[cid].cancel()
                                        await asyncio.sleep(0.05)
                                    user_text = (
                                        dec.get("content")
                                        or dec.get("text")
                                        or dec.get("message")
                                        or ""
                                    )
                                    active_tasks[cid] = asyncio.create_task(
                                        run_ai(
                                            ws=ws,
                                            client_id=cid,
                                            user_text=user_text,
                                            requested_model=dec.get("model", ""),
                                            image_b64=dec.get("image"),
                                            use_tools=bool(dec.get("use_tools", False)),
                                            req_history=dec.get("history"),
                                        )
                                    )
                                continue

                            if msg.get("client_id") and msg.get("payload"):
                                # Legacy encrypted payload path
                                try:
                                    decrypted_raw = decrypt_message(msg["payload"])
                                except RuntimeError:
                                    logger.error("ENCRYPTION_KEY missing for legacy payload")
                                    continue
                                if "خطای امنیتی" in decrypted_raw or "Security error" in decrypted_raw:
                                    logger.error("Security mismatch.")
                                    continue

                                dec = json.loads(decrypted_raw)
                                msg_type = dec.get("type")
                                cid = msg["client_id"]

                                if msg_type == "sys_cancel":
                                    if cid in active_tasks:
                                        active_tasks[cid].cancel()
                                    active_chats.pop(cid, None)

                                elif msg_type == "clear_history":
                                    if cid in active_tasks:
                                        active_tasks[cid].cancel()
                                    active_chats.pop(cid, None)
                                    await send_packet(
                                        ws, cid, "queue",
                                        "✅ تاریخچه سرور پردازشی پاک شد."
                                    )

                                elif msg_type == "get_models":
                                    asyncio.create_task(
                                        handle_get_models(ws, cid)
                                    )

                                elif msg_type == "unload_models":
                                    asyncio.create_task(
                                        handle_unload_models(ws, cid)
                                    )

                                elif msg_type == "chat":
                                    if dec.get("text") or dec.get("image"):
                                        if cid in active_tasks:
                                            active_tasks[cid].cancel()
                                            await asyncio.sleep(0.05)

                                        req_model = dec.get("model", "")
                                        has_tools = dec.get("use_tools", False)
                                        active_tasks[cid] = asyncio.create_task(
                                            run_ai(
                                                ws=ws,
                                                client_id=cid,
                                                user_text=dec.get("text", ""),
                                                requested_model=req_model,
                                                image_b64=dec.get("image"),
                                                use_tools=has_tools,
                                                req_history=dec.get("history")
                                            )
                                        )
                    finally:
                        monitor_task.cancel()
                        hb_task.cancel()
                        await asyncio.gather(monitor_task, hb_task, return_exceptions=True)

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("🔴 Connection Dropped: %s", e)
                for t in active_tasks.values():
                    t.cancel()
                active_tasks.clear()

                delay = min(60.0, (2 ** reconnect_attempts) + random.random())
                reconnect_attempts += 1
                logger.info("Reconnecting in %.2f seconds...", delay)
                await asyncio.sleep(delay)


if __name__ == "__main__":
    init_config()
    max_reqs = _CACHED_CFG["features"]["max_concurrent_requests"]
    llm_semaphore = asyncio.Semaphore(max_reqs)

    logger.info("Starting PC Core | HW: %s | Concurrency: %s", HW_MODE, max_reqs)
    try:
        asyncio.run(pc_worker())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user. Shutting down gracefully.")
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.critical("Critical System Failure: %s", err)