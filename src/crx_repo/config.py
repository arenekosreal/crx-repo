"""Classes and functions to parse config files."""

from abc import ABC
from abc import abstractmethod
from ssl import Purpose
from ssl import SSLContext
from ssl import create_default_context
from typing import Any
from typing import Literal
from typing import ClassVar
from typing import TypeGuard
from pathlib import Path

from pydantic import Field
from pydantic import BaseModel as PyDanticBaseModel
from pydantic import ConfigDict
from pydantic import PositiveInt
from pydantic import ValidationError
from pydantic import ValidatorFunctionWrapHandler
from pydantic import field_validator
from aiohttp.web import UrlDispatcher
from pydantic.alias_generators import to_snake

from crx_repo.cache import Cache
from crx_repo.cache import MemoryCache
from crx_repo.chrome import ChromeExtensionDownloader
from crx_repo.client import DownloaderCustomArg
from crx_repo.client import ExtensionDownloader


type LogLevelType = Literal["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
type ExtensionProvider = Literal["chrome"]


def _to_kebab(string: str) -> str:
    return to_snake(string).replace("_", "-")


def _are_all[T](collection: list[Any], t: type[T]) -> TypeGuard[list[T]]:  # pyright: ignore[reportExplicitAny]
    return all(isinstance(item, t) for item in collection)  # pyright: ignore[reportAny]


class BaseModel(PyDanticBaseModel):
    """A base class which defines models of config files."""

    model_config: ClassVar[ConfigDict] = ConfigDict(alias_generator=_to_kebab)


class TlsHttpListenConfig(BaseModel):
    """HTTPS config."""

    cert: Path = Path("crx-repo.crt")
    key: Path | None = None
    password: str | None = None

    @property
    def ssl_context(self) -> SSLContext:
        """The ssl context of current HTTPS config."""
        context = create_default_context(Purpose.CLIENT_AUTH)
        context.load_cert_chain(self.cert, self.key, self.password)
        return context


class UnixListenConfig(BaseModel):
    """Unix domain socket config."""

    path: Path = Path("/run/crx-repo/crx-repo.socket")
    permission: int = 666
    tls: TlsHttpListenConfig | None = None


class TcpListenConfig(BaseModel):
    """TCP config."""

    address: str = "127.0.0.1"
    port: PositiveInt = 8888
    tls: TlsHttpListenConfig | None = None


class NotNoneRequiredError(ValueError):
    """Exception raised when two items cannot be None either."""

    def __init__(self, name1: str, name2: str):
        """Initialize NotNoneRequired object with arguments given.

        Args:
            name1(str): The first item's name.
            name2(str): The second item's name.
        """
        msg = f"You need to specify at least one of {name1}, {name2}."
        super().__init__(msg)


class ListenConfig(BaseModel):
    """Listen config."""

    tcp: TcpListenConfig | None = None
    unix: UnixListenConfig | None = None

    @field_validator("tcp")
    @classmethod
    def _tcp_is_not_none(
        cls,
        value: TcpListenConfig | None,
    ) -> TcpListenConfig | None:
        if value is None and cls.unix is None:
            first = "tcp"
            second = "unix"
            raise NotNoneRequiredError(first, second)
        return value

    @field_validator("unix")
    @classmethod
    def _unix_is_not_none(
        cls,
        value: UnixListenConfig | None,
    ) -> UnixListenConfig | None:
        if value is None and cls.tcp is None:
            first = "tcp"
            second = "unix"
            raise NotNoneRequiredError(first, second)
        return value


class Extension(BaseModel):
    """Extension config."""

    extension_id: str = Field(max_length=32, min_length=32)
    extension_provider: ExtensionProvider = "chrome"
    proxy: str | None = None
    interval: PositiveInt | None = None
    custom_args: DownloaderCustomArg = Field(default_factory=dict)

    def get_downloader(
        self,
        custom_args: dict[ExtensionProvider, DownloaderCustomArg],
        interval: PositiveInt,
        proxy: str | None,
        cache: Cache,
    ) -> ExtensionDownloader:
        """Get downloader by extension config.

        Args:
            custom_args(dict[ExtensionProvider, DownloaderCustomArg]): Custom arguments in main cfg.
            interval(PositiveInt): The interval of ExtensionDownloader from main config.
            proxy(str | None): The proxy of ExtensionDownloader from main config.
            cache(Cache): The cache of ExtensionDownloader.

        Returns:
            ExtensionDownloader: An ExtensionDownloader implementation based on extension_provider.
        """
        match self.extension_provider:
            case "chrome":
                custom_args_updated = custom_args.get(self.extension_provider, {})
                custom_args_updated.update(self.custom_args)
                return ChromeExtensionDownloader(
                    self.extension_id,
                    custom_args_updated,
                    self.interval or interval,
                    self.proxy or proxy,
                    cache,
                )


class Config(BaseModel):
    """Main runtime config."""

    log_level: LogLevelType = "INFO"
    manifest_path: str = "/updates.xml"
    prefix: str = "/crx-repo"
    base: str = "http://localhost:8888"
    proxy: str | None = None
    interval: PositiveInt = 10800
    extensions: list[Extension] = []
    cache_dir: Path = Path("cache")
    listen: ListenConfig = ListenConfig()
    custom_args: dict[ExtensionProvider, DownloaderCustomArg] = Field(
        default_factory=dict,
    )

    @field_validator("extensions", mode="wrap")
    @classmethod
    def _convert_legacy_extensions(
        cls,
        value: Any,  # noqa: ANN401 # pyright: ignore[reportExplicitAny, reportAny]
        handler: ValidatorFunctionWrapHandler,
    ) -> list[Extension]:
        try:
            return handler(value)  # pyright: ignore[reportAny]
        except ValidationError:
            if isinstance(value, list) and _are_all(value, str):  # pyright: ignore[reportUnknownArgumentType]
                return [Extension.model_validate({"extension-id": i}) for i in value]
            raise

    def get_cache(
        self,
        path: Path,
        router: UrlDispatcher,
        prefix: str,
        router_name: str,
    ) -> Cache:
        """Get cache by config.

        Args:
            path(Path): The path to cache.
            router(UrlDispatcher): The router to register extensions.
            prefix(str): The extra part before url path.
            router_name(str): The name of resource registered in router.
        """
        return MemoryCache(path, router, prefix, router_name)


class ConfigParser(ABC):
    """Abstract class for what a config parser should do."""

    @abstractmethod
    async def parse_async(self, config: Path) -> Config | None:
        """Parse the config asynchronously.

        Args:
            config(Path): The path of config file.

        Returns:
            Config | None: Deserialized config. None means failed to parse.
        """
