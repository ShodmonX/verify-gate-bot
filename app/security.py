import base64
import hmac
import hashlib
from datetime import datetime, timezone
from typing import Tuple
from uuid import UUID


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def encode_session_id(session_id: UUID) -> str:
    return _b64_encode(session_id.bytes)


def decode_session_id(token: str) -> UUID:
    return UUID(bytes=_b64_decode(token))


def sign(secret: str, data: str, length: int = 8) -> str:
    digest = hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).digest()
    return _b64_encode(digest[:length])


def build_callback_signature(secret: str, group_id: int, user_id: int, session_id: UUID) -> str:
    data = f"{group_id}:{user_id}:{session_id}"
    return sign(secret, data, length=8)


def verify_callback_signature(secret: str, group_id: int, user_id: int, session_id: UUID, signature: str) -> bool:
    expected = build_callback_signature(secret, group_id, user_id, session_id)
    return hmac.compare_digest(expected, signature)


TOKEN_LEN = 22  # urlsafe base64 of 16 bytes without padding
SIG_LEN = 11    # urlsafe base64 of 8 bytes without padding


def build_start_payload(secret: str, group_id: int, user_id: int, session_id: UUID) -> str:
    data = f"{group_id}:{user_id}:{session_id}"
    sig = sign(secret, data, length=8)
    token = encode_session_id(session_id)
    return f"{token}{sig}"


def parse_start_payload(secret: str, payload: str) -> Tuple[int, int, UUID] | None:
    try:
        if len(payload) < TOKEN_LEN + 1:
            return None
        token = payload[:TOKEN_LEN]
        session_id = decode_session_id(token)
        return 0, 0, session_id
    except Exception:
        return None


def verify_start_payload(
    secret: str, group_id: int, user_id: int, session_id: UUID, payload: str
) -> bool:
    try:
        if len(payload) < TOKEN_LEN + 1:
            return False
        token = payload[:TOKEN_LEN]
        sig = payload[TOKEN_LEN: TOKEN_LEN + SIG_LEN]
        if decode_session_id(token) != session_id:
            return False
        data = f"{group_id}:{user_id}:{session_id}"
        expected = sign(secret, data, length=8)
        return hmac.compare_digest(expected, sig)
    except Exception:
        return False
