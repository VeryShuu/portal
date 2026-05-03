"""Кастомный identifier для fastapi-limiter.

Использует X-Real-IP (выставляется nginx из $remote_addr, клиент подделать не может)
вместо X-Forwarded-For (который fastapi-limiter по умолчанию берёт из первого
элемента, позволяя байпас через подделанный заголовок).
"""

from __future__ import annotations

import hashlib

from fastapi import Request


async def real_ip_identifier(request: Request) -> str:
    """Идентификатор для rate-limit: X-Real-IP + путь.

    Порядок источников:
    1. X-Real-IP — выставляется trusted proxy (nginx) из $remote_addr.
    2. request.client.host — fallback при обращении без proxy (dev/tests).
    """
    real_ip = request.headers.get("X-Real-IP")
    if not real_ip:
        real_ip = request.client.host if request.client else "unknown"
    return f"{real_ip}:{request.scope['path']}"


async def email_identifier(request: Request) -> str:
    """Идентификатор для local login по email (SHA-256), с fallback на real IP."""
    try:
        import json as _json

        raw = await request.body()
        body = _json.loads(raw) if raw else {}
        email = (body.get("email") or "").strip().lower() if isinstance(body, dict) else ""
        if not email:
            return await real_ip_identifier(request)
        email_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
        return f"login:email:{email_hash}"
    except Exception:
        return await real_ip_identifier(request)
