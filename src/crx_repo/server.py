"""Classes and functions to distribute manifest and crx files."""

import asyncio
import hashlib
import logging
from ssl import Purpose
from ssl import SSLContext
from ssl import create_default_context
from typing import Any
from aiohttp import web
from asyncio import Task
from asyncio import CancelledError
from asyncio import create_task
from pathlib import Path
from urllib.parse import unquote
from collections.abc import Generator
from crx_repo.client import ExtensionDownloader
from xml.etree.ElementTree import Element
from xml.etree.ElementTree import indent
from xml.etree.ElementTree import tostring
from crx_repo.config.config import Config
from crx_repo.config.config import TlsHttpListenConfig


_logger = logging.getLogger(__name__)


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
    _logger.debug("Handling query param.")
    for x in xs:
        x_unquoted = unquote(x)
        params = _parse_params(x_unquoted)
        crx = params.get("id")
        version = params.get("v")
        if crx is not None and version is not None:
            filters.append((crx, version))
    return filters


async def _block():
    sleep_seconds = 3600
    while True:
        try:
            await asyncio.sleep(sleep_seconds)
        except CancelledError:
            _logger.info("Exiting...")
            return


def _get_crx_info(
    cache_path: Path,
    filters: list[tuple[str, str]],
) -> Generator[tuple[str, tuple[str, int, str]], Any, None]:
    if len(filters) > 0:
        for crx, version in filters:
            path = cache_path / crx / (version + ".crx")
            if path.is_file():
                content = path.read_bytes()
                info = (version, len(content), hashlib.sha256(content).hexdigest())
                yield crx, info
    else:
        for path in cache_path.glob("./*/*.crx"):
            crx = path.parent.name
            version = path.name.removesuffix(".crx")
            content = path.read_bytes()
            info = (version, len(content), hashlib.sha256(content).hexdigest())
            yield crx, info


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

    async def register_services(app: web.Application):
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

    app.cleanup_ctx.append(register_services)

    prefix = config.prefix if config.prefix.startswith("/") else "/" + config.prefix
    manifest_path = config.manifest_path if config.manifest_path.startswith("/") else \
        "/" + config.manifest_path

    async def _handle_manifest(request: web.Request) -> web.Response:
        absolute_base = config.base + prefix + "/"
        root = Element("gupdate")
        root.attrib["xmlns"] = "http://www.google.com/update2/response"
        root.attrib["protocol"] = "2.0"
        xs = request.query.getall("x") if "x" in request.query else []
        filters = _get_filters(xs)

        for crx, info in _get_crx_info(cache_path, filters):
            app = root.find("./app[@appid='%s']".format())
            if app is None:
                app = Element("app")
                app.attrib["appid"] = crx
                root.append(app)
            version, size, sha256 = info
            update_check = Element("updatecheck")
            update_check.attrib["codebase"] = absolute_base + crx + "/" + version + ".crx"
            update_check.attrib["version"] = version
            update_check.attrib["size"] = str(size)
            update_check.attrib["hash_sha256"] = sha256
            app.append(update_check)
        indent(root)
        xml: bytes = tostring(root, encoding="utf-8", xml_declaration=True)
        return web.Response(
            body=xml + "\n".encode("utf-8"),
            content_type="application/xml",
            charset="utf-8"
        )

    _ = app.router.add_static(prefix, cache_path, name="crx-handler")
    _ = app.router.add_get(manifest_path, _handle_manifest, name="manifest-handler")
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
