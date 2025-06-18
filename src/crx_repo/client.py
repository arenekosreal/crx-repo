"""Classes and functions for downloading extensions."""

from abc import ABC
from abc import abstractmethod
from enum import Enum
from typing import final
from aiohttp import ClientError
from aiohttp import ClientSession
from asyncio import CancelledError
from asyncio import sleep
from hashlib import sha256
from logging import getLogger
from pathlib import Path
from aiofiles import open as aioopen
from pydantic import PositiveInt
from aiohttp.web import HTTPOk
from crx_repo.cache import Cache
from crx_repo.manifest import UpdateCheck


logger = getLogger(__name__)


class VersionComparationResult(Enum):
    """An Enum to represent result of version comparation."""

    LessThan = -1
    Equal = 0
    GreaterThan = 1


def _try_get_int(strings: list[str], index: int, default: int) -> int:
    if len(strings) >= index + 1:
        try:
            return int(strings[index])
        except ValueError:
            return default
    return default


def compare_version_string(a: str, b: str) -> VersionComparationResult:
    """Compare version string.

    Args:
        a(str): Version string a
        b(str): Version string b

    Returns:
        VersionComparationResult: If a is greater than b.
    """
    logger.debug("Comparing %s and %s...", a, b)
    splited_a = a.split(".")
    splited_b = b.split(".")
    max_component_count = max(len(splited_a), len(splited_b))
    for i in range(max_component_count):
        a_value = _try_get_int(splited_a, i, 0)
        b_value = _try_get_int(splited_b, i, 0)
        logger.debug("Comparing part %d and %d...", a_value, b_value)
        if a_value > b_value:
            return VersionComparationResult.GreaterThan
        if a_value < b_value:
            return VersionComparationResult.LessThan
    return VersionComparationResult.Equal


class ExtensionDownloader(ABC):
    """Abstract class for what a extension downloader should do."""

    CHUNK_SIZE_BYTES: int = 1024 * 1024  # 1MB

    @final
    def __init__(
        self,
        extension_id: str,
        chrome_version: str,
        proxy: str | None,
        cache: Cache,
    ):
        """Initialize ExtensionDownloader with arguments given.

        Args:
            extension_id(str): The id of extension.
            chrome_version(str): The value of `prodversion` in queries of request.
            proxy(str | None): The proxy to send requests. None means no proxy.
            cache(Cache): The Cache implementation.
        """
        self._extension_id: str = extension_id
        self._chrome_version: str = chrome_version
        self._proxy: str | None = proxy
        self.__cache: Cache = cache
        if self._proxy is not None:
            logger.debug(
                "Use proxy %s to download extension %s.",
                self._proxy,
                self._extension_id,
            )

    async def __download(
        self,
        url: str,
        path: Path,
        session: ClientSession,
        size: int | None = None,
        sha256_checksum: str | None = None,
    ):
        async with session.get(url, proxy=self._proxy) as response:
            if response.status != HTTPOk.status_code:
                logger.error(
                    "Failed to download extension because server returns %d",
                    response.status,
                )
                return
            check_size = response.content_length is not None or size is not None
            if check_size and response.content_length != size:
                logger.warning(
                    "Content-Length(%s) is not equal to size obtained from server(%s).",
                    response.content_length,
                    size,
                )
            hash_calculator = sha256()
            temp_crx = path.with_name(path.name + ".part")
            temp_crx.parent.mkdir(exist_ok=True, parents=True)
            async with aioopen(temp_crx, "wb") as writer:
                try:
                    async for chunk in response.content.iter_chunked(
                        self.CHUNK_SIZE_BYTES,
                    ):
                        chunk_size = await writer.write(chunk)
                        hash_calculator.update(chunk)
                        logger.debug("Writing %d byte(s) into %s...", chunk_size, path)
                except (TimeoutError, ClientError):
                    logger.exception("Failed to download %s.", self._extension_id)
            if sha256_checksum is not None:
                logger.debug("Checking sha256 of downloaded file...")
                actual_sha256_checksum = hash_calculator.hexdigest()
                if sha256_checksum != actual_sha256_checksum:
                    logger.error("Checksum of %s mismatch.", self._extension_id)
                    logger.error("Wants: %s", sha256_checksum)
                    logger.error("Actual: %s", actual_sha256_checksum)
                    logger.error("Removing downloaded file...")
                    temp_crx.unlink()
                    return
                logger.debug("Checksum of %s match.", self._extension_id)
            else:
                logger.warning("No sha256 checksum is provided, skip checking...")
            _ = temp_crx.replace(path)

    async def download_forever(self, interval: PositiveInt):
        """Download extensions forever if it is needed to do."""
        try:
            while True:
                async with ClientSession() as session:
                    extension_files = sorted(
                        self.__cache.extension_files(self._extension_id),
                        key=lambda p: p.stat().st_mtime,
                    )

                    update = await self._check_updates(
                        extension_files[-1].stem if len(extension_files) > 0 else None,
                        session,
                    )
                    if update is not None:
                        logger.info(
                            "Downloading extension %s with version %s...",
                            self._extension_id,
                            update.version,
                        )
                        path = self.__cache.extension_path(
                            self._extension_id,
                            update.version,
                        )
                        await self.__download(
                            update.codebase,
                            path,
                            session,
                            update.size,
                            update.hash_sha256,
                        )
                await sleep(interval)
        except (CancelledError, KeyboardInterrupt):
            logger.debug(
                "Exitting downloader for extension %s...",
                self._extension_id,
            )

    @abstractmethod
    async def _check_updates(
        self,
        latest_version: str | None,
        session: ClientSession,
    ) -> UpdateCheck | None: ...
