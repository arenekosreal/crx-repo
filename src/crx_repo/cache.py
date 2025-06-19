"""Update extension info automatically when its file changes."""

from abc import ABC
from abc import abstractmethod
from typing import final
from typing import override
from asyncio import Event
from asyncio import CancelledError
from hashlib import sha256
from logging import getLogger
from pathlib import Path
from collections.abc import Iterator

from aiofiles import open as aioopen
from watchfiles import Change
from watchfiles import awatch  # pyright: ignore[reportUnknownVariableType]
from aiohttp.web import Application


logger = getLogger(__name__)


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
    def extension_path(self, extension_id: str, extension_version: str) -> Path:
        """Get extension path by its id and version.

        Args:
            extension_id(str): The id of extension.
            extension_version(str): The version of extension.

        Returns:
            Path: The path of extension file.
        """

    @abstractmethod
    def extension_size(self, extension_id: str, extension_version: str) -> int:
        """Get extension size by its id and version.

        Args:
            extension_id(str): The id of extension
            extension_version(str): The version of extension

        Returns:
            int: The size of file. 0 if not found.
        """

    @abstractmethod
    async def extension_sha256_async(
        self,
        extension_id: str,
        extension_version: str,
    ) -> str:
        """Get extension sha256 checksum asynchronously by its id and version.

        Args:
            extension_id(str): The id of extension.
            extension_version(str): The version of extension.

        Returns:
            str: The sha256 checksum of file. Empty string if not found.
        """

    @abstractmethod
    async def watch(self, stop_event: Event):
        """Watch cache changes and update cache automatically.

        Args:
            stop_event(Event): The `asyncio.Event` to stop watching.

        Notes:
            This will block forever until `asyncio.CancelledError` raised.
            This error usually raised by `asyncio.Task.cancel()` method.
        """

    @abstractmethod
    def iter_extensions(
        self,
        extension_id: str | None = None,
        extension_version: str | None = None,
    ) -> Iterator[tuple[str, str]]:
        """Iter extensions in cache.

        Args:
            extension_id(str | None): The extension_id to filter, defaults to None.
            extension_version(str | None): The extension version to filter, defaults to None.

        Returns:
            Iterator[tuple[str, str]]: An iterator of a tuple.

            Each tuple contains extension id and extension version in string.

        Example:
            ```python
            cache: Cache
            for extension_id, extension_version in cache.iter_extensions():
                ...
            ```
        """

    @abstractmethod
    def extension_files(self, extension_id: str) -> Iterator[Path]:
        """Iter extension files in cache.

        Args:
            extension_id(str): The id of extension.

        Returns:
            Iterator[Path]: An iterator of Path.

            Each Path is the file of extension.

        Example:
            ```python
            cache: Cache
            for path in cache.iter_extensions("example-extension-id"):
                ...
            ```
        """

    @abstractmethod
    def extension_codebase(
        self, base: str, prefix: str, extension_id: str, extension_version: str,
    ) -> str:
        """Get codebase address of extension.

        Args:
            base(str): The host:port of final url.
            prefix(str): The extra part after base of final url.
            extension_id(str): The id of extension.
            extension_version(str): The version of extension.

        Returns:
            str: The final url.
        """


@final
class MemoryCache(Cache):
    """A cache storage data in memory."""

    @override
    def __init__(self, cache: Path, app: Application, prefix: str, router_name: str):
        self.path = cache
        if self.path.exists() and not self.path.is_dir():
            logger.warning("Removing %s to create cache directory...", self.path)
            self.path.unlink()
        self.path.mkdir(parents=True, exist_ok=True)
        # extension_id, extension_version
        self.extension_infos: set[tuple[str, str]] = set()
        for extension_path in self.path.glob("./*/*.crx"):
            self.extension_infos.add((extension_path.parent.stem, extension_path.stem))
            logger.debug("Adding extension %s to cache...", extension_path)
        _ = app.router.add_static(prefix, self.path, name=router_name)

    @override
    def extension_path(self, extension_id: str, extension_version: str) -> Path:
        return self.path / extension_id / (extension_version + ".crx")

    @override
    def extension_size(self, extension_id: str, extension_version: str) -> int:
        path = self.extension_path(extension_id, extension_version)
        return path.stat().st_size if path.exists() else 0

    @override
    async def extension_sha256_async(
        self,
        extension_id: str,
        extension_version: str,
    ) -> str:
        path = self.extension_path(extension_id, extension_version)
        if not path.exists():
            return ""
        async with aioopen(path, "rb") as reader:
            return sha256(await reader.read()).hexdigest()

    @override
    async def watch(self, stop_event: Event):
        try:
            async for changes in awatch(
                self.path,
                watch_filter=lambda change, path: change != Change.modified
                and path.endswith(".crx"),
                stop_event=stop_event,
            ):
                for change, path_str in changes:
                    path = Path(path_str)
                    extension_info = path.parent.stem, path.stem
                    match change:
                        case Change.added:
                            self.extension_infos.add(extension_info)
                        case Change.deleted:
                            for filtered_extension_info in filter(
                                lambda info: info == extension_info,
                                self.extension_infos,
                            ):
                                self.extension_infos.remove(filtered_extension_info)
                        case _:
                            pass
        except CancelledError:
            pass
        logger.debug("Stopping watcher...")

    @override
    def iter_extensions(
        self,
        extension_id: str | None = None,
        extension_version: str | None = None,
    ) -> Iterator[tuple[str, str]]:
        for extension_info in self.extension_infos:
            if extension_id is not None:
                extension_id_match = extension_id == extension_info[0]
            else:
                extension_id_match = True
            if extension_version is not None:
                extension_version_match = extension_version == extension_info[1]
            else:
                extension_version_match = True
            if extension_id_match and extension_version_match:
                yield extension_info

    @override
    def extension_files(self, extension_id: str) -> Iterator[Path]:
        return (self.path / extension_id).glob("*.crx")

    @override
    def extension_codebase(
        self, base: str, prefix: str, extension_id: str, extension_version: str,
    ) -> str:
        return f"{base}{prefix}/{extension_id}/{extension_version}.crx"
