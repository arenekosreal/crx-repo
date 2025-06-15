"""Classes to deserialize config."""

from typing import Literal
from typing import ClassVar
from pathlib import Path
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import PositiveInt
from pydantic.alias_generators import to_snake


type LogLevelType = Literal["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class TlsHttpListenConfig(BaseModel):
    """HTTPS config."""

    cert: Path = Path("crx-repo.crt")
    key: str | None = None
    model_config: ClassVar[ConfigDict] = ConfigDict(alias_generator=to_snake)


class UnixListenConfig(BaseModel):
    """Unix domain socket config."""

    path: Path = Path("/run/crx-repo/crx-repo.socket")
    permission: int = 666
    tls: TlsHttpListenConfig | None = None
    model_config: ClassVar[ConfigDict] = ConfigDict(alias_generator=to_snake)


class TcpListenConfig(BaseModel):
    """TCP config."""

    address: str = "127.0.0.1"
    port: PositiveInt = 8888
    tls: TlsHttpListenConfig | None = None
    model_config: ClassVar[ConfigDict] = ConfigDict(alias_generator=to_snake)


class ListenConfig(BaseModel):
    """Listen config."""

    tcp: TcpListenConfig | None = None
    unix: UnixListenConfig | None = None
    model_config: ClassVar[ConfigDict] = ConfigDict(alias_generator=to_snake)


class Config(BaseModel):
    """Main runtime config."""

    log_level: LogLevelType = "INFO"
    manifest_path: str = "/updates.xml"
    prefix: str = "/crx-repo"
    base: str = "http://localhost:8888"
    proxy: str | None = None
    version: str = "128.0"
    interval: PositiveInt = 10800
    extensions: list[str] = []
    cache_dir: str = "cache"
    listen: ListenConfig = ListenConfig()
    model_config: ClassVar[ConfigDict] = ConfigDict(alias_generator=to_snake)


__all__ = ["Config"]
