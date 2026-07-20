import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


def _cipher() -> Fernet:
    secret = get_settings().ai_config_secret.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt_api_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    return _cipher().encrypt(api_key.encode("utf-8")).decode("ascii")


def decrypt_api_key(encrypted_api_key: str | None) -> str | None:
    if not encrypted_api_key:
        return None
    try:
        return _cipher().decrypt(encrypted_api_key.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("無法解密 AI API Key，請重新儲存此設定") from exc
