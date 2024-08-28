"""Basic parser implementation."""

import inspect
import logging
from abc import ABC
from abc import abstractmethod
from types import UnionType
from typing import Any
from typing import Literal
from typing import TypeVar
from typing import Callable
from typing import TypeGuard
from typing import get_args
from typing import overload
from typing import get_origin
from pathlib import Path
from crx_repo.config.config import Config


PathOrStr = Path | str
T = TypeVar("T")
ConfigJsonType = dict[str, Any]
KeyConverterType = Callable[[str], str] | None

_logger = logging.getLogger(__name__)


class ConfigParser(ABC):
    """Class to parse config."""
    def __init__(self):
        """Initialize class with no parameter."""
        super().__init__()
        self._cache: dict[Path, Config] = {}

    @overload
    async def parse_async(self, path: str) -> Config:
        ...

    @overload
    async def parse_async(self, path: Path) -> Config:
        ...

    @abstractmethod
    async def parse_async(self, path: PathOrStr) -> Config:
        """Deserialize config from file at path."""

    @overload
    async def support_async(self, path: str) -> bool:
        ...

    @overload
    async def support_async(self, path: Path) -> bool:
        ...

    @abstractmethod
    async def support_async(self, path: PathOrStr) -> bool:
        """Check if path is supported by the parser."""

    @staticmethod
    def deserialize(
        cls_: type[T],
        json: ConfigJsonType,
        key_convert: KeyConverterType = None,
    ) -> T:
        """Deserialize json to a class.

        Args:
            cls_(type[T]): The class itself, it must have a no-argument constructor.
            json(ConfigJsonType): The json data.
            key_convert(KeyConverterType): A converter to convert key between json and class.
                It should accept key in json and return a string,
                    which represents the attribute name of cls_ instance.
                It defaults to None, means do not convert.

        Returns:
            T: The instance of cls_

        Remarks:
            This method is slow because using setattr() and getattr(),
                please cache its result to speed up.
        """
        instance = cls_()
        type_of_instance = inspect.get_annotations(cls_)
        for k, v in json.items():  # pyright: ignore[reportAny]
            attr_name = key_convert(k) if key_convert is not None else k
            if hasattr(instance, attr_name):
                type_of_attr = type_of_instance.get(attr_name)
                _logger.debug("Type of %s is %s", k, type_of_attr)
                if type_of_attr is None:
                    _logger.debug(
                        "%s does not have a type hint, ignoring its deserialization.",
                        attr_name,
                    )
                elif ConfigParser._is_config_json(v):  # pyright: ignore[reportAny]
                    _logger.debug("Calling deserialize() recursively.")
                    v_deserialized = ConfigParser.deserialize(  # pyright: ignore[reportUnknownVariableType]
                        ConfigParser._ensure_instanceable(type_of_attr),  # pyright: ignore[reportAny]
                        v,
                        key_convert,
                    )
                    setattr(instance, attr_name, v_deserialized)
                elif ConfigParser._is_generics_valid(
                        v,  # pyright: ignore[reportAny]
                        type_of_attr,  # pyright: ignore[reportAny]
                    ) or isinstance(v, type_of_attr):
                    _logger.debug("Type match, assigning value of %s directly.", k)
                    setattr(instance, attr_name, v)
                else:
                    _logger.debug("Do not know how to deserialize %s, ignoring.", k)
        return instance

    @staticmethod
    def _is_config_json(obj: object) -> TypeGuard[ConfigJsonType]:
        return isinstance(obj, dict) and all(isinstance(k, str) for k in obj)  # pyright: ignore[reportUnknownVariableType]

    @staticmethod
    def _is_generics_valid(v: object, t: type) -> bool:
        args = get_args(t)
        if len(args) > 0:
            origin = get_origin(t)
            if origin is Literal or origin is UnionType:
                return v in args
            if origin is list:
                return isinstance(v, list) and ConfigParser._is_list_valid(v, t)  # pyright: ignore[reportUnknownArgumentType]
            raise NotImplementedError("Unsupported type", origin)
        return False

    @staticmethod
    def _is_list_valid(v: list[T], t: type[list[T]]) -> bool:
        return (len(v) == 0) or all(isinstance(value, get_args(t)[0]) for value in v)

    @staticmethod
    def _ensure_instanceable(
        i: type,
        checker: Callable[[type], bool] = callable,
    ) -> type:
        _logger.debug("Ensuring object %s is instanceable...", i)
        if checker(i):
            return i
        if ConfigParser._is_union_type(i):
            args = get_args(i)
            matches = (arg for arg in args if checker(arg))  # pyright: ignore[reportAny]
            found = next(matches, None)
            if found is None:
                raise ValueError("No instanceable object can be extracted in UnionType")
            return found  # pyright: ignore[reportAny]
        raise NotImplementedError("Unsupported type", i)

    @staticmethod
    def _is_union_type(i: type) -> TypeGuard[UnionType]:
        args = get_args(i)
        if len(args) > 0:
            origin = get_origin(i)
            return origin is UnionType
        return False
