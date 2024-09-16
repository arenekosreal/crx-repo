"""Classes to deserialize config."""

from typing import Literal
from dataclasses import field
from dataclasses import dataclass


type LogLevelType = Literal["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


@dataclass
class TlsHttpListenConfig:
    """HTTPS config."""
    cert: str = "crx-repo.crt"
    key: str | None = None


@dataclass
class UnixListenConfig:
    """Unix domain socket config."""
    path: str = "/run/crx-repo/crx-repo.socket"
    permission: int = 666
    tls: TlsHttpListenConfig | None = None


@dataclass
class TcpListenConfig:
    """TCP config."""
    address: str = "127.0.0.1"
    port: int = 8888
    tls: TlsHttpListenConfig | None = None


@dataclass
class ListenConfig:
    """Listen config."""
    tcp: TcpListenConfig | None = None
    unix: UnixListenConfig | None = None


@dataclass
class Config:
    """Main runtime config."""
    log_level: LogLevelType = "INFO"
    manifest_path: str = "/updates.xml"
    prefix: str = "/crx-repo"
    base: str = "http://localhost:8888"
    proxy: str | None = None
    version: str = "128.0"
    interval: int = 10800
    extensions: list[str] = field(default_factory=list)
    cache_dir: str = "cache"
    listen: ListenConfig = field(default_factory=ListenConfig)


__all__ = ["Config"]
