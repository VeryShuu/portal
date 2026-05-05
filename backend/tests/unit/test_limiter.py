from __future__ import annotations

import hashlib
import json

import pytest
from starlette.testclient import TestClient
from starlette.requests import Request
from starlette.datastructures import Headers

from app.core.limiter import email_identifier, real_ip_identifier


def _make_request(
    body: bytes = b"",
    content_type: str = "application/json",
    real_ip: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = [
        (b"content-type", content_type.encode()),
    ]
    if real_ip:
        headers.append((b"x-real-ip", real_ip.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/local/login",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_email_identifier_json():
    body = json.dumps({"email": "User@Example.com", "password": "secret"}).encode()
    req = _make_request(body=body, content_type="application/json")
    result = await email_identifier(req)
    expected_hash = hashlib.sha256(b"user@example.com").hexdigest()
    assert result == f"login:email:{expected_hash}"


@pytest.mark.asyncio
async def test_email_identifier_form_urlencoded():
    body = b"email=User%40Example.com&password=secret"
    req = _make_request(body=body, content_type="application/x-www-form-urlencoded")
    result = await email_identifier(req)
    expected_hash = hashlib.sha256(b"user@example.com").hexdigest()
    assert result == f"login:email:{expected_hash}"


@pytest.mark.asyncio
async def test_email_identifier_no_email_falls_back_to_ip():
    body = json.dumps({"password": "secret"}).encode()
    req = _make_request(body=body, content_type="application/json", real_ip="10.0.0.1")
    result = await email_identifier(req)
    assert "login:email:" not in result
    assert "10.0.0.1" in result


@pytest.mark.asyncio
async def test_email_identifier_unknown_content_type_falls_back():
    body = b"some-binary-data"
    req = _make_request(body=body, content_type="text/plain", real_ip="10.0.0.2")
    result = await email_identifier(req)
    assert "login:email:" not in result


@pytest.mark.asyncio
async def test_email_identifier_malformed_json_falls_back():
    body = b"not-json"
    req = _make_request(body=body, content_type="application/json", real_ip="10.0.0.3")
    result = await email_identifier(req)
    assert "login:email:" not in result
    assert "10.0.0.3" in result


@pytest.mark.asyncio
async def test_real_ip_identifier_uses_x_real_ip():
    req = _make_request(real_ip="192.168.1.5")
    result = await real_ip_identifier(req)
    assert result.startswith("192.168.1.5:")


@pytest.mark.asyncio
async def test_real_ip_identifier_fallback_to_client_host():
    req = _make_request()
    result = await real_ip_identifier(req)
    assert result.startswith("127.0.0.1:")
