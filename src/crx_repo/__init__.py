"""Download Chrom(e|ium) extensions from Chrome Web Store and serve a update manifest."""

import sys
import logging
from typing import Literal
from aiohttp import web
from pathlib import Path
from argparse import Namespace
from argparse import ArgumentParser


try:
    from uvloop import run as _run_async
    uvloop = True
except ImportError:
    from asyncio import run as _run_async
    uvloop = False

from crx_repo.server import run_app as _run_app
from crx_repo.server import setup_server as _setup_server
from crx_repo.config.parser import parse_config_async as _parse_config_async


__version__ = "0.1.0"


_logger = logging.getLogger(__name__)


def _setup_logger(logger: logging.Logger = _logger):
    _fmt = logging.Formatter("%(asctime)s-%(levelname)s-%(message)s", "%Y-%m-%d %H:%M:%S")
    if len(logger.handlers) == 0:
        logger.addHandler(logging.StreamHandler())
    for handler in logger.handlers:
        handler.setLevel(logger.level)
        handler.setFormatter(_fmt)


def _parse_args() -> Namespace:
    parser = ArgumentParser(
        description=sys.modules[__name__].__doc__
    )
    _ = parser.add_argument(
        "-v", "--version",
        help="Print program version.",
        action="version",
        version=__version__,
    )
    _ = parser.add_argument(
        "-c", "--config",
        help="Config file path.",
    )
    _ = parser.add_argument(
        "-l", "--log-level",
        help="Log level before config is load.",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO"
    )
    return parser.parse_args()


async def _main_async(
    config_path: str,
    log_level_in_arg: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
):
    config = await _parse_config_async(config_path)
    if log_level_in_arg != config.log_level:
        _logger.setLevel(config.log_level)
        _setup_logger()
    if config.listen.tcp is None and config.listen.unix is None:
        _logger.critical("No valid listen config found.")
        raise RuntimeError
    app = _setup_server(
        config,
        _logger.level == logging.DEBUG
    )
    tcp = config.listen.tcp
    host = tcp.address if tcp is not None else None
    port = tcp.port if tcp is not None else None
    unix = config.listen.unix
    path = unix.path if unix is not None else None
    permission = unix.permission if unix is not None else None
    tls_tcp = tcp.tls if tcp is not None else None
    tls_unix = unix.tls if unix is not None else None

    if path is not None and permission is not None:
        permission = int("0o%s".format(), base=8)

        async def set_permission(_: web.Application):
            _logger.debug("Setting permission of socket to %s", permission)
            Path(path).chmod(permission)
            yield
        app.cleanup_ctx.append(set_permission)

    await _run_app(app, (host, port, tls_tcp), (path, tls_unix))


def main():
    """Main entrance of cli."""
    args = _parse_args()
    # Temp value, may be overriden by config.
    _logger.setLevel(args.log_level)  # pyright: ignore[reportAny]
    _setup_logger()
    if uvloop:
        _logger.info("Using uvloop as async event loop.")
    _run_async(
        _main_async(
            args.config,  # pyright: ignore[reportAny]
            args.log_level  # pyright: ignore[reportAny]
        )
    )
