"""Classes and functions to distribute manifest and crx files."""

# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportAny=false

import asyncio
import hashlib
import logging
from ssl import Purpose
from ssl import SSLContext
from ssl import create_default_context
from typing import Any
from typing import Callable
from typing import NamedTuple
from aiohttp import web
from asyncio import Task
from asyncio import CancelledError
from asyncio import create_task
from pathlib import Path
from watchfiles import Change
from watchfiles import awatch
from urllib.parse import unquote
from collections.abc import Iterator
from collections.abc import Coroutine
from collections.abc import AsyncIterator
from crx_repo.client import ExtensionDownloader
from xml.etree.ElementTree import Element
from xml.etree.ElementTree import indent
from xml.etree.ElementTree import tostring
from crx_repo.config.config import Config
from crx_repo.config.config import TlsHttpListenConfig


class ExtensionInfo(NamedTuple):
    """A named tuple stores metainfo for an .crx file."""
    extension_id: str
    version: str
    size: int
    hash_sha256: str


_logger = logging.getLogger(__name__)
_cache: set[ExtensionInfo] = set()


def _iter_extension_info(
    target_extension_id: str | None = None,
    target_extension_version: str | None = None,
) -> Iterator[ExtensionInfo]:
    for info in _cache:
        if target_extension_id is not None:
            extension_id_match = info.extension_id == target_extension_id
        else:
            extension_id_match = True

        if target_extension_version is not None:
            extension_version_match = info.version == target_extension_version
        else:
            extension_version_match = True

        if extension_id_match and extension_version_match:
            yield info


def _get_ssl_context(tls: TlsHttpListenConfig | None) -> SSLContext | None:
    if tls is not None:
        context = create_default_context(Purpose.CLIENT_AUTH)
        context.load_cert_chain(tls.cert, tls.key)
        return context
    return None


def _parse_params(params: str) -> dict[str, str | None]:
    equal = "="
    ampersand = "&"
    kv_required_min_size = 2
    result: dict[str, str | None] = {}
    for param in params.split(ampersand):
        splited = param.split(equal, 1)
        if len(splited) < kv_required_min_size:
            result[splited[0]] = None
        else:
            result[splited[0]] = splited[1]
    return result


def _get_filters(xs: list[str]) -> list[tuple[str, str]]:
    filters: list[tuple[str, str]] = []
    _logger.debug("Handling query param %s.", xs)
    for x in xs:
        x_unquoted = unquote(x)
        params = _parse_params(x_unquoted)
        crx = params.get("id")
        version = params.get("v")
        if crx is not None and version is not None:
            filters.append((crx, version))
    return filters


def _watch_filter(change: Change, path: str) -> bool:
    return change != Change.modified and path.endswith(".crx")


async def _watch_cache(cache: Path):
    try:
        async for changes in awatch(cache, watch_filter=_watch_filter):
            for (change, path) in changes:
                _logger.debug("Updating cache for path %s", path)
                p = Path(path)
                extension_version = p.stem
                extension_id = p.parent.stem
                match change:
                    case Change.added:
                        info = ExtensionInfo(
                            extension_id,
                            extension_version,
                            p.stat().st_size,
                            hashlib.sha256(p.read_bytes()).hexdigest()
                        )
                        _cache.add(info)
                    case Change.deleted:
                        for info in _iter_extension_info(extension_id, extension_version):
                            _cache.remove(info)
                    case _:
                        pass
    except CancelledError:
        _logger.info("Stopping watcher...")


async def _block():
    sleep_seconds = 3600
    while True:
        try:
            await asyncio.sleep(sleep_seconds)
        except CancelledError:
            _logger.info("Exiting...")
            return


def _gen_cache(cache: Path):
    for path in cache.glob("./*/*.crx"):
        extension_version = path.stem
        extension_id = path.parent.stem
        extension_size = path.stat().st_size
        extension_hash_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        _cache.add(
            ExtensionInfo(
                extension_id,
                extension_version,
                extension_size,
                extension_hash_sha256,
            )
        )


def _get_cleanup_ctx_callback(
    config: Config,
    cache_path: Path,
    watcher_key: web.AppKey[Task[None]],
    extension_keys: list[web.AppKey[Task[None]]]
) -> Callable[[web.Application], AsyncIterator[None]]:
    async def callback(app: web.Application):
        _gen_cache(cache_path)

        app[watcher_key] = create_task(_watch_cache(cache_path))

        for extension_key in extension_keys:
            extension_id = config.extensions[extension_keys.index(extension_key)]
            downloader = ExtensionDownloader(
                extension_id,
                config.interval,
                config.version,
                cache_path,
                config.proxy
            )
            app[extension_key] = create_task(downloader.download_forever())

        yield

        for extension_key in extension_keys:
            _ = app[extension_key].cancel()
            await app[extension_key]

        _ = app[watcher_key].cancel()
        await app[watcher_key]

        _cache.clear()
    return callback


def _get_handler(
    config: Config,
    prefix: str
) -> Callable[[web.Request], Coroutine[Any, Any, web.Response]]:
    async def handler(request: web.Request) -> web.Response:
        absolute_base = config.base + prefix + "/"
        root = Element("gupdate")
        root.attrib["xmlns"] = "http://www.google.com/update2/response"
        root.attrib["protocol"] = "2.0"
        xs = request.query.getall("x") if "x" in request.query else []
        filters = _get_filters(xs)
        infos: list[ExtensionInfo] = []
        if len(filters) > 0:
            for extension_id, extension_version in filters:
                for info in _iter_extension_info(extension_id, extension_version):
                    infos.append(info)
        else:
            for info in _iter_extension_info():
                infos.append(info)

        for info in infos:
            extension_path = info.extension_id + "/" + info.version + ".crx"
            app = root.find("./app[@appid='{}']".format(info.extension_id))
            if app is None:
                app = Element("app")
                app.attrib["appid"] = info.extension_id
                root.append(app)
            update_check = Element("updatecheck")
            update_check.attrib["codebase"] = absolute_base + extension_path
            update_check.attrib["version"] = info.version
            update_check.attrib["status"] = "ok"
            update_check.attrib["size"] = str(info.size)
            update_check.attrib["hash_sha256"] = info.hash_sha256
            app.append(update_check)
        indent(root)
        xml: bytes = tostring(root, encoding="utf-8", xml_declaration=True)
        return web.Response(
            body=xml + "\n".encode("utf-8"),
            content_type="application/xml",
            charset="utf-8"
        )
    return handler


def setup_server(
    config: Config,
    debug: bool = False,
) -> web.Application:
    """Get WebApplication instance from config."""
    cache_path = Path(config.cache_dir)

    app = web.Application(
        logger=_logger,
        debug=debug,
    )

    extension_keys: list[web.AppKey[Task[None]]] = []
    for extension in config.extensions:
        extension_key = web.AppKey(extension, Task[None])
        extension_keys.append(extension_key)

    watcher_key = web.AppKey("cache-watcher", Task[None])

    callback = _get_cleanup_ctx_callback(config, cache_path, watcher_key, extension_keys)

    app.cleanup_ctx.append(callback)

    prefix = config.prefix if config.prefix.startswith("/") else "/" + config.prefix
    manifest_path = config.manifest_path if config.manifest_path.startswith("/") else \
        "/" + config.manifest_path

    handler = _get_handler(config, prefix)

    if not cache_path.is_dir():
        if cache_path.exists():
            _logger.debug("Removing %s to create directory.", cache_path)
            cache_path.unlink()
        cache_path.mkdir(parents=True)
    _ = app.router.add_static(prefix, cache_path, name="crx-handler")
    _ = app.router.add_get(manifest_path, handler, name="manifest-handler")
    return app


async def run_app(
    app: web.Application,
    tcp: tuple[str | None, int | None, TlsHttpListenConfig | None],
    unix: tuple[str | None, TlsHttpListenConfig | None],
):
    """Run the WebApplication and block forever."""
    host, port, tls_tcp = tcp
    path, tls_unix = unix
    runner = web.AppRunner(app)
    await runner.setup()
    sites: list[web.BaseSite] = []
    if host is not None and port is not None:
        site = web.TCPSite(runner, host, port, ssl_context=_get_ssl_context(tls_tcp))
        _logger.info(
            "Listening on %s://%s:%s",
            "https" if tls_tcp is not None else "http",
            host,
            port
        )
        sites.append(site)
    if path is not None:
        site = web.UnixSite(runner, path, ssl_context=_get_ssl_context(tls_unix))
        _logger.info(
            "Listening on unix+%s://%s",
            "https" if tls_unix is not None else "http",
            path,
        )
        sites.append(site)

    if len(sites) == 0:
        raise RuntimeError("Cannot start listening.")
    _ = await asyncio.gather(*(site.start() for site in sites))

    await _block()
    await runner.cleanup()
