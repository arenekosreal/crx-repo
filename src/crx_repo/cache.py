"""Update extension info automatically when its file changes."""

from abc import ABC
from abc import abstractmethod
from json import dumps
from json import loads
from typing import final
from typing import override
from asyncio import TaskGroup
from asyncio import to_thread
from hashlib import sha256
from logging import getLogger
from pathlib import Path
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from aiohttp.web import Request
from aiohttp.web import Response
from aiohttp.web import HTTPNotFound
from aiohttp.web import UrlDispatcher
from aiohttp.web import HTTPBadRequest

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
    def __init__(
        self,
        cache: Path,
        router: UrlDispatcher,
        prefix: str,
        router_name: str,
    ):
        """Initialize Cache with cache path.

        Args:
            cache(Path): The path of cache.
            router(UrlDispatcher): The router to set handler for extension files.
            prefix(str): The prefix of request path.
            router_name(str): The name of router.
        """

    @abstractmethod
    @asynccontextmanager
    def new_extension_async(
        self,
        extension_id: str,
        extension_version: str,
        data: dict[str, MetadataSupportedType | None],
    ) -> AsyncGenerator[Path]:
        """Prepare storaging a new extension.

        Args:
            extension_id(str): The id of extension.
            extension_version(str): The version of extension.
            data(dict[MetadataSupportedType | None]): The metadata of extension.

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
        extension_id: str | None = None,
        extension_version: str | None = None,
    ) -> GUpdate:
        """Get GUpdate object from cached extensions.

        Args:
            base(str): The `scheme://host:port` part of codebase in UpdateCheck.
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
    def __init__(
        self,
        cache: Path,
        router: UrlDispatcher,
        prefix: str,
        router_name: str,
    ):
        self.__path = cache
        if self.__path.exists() and not self.__path.is_dir():
            logger.warning("Removing %s to create cache directory...", self.__path)
            self.__path.unlink()
        self.__path.mkdir(parents=True, exist_ok=True)
        self.__extensions = router.add_get(
            prefix + "/{ext_id}/{ext_ver}.crx",
            self.__handle_request_async,
            name=router_name,
        )

    async def __handle_request_async(self, request: Request) -> Response:
        ext_id = request.match_info.get("ext_id")
        ext_ver = request.match_info.get("ext_ver")
        if ext_id is not None and ext_ver is not None:
            physical_path = self.__path / ext_id / (ext_ver + ".crx")
            if physical_path.is_file():
                return Response(
                    body=await to_thread(physical_path.read_bytes),
                    # See https://developer.chrome.com/docs/extensions/how-to/distribute/host-on-linux#hosting
                    # for how chrome think an extension is installable.
                    content_type="application/x-chrome-extension",
                )
            raise HTTPNotFound(reason="No such file found in repo.")
        raise HTTPBadRequest(reason="Extension version and id are required.")

    def __metadata_path(self, extension_id: str, extension_version: str) -> Path:
        return self.__path / extension_id / (extension_version + ".meta.json")

    def __read_metadata[T: MetadataSupportedType](
        self,
        extension_id: str,
        extension_version: str,
        key: str,
        t: type[T],
    ) -> T | None:
        data = loads(self.__metadata_path(extension_id, extension_version).read_text())  # pyright: ignore[reportAny]
        if isinstance(data, dict):
            value = data.get(key)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if isinstance(value, t):
                return value
        return None

    def __write_metadata(
        self,
        extension_id: str,
        extension_version: str,
        data: dict[str, MetadataSupportedType],
    ):
        _ = self.__metadata_path(extension_id, extension_version).write_text(
            dumps(data, sort_keys=True, indent=4),
        )

    @override
    @asynccontextmanager
    async def new_extension_async(
        self,
        extension_id: str,
        extension_version: str,
        data: dict[str, MetadataSupportedType | None],
    ) -> AsyncGenerator[Path]:
        extension_path = self.__path / extension_id / (extension_version + ".crx")
        await to_thread(extension_path.parent.mkdir, parents=True, exist_ok=True)
        yield extension_path
        if (
            await to_thread(extension_path.is_file)
            and (await to_thread(extension_path.stat)).st_size > 0
        ):
            await to_thread(
                self.__write_metadata,
                extension_id,
                extension_version,
                {k: v for k, v in data.items() if v is not None},
            )

    @override
    async def get_gupdate_async(
        self,
        base: str,
        extension_id: str | None = None,
        extension_version: str | None = None,
    ) -> GUpdate:
        gupdate = GUpdate(apps=[], protocol="2.0")

        def on_each_extension(extension: Path):
            cur_ext_id = extension.parent.stem
            cur_ext_ver = extension.stem
            if extension_id is not None and cur_ext_id != extension_id:
                return
            if (
                extension_version is not None
                and compare_version_string(cur_ext_ver, extension_version)
                == VersionComparationResult.LessThan
            ):
                return
            codebase = f"{base}{self.__extensions.url_for(ext_id=cur_ext_id, ext_ver=cur_ext_ver)}"
            hash_sha256 = sha256(extension.read_bytes()).hexdigest()
            size = extension.stat().st_size
            prodversionmin = self.__read_metadata(
                cur_ext_id,
                cur_ext_ver,
                "prodversionmin",
                str,
            )
            updatecheck = UpdateCheck(
                codebase=codebase,
                hash_sha256=hash_sha256,
                size=size,
                version=cur_ext_ver,
                prodversionmin=prodversionmin,
            )
            app = gupdate.get_extension(cur_ext_id)
            if app is None:
                app = App(appid=cur_ext_id, status="ok", updatechecks=[updatecheck])
                gupdate.apps.append(app)
            elif updatecheck not in app.updatechecks:
                app.updatechecks.append(updatecheck)

        async with TaskGroup() as tg:
            tasks = [
                tg.create_task(to_thread(on_each_extension, extension))
                for extension in self.__path.glob("./*/*.crx")
            ]
        logger.debug("Waiting for %d tasks...", len(tasks))
        return gupdate
