"""Cryptography utilities for Bridge ↔ Worker relay (AES-256-GCM authenticated encryption)."""

from __future__ import annotations

import base64
import hashlib
import logging
import os

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("Crypto")

MAX_PAYLOAD_BYTES = 1024 * 1024 * 2
NONCE_LEN = 12
TAG_LEN = 16
V2_PREFIX = "v2:"


def _load_key() -> bytes:
    raw_key = os.getenv("ENCRYPTION_KEY")
    if not raw_key or len(raw_key.strip()) < 16:
        raise RuntimeError(
            "ENCRYPTION_KEY is missing or too short. "
            "Set a strong key in .env (min 16 chars). No insecure default."
        )
    return hashlib.sha256(raw_key.strip().encode("utf-8")).digest()


try:
    KEY = _load_key()
except RuntimeError:
    KEY = b""


def encrypt_message(text: str) -> str:
    """AES-256-GCM with a random 96-bit nonce and 128-bit auth tag."""
    if not text:
        return ""
    if not KEY:
        raise RuntimeError("ENCRYPTION_KEY is not configured")
    nonce = get_random_bytes(NONCE_LEN)
    cipher = AES.new(KEY, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(text.encode("utf-8"))
    blob = base64.b64encode(nonce + tag + ciphertext).decode("ascii")
    return f"{V2_PREFIX}{blob}"


def decrypt_message(encrypted_payload: str) -> str:
    """Decrypt and authenticate AES-256-GCM payload with size checks."""
    if not encrypted_payload:
        return ""
    if not KEY:
        raise RuntimeError("ENCRYPTION_KEY is not configured")
    try:
        raw_b64 = (
            encrypted_payload[len(V2_PREFIX) :]
            if encrypted_payload.startswith(V2_PREFIX)
            else encrypted_payload
        )
        data = base64.b64decode(raw_b64, validate=True)
        if len(data) > MAX_PAYLOAD_BYTES:
            raise ValueError("Payload too large")
        if len(data) < NONCE_LEN + TAG_LEN:
            raise ValueError("Invalid data length")

        nonce = data[:NONCE_LEN]
        tag = data[NONCE_LEN : NONCE_LEN + TAG_LEN]
        ciphertext = data[NONCE_LEN + TAG_LEN :]
        cipher = AES.new(KEY, AES.MODE_GCM, nonce=nonce)
        decrypted = cipher.decrypt_and_verify(ciphertext, tag)
        return decrypted.decode("utf-8")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Payload decryption/authentication failed: %s", type(exc).__name__)
        return (
            '{"type": "error", "content": '
            '"Security error: key mismatch or corrupted payload."}'
        )
