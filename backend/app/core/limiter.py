"""Кастомный identifier для fastapi-limiter.

Использует X-Real-IP (выставляется nginx из $remote_addr, клиент подделать не может)
вместо X-Forwarded-For (который fastapi-limiter по умолчанию берёт из первого
элемента, позволяя байпас через подделанный заголовок).
"""
from __future__ import annotations

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
