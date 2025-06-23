"""Test src/crx_repo/config.py."""

from typing import NamedTuple
from asyncio import StreamReader
from asyncio import StreamWriter
from asyncio import start_server
from pathlib import Path
from datetime import UTC
from datetime import datetime
from datetime import timedelta

import pytest
from aiohttp.web import UrlDispatcher
from cryptography.x509 import Name
from cryptography.x509 import DNSName
from cryptography.x509 import NameOID
from cryptography.x509 import NameAttribute
from cryptography.x509 import CertificateBuilder
from cryptography.x509 import SubjectAlternativeName
from cryptography.x509 import random_serial_number
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.hazmat.primitives.serialization import PrivateFormat
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key

from crx_repo.cache import MemoryCache
from crx_repo.chrome import ChromeExtensionDownloader
from crx_repo.config import Config
from crx_repo.config import Extension
from crx_repo.config import TlsHttpListenConfig


class _SslExample(NamedTuple):
    public: Path
    private: Path
    password: str | None


@pytest.fixture
def ssl_example(tmp_path: Path) -> _SslExample:
    """A pytest fixture to generate ssl public key and private key."""
    ssl_pubkey = tmp_path / "pubkey.crt"
    ssl_privkey = tmp_path / "privkey.key"
    privkey = generate_private_key(65537, 2048)
    _ = ssl_privkey.write_bytes(
        privkey.private_bytes(
            Encoding.PEM,
            PrivateFormat.TraditionalOpenSSL,
            BestAvailableEncryption(b"test"),
        ),
    )
    subject = issuer = Name(
        [
            NameAttribute(NameOID.COUNTRY_NAME, "US"),
            NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
            NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            NameAttribute(NameOID.ORGANIZATION_NAME, "CRX Repo"),
            NameAttribute(NameOID.COMMON_NAME, "127.0.0.1"),
        ],
    )
    builder = CertificateBuilder(
        issuer,
        subject,
        privkey.public_key(),
        random_serial_number(),
        datetime.now(UTC),
        datetime.now(UTC) + timedelta(1),
    )
    builder = builder.add_extension(
        SubjectAlternativeName([DNSName("localhost")]),
        False,  # noqa: FBT003
    )
    cert = builder.sign(privkey, SHA256())
    _ = ssl_pubkey.write_bytes(cert.public_bytes(Encoding.PEM))
    return _SslExample(ssl_pubkey, ssl_privkey, "test")


@pytest.mark.asyncio
async def test_ssl_context(ssl_example: _SslExample, unused_tcp_port: int):
    """Test `crx_repo.config.TlsHttpListenConfig.ssl_context` property."""
    config = TlsHttpListenConfig(
        cert=ssl_example.public,
        key=ssl_example.private,
        password=ssl_example.password,
    )

    async def client_connected(reader: StreamReader, writer: StreamWriter):
        data = await reader.read()
        writer.write(data)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await start_server(
        client_connected,
        "127.0.0.1",
        unused_tcp_port,
        ssl=config.ssl_context,
    )
    async with server:
        pass


def test_get_downloader(cache: MemoryCache):
    """Test `crx_repo.config.Extension.get_downloader` method."""
    extension = Extension.model_validate(
        {
            "extension-id": "abcdefghijklmnopqrstuvwxyzabcdef",
            "extension-provider": "chrome",
        },
    )
    downloader = extension.get_downloader("128.0", None, cache)
    assert isinstance(downloader, ChromeExtensionDownloader)


def test_get_cache(tmp_path: Path):
    """Test `crx_repo.config.Config.get_cache` method."""
    config = Config.model_validate({})
    router = UrlDispatcher()
    cache = config.get_cache(tmp_path, router, "/example-prefix", "example-router-name")
    assert isinstance(cache, MemoryCache)
