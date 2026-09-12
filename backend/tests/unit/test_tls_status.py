"""Unit-тесты для app/services/tls_status.py."""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, patch

import pytest

from app.services.tls_status import TlsStatusOut, get_tls_status_info


class TestGetTlsStatusInfo:
    @pytest.mark.asyncio
    async def test_no_cert_no_key(self, tmp_path):
        cert = tmp_path / "cert.pem"
        key = tmp_path / "key.pem"
        result = await get_tls_status_info(cert, key)
        assert result.cert_exists is False
        assert result.key_exists is False
        assert result.cert_expires_at is None
        assert result.cert_subject is None

    @pytest.mark.asyncio
    async def test_key_exists_cert_absent(self, tmp_path):
        cert = tmp_path / "cert.pem"
        key = tmp_path / "key.pem"
        key.write_text("KEY DATA")
        result = await get_tls_status_info(cert, key)
        assert result.cert_exists is False
        assert result.key_exists is True
        assert result.cert_expires_at is None
        assert result.cert_subject is None

    @pytest.mark.asyncio
    async def test_cert_parses_notafter_and_subject(self, tmp_path):
        cert = tmp_path / "cert.pem"
        cert.write_text("CERT DATA")
        key = tmp_path / "key.pem"
        key.write_text("KEY DATA")

        stdout = b"notAfter=Jan  1 00:00:00 2030 GMT\nsubject=CN=example.com, O=Org\n"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(stdout, b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await get_tls_status_info(cert, key)

        mock_exec.assert_awaited_once()
        assert result.cert_exists is True
        assert result.key_exists is True
        assert result.cert_expires_at == "Jan  1 00:00:00 2030 GMT"
        assert result.cert_subject == "CN=example.com, O=Org"

    @pytest.mark.asyncio
    async def test_cert_parses_only_notafter(self, tmp_path):
        cert = tmp_path / "cert.pem"
        cert.write_text("CERT DATA")
        key = tmp_path / "key.pem"

        stdout = b"notAfter=Dec 31 23:59:59 2025 GMT\n"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(stdout, b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await get_tls_status_info(cert, key)

        assert result.cert_expires_at == "Dec 31 23:59:59 2025 GMT"
        assert result.cert_subject is None

    @pytest.mark.asyncio
    async def test_cert_parses_only_subject(self, tmp_path):
        cert = tmp_path / "cert.pem"
        cert.write_text("CERT DATA")
        key = tmp_path / "key.pem"

        stdout = b"subject=O=MyOrg\n"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(stdout, b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await get_tls_status_info(cert, key)

        assert result.cert_expires_at is None
        assert result.cert_subject == "O=MyOrg"

    @pytest.mark.asyncio
    async def test_openssl_oserror_swallowed(self, tmp_path):
        cert = tmp_path / "cert.pem"
        cert.write_text("CERT DATA")
        key = tmp_path / "key.pem"

        with patch("asyncio.create_subprocess_exec", side_effect=OSError("openssl not found")):
            result = await get_tls_status_info(cert, key)

        assert result.cert_exists is True
        assert result.cert_expires_at is None
        assert result.cert_subject is None

    @pytest.mark.asyncio
    async def test_timeout_error_swallowed(self, tmp_path):

        cert = tmp_path / "cert.pem"
        cert.write_text("CERT DATA")
        key = tmp_path / "key.pem"

        async def _mock_wait_for(fut, timeout):
            with contextlib.suppress(Exception):
                await fut
            raise TimeoutError()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.wait_for", new=_mock_wait_for),
        ):
            result = await get_tls_status_info(cert, key)

        assert result.cert_exists is True
        assert result.cert_expires_at is None

    @pytest.mark.asyncio
    async def test_empty_openssl_output(self, tmp_path):
        cert = tmp_path / "cert.pem"
        cert.write_text("CERT DATA")
        key = tmp_path / "key.pem"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await get_tls_status_info(cert, key)

        assert result.cert_expires_at is None
        assert result.cert_subject is None

    def test_tls_status_out_schema(self):
        out = TlsStatusOut(
            cert_exists=True,
            key_exists=False,
            cert_expires_at="Jan 1 2030",
            cert_subject="CN=test",
        )
        assert out.cert_exists is True
        assert out.key_exists is False
