"""Classes and functions to download crx from Google Web Store."""

import asyncio
import hashlib
import logging
from http import HTTPStatus
from typing import TypeGuard
from aiohttp import ClientError
from pathlib import Path
from urllib.parse import urlencode
from aiohttp.client import ClientSession
from defusedxml.ElementTree import fromstring  # pyright: ignore[reportUnknownVariableType]


_logger = logging.getLogger(__name__)


class ExtensionDownloader:
    """Extension downloader."""
    def __init__(
        self,
        extension_id: str,
        interval: int,
        chromium_version: str,
        cache_path: Path,
        proxy: str | None,
    ):
        """Initialize ExtensionDownloader with arguments given."""
        self.extension_id = extension_id
        self.interval = interval
        self.chromium_version = chromium_version
        self.cache_path = cache_path / extension_id
        if not self.cache_path.is_dir():
            if self.cache_path.exists():
                self.cache_path.unlink()
            self.cache_path.mkdir(parents=True)
        self.proxy = proxy
        if self.proxy is not None:
            _logger.info("Using proxy %s to download extension...", self.proxy)
        self.CHROME_WEB_STORE_API_BASE = "https://clients2.google.com/service/update2/crx"
        self.CHUNK_SIZE_BYTES = 1024 * 1024  # 1MB

    async def download_forever(self):
        """Download extension forever."""
        while True:
            try:
                await self._do_download()
                await asyncio.sleep(self.interval)
            except (asyncio.CancelledError, KeyboardInterrupt):
                break
        _logger.debug("Cleaning old extensions...")
        for p in sorted(
            self.cache_path.rglob("*.crx"),
            key=lambda p: p.stat().st_mtime,
        )[:-1]:
            p.unlink()
        _logger.debug(
            "Stopping downloader for extension %s",
            self.extension_id,
        )

    async def _do_download(self):
        async with ClientSession() as session:
            update = await self._check_update(session)
            if not ExtensionDownloader._is_updatecheck_valid(update):
                return
            url, sha256, size, version = update
            if not self._requires_download(version):
                _logger.info("No need to download extension %s.", self.extension_id)
                return
            async with session.get(url, proxy=self.proxy) as response:
                if response.status != HTTPStatus.OK:
                    _logger.debug("Failed to download extension.")
                    return
                if response.content_length is None:
                    _logger.warning("No Content-Length header found.")
                elif response.content_length != int(size):
                    _logger.warning("Content-Length is not equals to size returned by API.")
                hash_calculator = hashlib.sha256()
                extension_path = self.cache_path / (version + ".crx.part")
                with extension_path.open("wb") as writer:
                    try:
                        async for chunk in response.content.iter_chunked(self.CHUNK_SIZE_BYTES):
                            chunk_size = writer.write(chunk)
                            hash_calculator.update(chunk)
                            _logger.debug(
                                "Writing %s byte(s) into %s...",
                                chunk_size,
                                extension_path,
                            )
                    except ClientError as e:
                        _logger.error("Failed to download because %s", e)
                    except asyncio.TimeoutError:
                        _logger.error("Failed to build because async operation timeout.")
                _logger.debug("Checking checksums of extension %s...", self.extension_id)
                sha256_hash = hash_calculator.hexdigest()
                if sha256_hash != sha256:
                    _logger.error(
                        "SHA256 checksum of %s mismatch. Removing file.",
                        self.extension_id,
                    )
                    extension_path.unlink()
                else:
                    _logger.info(
                        "SHA256 checksum of %s match. Keeping file.",
                        self.extension_id,
                    )
                    _ = extension_path.rename(extension_path.parent / extension_path.stem)

    async def _check_update(
        self,
        session: ClientSession,
    ) -> tuple[str | None, str | None, str | None, str | None] | None:
        # Get version
        params: dict[str, str] = {
            "response": "updatecheck",
            "acceptformat": "crx2,crx3",
            "prodversion": self.chromium_version,
            "x": urlencode({
                "id": self.extension_id,
            }) + "&uc"
        }
        async with session.get(
            self.CHROME_WEB_STORE_API_BASE,
            params=params,
            proxy=self.proxy,
        ) as response:
            text = await response.text()
            if response.status != HTTPStatus.OK:
                _logger.debug(
                    "Failed to send update check request, it returns `%s`",
                    text
                )
                return None
            element = fromstring(text)
            updatecheck = element.find("./*/{http://www.google.com/update2/response}updatecheck")
            if updatecheck is None:
                _logger.debug("No update is found for extension %s.", self.extension_id)
                return None
            status = updatecheck.get("status")
            if status != "ok":
                _logger.debug("Update check status is not OK.")
                return None
            return (
                updatecheck.get("codebase"),
                updatecheck.get("hash_sha256"),
                updatecheck.get("size"),
                updatecheck.get("version"),
            )

    @staticmethod
    def _is_updatecheck_valid(
        updatecheck: tuple[str | None, str | None, str | None, str | None] | None
    ) -> TypeGuard[tuple[str, str, str, str]]:
        return updatecheck is not None and all(item is not None for item in updatecheck)

    def _requires_download(self, version: str) -> bool:
        current_version = self._get_current_version()
        if current_version is None:
            return True
        current_versions = current_version.split(".")
        versions = version.split(".")
        max_count = max(len(current_versions), len(versions))
        for i in range(max_count):
            current_version_value = int(current_versions[i]) if len(current_versions) > i else 0
            versions_value = int(versions[i]) if len(versions) > i else 0
            if versions_value > current_version_value:
                return True
        return False

    def _get_current_version(self) -> str | None:
        paths = self.cache_path.glob("*.crx")
        ordered = sorted(paths, key=lambda x: x.stat().st_mtime)
        return ordered[-1].name.removesuffix(".crx") if len(ordered) > 0 else None
