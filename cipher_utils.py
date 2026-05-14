import os
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes
from dotenv import load_dotenv
import logging

# ---------------------------------------------------------
# نکته مهم برای توسعه دهنده:
# این یک فایل محلی است. کتابخانه اصلی که استفاده شده pycryptodome است.
# به هیچ وجه نباید `pip install cipher_utils` را اجرا کنید!
# ---------------------------------------------------------

load_dotenv()
logger = logging.getLogger("Crypto")

raw_key = os.getenv("ENCRYPTION_KEY", "12345678901234567890123456789012")
# تضمین طول کلید برای AES-256
KEY = raw_key.encode('utf-8')[:32].ljust(32, b'\0')

# جلوگیری از حملات Memory Filling (دو مگابایت سقف)
MAX_PAYLOAD_BYTES = 1024 * 1024 * 2 

def encrypt_message(text: str) -> str:
    """رمزنگاری AES-CBC با IV تصادفی در هر پیام"""
    if not text: return ""
    try:
        iv = get_random_bytes(16)
        cipher = AES.new(KEY, AES.MODE_CBC, iv)
        padded_data = pad(text.encode('utf-8'), AES.block_size)
        encrypted_bytes = cipher.encrypt(padded_data)
        return base64.b64encode(iv + encrypted_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f"Encryption error: {e}")
        return ""

def decrypt_message(encrypted_b64: str) -> str:
    """رمزگشایی ایمن با چک کردن یکپارچگی داده"""
    if not encrypted_b64: return ""
    try:
        data = base64.b64decode(encrypted_b64)
        if len(data) > MAX_PAYLOAD_BYTES: raise ValueError("Payload too large")
        if len(data) < 16: raise ValueError("Invalid data length")
        
        iv, ciphertext = data[:16], data[16:]
        cipher = AES.new(KEY, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ciphertext), AES.block_size).decode('utf-8')
    except Exception:
        return '{"type": "error", "content": "خطای امنیتی: عدم تطابق کلیدها یا داده مخدوش است."}'