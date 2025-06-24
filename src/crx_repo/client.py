"""Classes and functions for downloading extensions."""

from abc import ABC
from abc import abstractmethod
from typing import final
from asyncio import CancelledError
from asyncio import sleep
from hashlib import sha256
from logging import getLogger
from pathlib import Path

from aiohttp import ClientError
from aiohttp import ClientSession
from pydantic import PositiveInt
from aiohttp.web import HTTPOk

from crx_repo.cache import Cache
from crx_repo.manifest import UpdateCheck


logger = getLogger(__name__)


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

    @final
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
            with temp_crx.open("wb") as writer:
                try:
                    async for chunk in response.content.iter_chunked(
                        self.CHUNK_SIZE_BYTES,
                    ):
                        chunk_size = writer.write(chunk)
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

    @final
    async def __check_and_download(self, base: str):
        async with ClientSession() as session:
            gupdate = await self.__cache.get_gupdate_async(
                base,
                self._extension_id,
            )
            extension = gupdate.get_extension(self._extension_id)
            update = await self._check_updates(
                extension.latest_version if extension is not None else None,
                session,
            )
            if update is not None:
                logger.info(
                    "Downloading extension %s with version %s...",
                    self._extension_id,
                    update.version,
                )
                async with self.__cache.new_extension_async(
                    self._extension_id,
                    update.version,
                    {"prodversionmin": update.prodversionmin},
                ) as path:
                    await self.__download(
                        update.codebase,
                        path,
                        session,
                        update.size,
                        update.hash_sha256,
                    )

    @final
    async def download_forever(self, interval: PositiveInt, base: str):
        """Download extensions forever if it is needed to do."""
        try:
            while True:
                await self.__check_and_download(base)
                await sleep(interval)
        except CancelledError:
            pass
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
