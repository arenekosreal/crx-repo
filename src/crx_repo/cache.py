"""Update extension info automatically when its file changes."""

from abc import ABC
from abc import abstractmethod
from json import dumps
from json import loads
from typing import final
from typing import override
from hashlib import sha256
from logging import getLogger
from pathlib import Path
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from aiofiles import open as aioopen
from aiohttp.web import Application

from crx_repo.utils import VersionComparationResult
from crx_repo.utils import compare_version_string
from crx_repo.manifest import App
from crx_repo.manifest import GUpdate
from crx_repo.manifest import UpdateCheck


logger = getLogger(__name__)


type MetadataSupportedType = int | str | bool


class Cache(ABC):
    """Abstract class for what a cache should do."""

    @abstractmethod
    def __init__(self, cache: Path, app: Application, prefix: str, router_name: str):
        """Initialize Cache with cache path.

        Args:
            cache(Path): The path of cache.
            app(Application): The server application.
            prefix(str): The prefix of request path.
            router_name(str): The name of router.
        """

    @abstractmethod
    @asynccontextmanager
    def new_extension_async(
        self,
        extension_id: str,
        extension_version: str,
        **data: MetadataSupportedType | None,
    ) -> AsyncGenerator[Path]:
        """Prepare storaging a new extension.

        Args:
            extension_id(str): The id of extension.
            extension_version(str): The version of extension.
            **data(MetadataSupportedType): The metadata of extension.

        Yields:
            Path: The path of extension.

        Example:
            ```python
                cache: Cache
                async with cache.new_extension_async("id", "version") as path:
                    ...
            ```
        """

    @abstractmethod
    async def get_gupdate_async(
        self,
        base: str,
        prefix: str,
        extension_id: str | None = None,
        extension_version: str | None = None,
    ) -> GUpdate:
        """Get GUpdate object from cached extensions.

        Args:
            base(str): The `scheme://host:port` part of codebase in UpdateCheck.
            prefix(str): The extra after base in codebase.
            extension_id(str | None): The extension_id to filter, defaults to None.
            extension_version(str | None): The extension version to filter, defaults to None.

        Returns:
            GUpdate: The generated GUpdate object.
        """


@final
class MemoryCache(Cache):
    """A cache storage metadata in memory.

    Notes:
        Extensions are storaged at `self.cache / "extension-id" / "extension-version.crx"`.
    """

    @override
    def __init__(self, cache: Path, app: Application, prefix: str, router_name: str):
        self.__path = cache
        if self.__path.exists() and not self.__path.is_dir():
            logger.warning("Removing %s to create cache directory...", self.__path)
            self.__path.unlink()
        self.__path.mkdir(parents=True, exist_ok=True)
        _ = app.router.add_static(prefix, self.__path, name=router_name)

    def __metadata_path(self, extension_id: str, extension_version: str) -> Path:
        return self.__path / extension_id / (extension_version + ".meta.json")

    async def __read_metadata(
        self,
        extension_id: str,
        extension_version: str,
    ) -> dict[str, MetadataSupportedType]:
        metadata_path = self.__metadata_path(extension_id, extension_version)
        async with aioopen(metadata_path) as reader:
            return loads(await reader.read())  # pyright: ignore[reportAny]

    async def __write_metadata(
        self,
        extension_id: str,
        extension_version: str,
        **data: MetadataSupportedType,
    ):
        metadata_path = self.__metadata_path(extension_id, extension_version)
        async with aioopen(metadata_path, "w") as writer:
            _ = await writer.write(dumps(data, sort_keys=True, indent=4))

    @override
    @asynccontextmanager
    async def new_extension_async(
        self,
        extension_id: str,
        extension_version: str,
        **data: MetadataSupportedType | None,
    ) -> AsyncGenerator[Path]:
        extension_path = self.__path / extension_id / (extension_version + ".crx")
        yield extension_path
        await self.__write_metadata(
            extension_id,
            extension_version,
            **{k: v for k, v in data.items() if v is not None},
        )

    @override
    async def get_gupdate_async(
        self,
        base: str,
        prefix: str,
        extension_id: str | None = None,
        extension_version: str | None = None,
    ) -> GUpdate:
        gupdate = GUpdate(apps=[], protocol="2.0")
        for extension in self.__path.glob("./*/*.crx"):
            cur_ext_id = extension.parent.stem
            cur_ext_ver = extension.stem
            if extension_id is not None and cur_ext_id != extension_id:
                continue
            if extension_version is not None:
                cmp_result = compare_version_string(cur_ext_ver, extension_version)
                if cmp_result == VersionComparationResult.LessThan:
                    continue
            codebase = f"{base}{prefix}/{cur_ext_id}/{cur_ext_ver}.crx"
            async with aioopen(extension, "rb") as reader:
                hash_sha256 = sha256(await reader.read()).hexdigest()
            size = extension.stat().st_size
            prodversionmin = (await self.__read_metadata(cur_ext_id, cur_ext_ver)).get(
                "prodversionmin",
            )
            if prodversionmin is not None and not isinstance(prodversionmin, str):
                prodversionmin = None
            updatecheck = UpdateCheck(
                codebase=codebase,
                hash_sha256=hash_sha256,
                size=size,
                version=cur_ext_ver,
                prodversionmin=prodversionmin,
            )
            app = next(filter(lambda app: app.appid == cur_ext_id, gupdate.apps), None)
            if app is None:
                app = App(appid=cur_ext_id, status="ok", updatechecks=[updatecheck])
                gupdate.apps.append(app)
            elif len([upd for upd in app.updatechecks if upd == updatecheck]) == 0:
                app.updatechecks.append(updatecheck)
        return gupdate
