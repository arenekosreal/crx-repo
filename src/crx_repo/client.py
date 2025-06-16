from abc import ABC
from abc import abstractmethod
from aiohttp import ClientSession
from aiohttp import ClientError
from aiohttp.web import HTTPOk
from asyncio import TimeoutError as AsyncTimeoutError
from asyncio import sleep
from asyncio import CancelledError
from aiofiles import open as aioopen
from logging import getLogger
from pathlib import Path
from typing import override
from typing import final
from pydantic import PositiveInt
from pydantic import ValidationError
from hashlib import sha256
from urllib.parse import urlencode
from enum import Enum
from .cache import Cache
from .manifest import GUpdate
from .manifest import UpdateCheck


logger = getLogger(__name__)


class VersionComparationResult(Enum):
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


def _compare_version_string(a: str, b: str) -> VersionComparationResult:
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
    CHUNK_SIZE_BYTES: int = 1024 * 1024  # 1MB

    @final
    def __init__(
        self,
        extension_id: str,
        interval: PositiveInt,
        chrome_version: str,
        proxy: str | None,
        cache: Cache,
    ):
        self._extension_id: str = extension_id
        self.__interval: PositiveInt = interval
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
            async with aioopen(temp_crx, "wb") as writer:
                try:
                    async for chunk in response.content.iter_chunked(
                        self.CHUNK_SIZE_BYTES
                    ):
                        chunk_size = await writer.write(chunk)
                        hash_calculator.update(chunk)
                        logger.debug("Writing %d byte(s) into %s...", chunk_size, path)
                except (ClientError, AsyncTimeoutError) as ce:
                    logger.error(
                        "Failed to download %s because %s.", self._extension_id, ce
                    )
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
                else:
                    logger.debug("Checksum of %s match.", self._extension_id)
            else:
                logger.warning("No sha256 checksum is provided, skip checking...")
            _ = temp_crx.replace(path)

    async def download_forever(self):
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
                        path = self.__cache.extension_path(
                            self._extension_id, update.version
                        )
                        await self.__download(
                            update.codebase,
                            path,
                            session,
                            update.size,
                            update.hash_sha256,
                        )
                await sleep(self.__interval)
        except (CancelledError, KeyboardInterrupt):
            logger.debug(
                "Exitting downloader for extension %s...",
                self._extension_id,
            )

    @abstractmethod
    async def _check_updates(
        self, latest_version: str | None, session: ClientSession
    ) -> UpdateCheck | None: ...


@final
class ChromeExtensionDownloader(ExtensionDownloader):
    CHROME_WEB_STORE_API_BASE = "https://clients2.google.com/service/update2/crx"

    @override
    async def _check_updates(
        self,
        latest_version: str | None,
        session: ClientSession,
    ) -> UpdateCheck | None:
        x = {"id": self._extension_id}
        params = {
            "response": "updatecheck",
            "acceptformat": "crx2,crx3",
            "prodversion": self._chrome_version,
            "x": urlencode(x) + "&uc",  # No `updatecheck` without `&uc`
        }
        async with session.get(
            self.CHROME_WEB_STORE_API_BASE,
            params=params,
            proxy=self._proxy,
        ) as response:
            logger.debug("Sending url %s...", response.url)
            if response.status != HTTPOk.status_code:
                logger.error(
                    "Failed to check extension update because server returns %d.",
                    response.status,
                )
                return None
            try:
                text = await response.read()
            except (ClientError, AsyncTimeoutError) as ce:
                logger.error("Failed to get response text because %s.", ce)
                return
        logger.debug("Parsing XML response:")
        logger.debug("%s", text)
        try:
            gupdate = GUpdate.from_xml(text)
        except ValidationError as ve:
            logger.error("Failed to deserialize response because %s.", ve.json())
            return None
        logger.debug("Parsed XML response:")
        logger.debug("%s", gupdate.model_dump_json())
        if latest_version is not None:
            for app in filter(
                lambda app: app.appid == self._extension_id, gupdate.apps
            ):
                for updatecheck in app.updatechecks:
                    if (
                        _compare_version_string(updatecheck.version, latest_version)
                        == VersionComparationResult.GreaterThan
                    ):
                        logger.debug(
                            "Updating %s from %s to %s...",
                            self._extension_id,
                            latest_version,
                            updatecheck.version,
                        )
                        return updatecheck
        else:
            app = next(
                filter(lambda app: app.appid == self._extension_id, gupdate.apps),
                None,
            )
            return (
                app.updatechecks[0]
                if app is not None and len(app.updatechecks) > 0
                else None
            )
        return None
