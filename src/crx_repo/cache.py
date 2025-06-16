from typing import final
from pathlib import Path
from logging import getLogger
from aiofiles import open as aioopen  # pyright: ignore[reportMissingModuleSource]
from hashlib import sha256
from watchfiles import Change
from watchfiles import awatch  # pyright: ignore[reportUnknownVariableType]
from asyncio import CancelledError
from collections.abc import Iterator
from abc import ABC
from abc import abstractmethod
from typing import override


logger = getLogger(__name__)


class Cache(ABC):
    @abstractmethod
    def __init__(self, cache: Path): ...

    @abstractmethod
    def extension_path(self, extension_id: str, extension_version: str) -> Path: ...

    @abstractmethod
    def extension_size(self, extension_id: str, extension_version: str) -> int: ...

    @abstractmethod
    async def extension_sha256_async(
        self,
        extension_id: str,
        extension_version: str,
    ) -> str: ...

    @abstractmethod
    async def watch(self): ...

    @abstractmethod
    def iter_extensions(
        self,
        extension_id: str | None = None,
        extension_version: str | None = None,
    ) -> Iterator[tuple[str, str]]: ...

    @abstractmethod
    def extension_files(self, extension_id: str) -> Iterator[Path]: ...


@final
class MemoryCache(Cache):
    def __init__(self, cache: Path):
        self.path = cache
        self.extension_infos: set[tuple[str, str]] = set()
        for extension_path in self.path.glob("./*/*.crx"):
            self.extension_infos.add((extension_path.parent.stem, extension_path.stem))
            logger.debug("Adding extension %s to cache...", extension_path)

    @override
    def extension_path(self, extension_id: str, extension_version: str) -> Path:
        return self.path / extension_id / (extension_version + ".crx")

    @override
    def extension_size(self, extension_id: str, extension_version: str) -> int:
        return self.extension_path(extension_id, extension_version).stat().st_size

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
    async def watch(self):
        try:
            async for changes in awatch(
                self.path,
                watch_filter=lambda change, path: change != Change.modified
                and path.endswith(".crx"),
            ):
                for change, path in changes:
                    path = Path(path)
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
