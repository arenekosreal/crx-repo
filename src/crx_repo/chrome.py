"""Download extensions from Chrome Web Store."""

from typing import final
from typing import override
from .client import ExtensionDownloader
from .client import VersionComparationResult
from .client import compare_version_string
from aiohttp import ClientError
from aiohttp import ClientSession
from asyncio import TimeoutError as AsyncTimeoutError
from logging import getLogger
from pydantic import ValidationError
from .manifest import GUpdate
from .manifest import UpdateCheck
from aiohttp.web import HTTPOk
from urllib.parse import urlencode


logger = getLogger(__name__)


@final
class ChromeExtensionDownloader(ExtensionDownloader):
    """An ExtensionDownloader implementation downloads extensions from Chrome Web Store."""

    CHROME_WEB_STORE_API_BASE = "https://clients2.google.com/service/update2/crx"

    @override
    async def _check_updates(
        self,
        latest_version: str | None,
        session: ClientSession,
    ) -> UpdateCheck | None:
        x = {"id": self._extension_id}
        params = {
            "response": "updatecheck",
            "acceptformat": "crx2,crx3",
            "prodversion": self._chrome_version,
            "x": urlencode(x) + "&uc",  # No `updatecheck` without `&uc`
        }
        async with session.get(
            self.CHROME_WEB_STORE_API_BASE,
            params=params,
            proxy=self._proxy,
        ) as response:
            logger.debug("Sending url %s...", response.url)
            if response.status != HTTPOk.status_code:
                logger.error(
                    "Failed to check extension update because server returns %d.",
                    response.status,
                )
                return None
            try:
                text = await response.read()
            except (ClientError, AsyncTimeoutError) as ce:
                logger.error("Failed to get response text because %s.", ce)
                return None
        logger.debug("Parsing XML response:")
        logger.debug("%s", text)
        try:
            gupdate = GUpdate.from_xml(text)
        except ValidationError as ve:
            logger.error("Failed to deserialize response because %s.", ve.json())
            return None
        logger.debug("Parsed XML response:")
        logger.debug("%s", gupdate.model_dump_json())
        if latest_version is not None:
            for app in filter(
                lambda app: app.appid == self._extension_id, gupdate.apps
            ):
                for updatecheck in app.updatechecks:
                    if (
                        compare_version_string(updatecheck.version, latest_version)
                        == VersionComparationResult.GreaterThan
                    ):
                        logger.debug(
                            "Updating %s from %s to %s...",
                            self._extension_id,
                            latest_version,
                            updatecheck.version,
                        )
                        return updatecheck
        else:
            app = next(
                filter(lambda app: app.appid == self._extension_id, gupdate.apps),
                None,
            )
            return (
                app.updatechecks[0]
                if app is not None and len(app.updatechecks) > 0
                else None
            )
        return None
