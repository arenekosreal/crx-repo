"""Models for a manifest for api requesting.

Example:
    manifest is omitted for clarity.
    ```xml
    <gupdate xmlns="http://www.google.com/update2/response" protocol="2.0">
        <app appid="" status="ok">
            <updatecheck codebase="" hash_sha256="" size="" version=""/>
        </app>
    </gupdate>
    ```
"""

from typing import Literal
from functools import cmp_to_key

from pydantic_xml import BaseXmlModel
from pydantic_xml import attr
from pydantic_xml import element

from crx_repo.utils import compare_version_string


CHROME_MANIFEST_XML_NAMESPACE = "http://www.google.com/update2/response"

type ResponseStatus = Literal["ok"]
type ProtocolVersion = Literal["2.0"]


class UpdateCheck(
    BaseXmlModel,
    nsmap={"": CHROME_MANIFEST_XML_NAMESPACE},
    tag="updatecheck",
    search_mode="ordered",
):
    """The model of <updatecheck> element."""

    codebase: str = attr()
    hash_sha256: str | None = attr(default=None)
    size: int | None = attr(default=None)
    version: str = attr()
    prodversionmin: str | None = attr(default=None)


class App(
    BaseXmlModel,
    nsmap={"": CHROME_MANIFEST_XML_NAMESPACE},
    tag="app",
    search_mode="ordered",
):
    """The model of <app> element."""

    appid: str = attr()
    status: ResponseStatus = attr()
    updatechecks: list[UpdateCheck] = element(tag="updatecheck")

    @property
    def latest_version(self) -> str | None:
        """Get latest extension version."""
        sort = sorted(
            self.updatechecks,
            key=cmp_to_key(
                lambda a, b: compare_version_string(a.version, b.version).value,
            ),
        )
        return sort[-1].version if len(sort) > 0 else None


class GUpdate(
    BaseXmlModel,
    nsmap={"": CHROME_MANIFEST_XML_NAMESPACE},
    tag="gupdate",
    search_mode="ordered",
):
    """The model of <gupdate> element."""

    apps: list[App] = element(tag="app")
    protocol: ProtocolVersion = attr()

    def get_extension(self, extension_id: str) -> App | None:
        """Get the extension App by extension id.

        Args:
            extension_id(str): The id of extension.

        Returns:
            App | None: The extension App, None if not found.
        """
        return next(filter(lambda app: app.appid == extension_id, self.apps), None)
