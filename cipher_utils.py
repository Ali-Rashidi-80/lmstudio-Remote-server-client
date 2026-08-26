"""Cryptography utilities for Bridge ↔ Worker relay (optional payload encryption)."""

from __future__ import annotations

import base64
import logging
import os

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("Crypto")

MAX_PAYLOAD_BYTES = 1024 * 1024 * 2


def _load_key() -> bytes:
    raw_key = os.getenv("ENCRYPTION_KEY")
    if not raw_key or len(raw_key.strip()) < 16:
        raise RuntimeError(
            "ENCRYPTION_KEY is missing or too short. "
            "Set a strong key in .env (min 16 chars). No insecure default."
        )
    return raw_key.encode("utf-8")[:32].ljust(32, b"\0")


try:
    KEY = _load_key()
except RuntimeError:
    KEY = b""


def encrypt_message(text: str) -> str:
    """AES-CBC with a random IV per message."""
    if not text:
        return ""
    if not KEY:
        raise RuntimeError("ENCRYPTION_KEY is not configured")
    try:
        iv = get_random_bytes(16)
        cipher = AES.new(KEY, AES.MODE_CBC, iv)
        padded_data = pad(text.encode("utf-8"), AES.block_size)
        encrypted_bytes = cipher.encrypt(padded_data)
        return base64.b64encode(iv + encrypted_bytes).decode("utf-8")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Encryption error: %s", e)
        return ""


def decrypt_message(encrypted_b64: str) -> str:
    """Decrypt AES-CBC payload with size checks."""
    if not encrypted_b64:
        return ""
    if not KEY:
        raise RuntimeError("ENCRYPTION_KEY is not configured")
    try:
        data = base64.b64decode(encrypted_b64)
        if len(data) > MAX_PAYLOAD_BYTES:
            raise ValueError("Payload too large")
        if len(data) < 16:
            raise ValueError("Invalid data length")

        iv = data[:16]
        ciphertext = data[16:]
        cipher = AES.new(KEY, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
        return decrypted.decode("utf-8")
    except Exception:  # pylint: disable=broad-exception-caught
        return (
            '{"type": "error", "content": '
            '"Security error: key mismatch or corrupted payload."}'
        )
