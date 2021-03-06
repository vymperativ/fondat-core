"""Module to support encoding and decoding of values."""

from __future__ import annotations

import base64
import binascii
import csv
import decimal
import functools
import io
import json
import keyword
import wrapt

from collections.abc import Iterable, Mapping, Set
from dataclasses import dataclass, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from fondat.types import NoneType, affix_type_hints
from fondat.validation import validate, validate_arguments
from typing import Annotated, Any, Generic, Literal, TypeVar, TypedDict, Union
from typing import get_origin, get_args, get_type_hints
from uuid import UUID


providers = []


_TEXT_PLAIN = "text/plain; charset=UTF-8"


# tracks types being built to deal with recursion (cyclic graphs)
_building = {}


def _issubclass(cls, cls_or_tuple):
    try:
        return issubclass(cls, cls_or_tuple)
    except:
        return False


def _provider(wrapped=None):
    if wrapped is None:
        return functools.partial(provider)
    providers.append(wrapped)
    return wrapped


# ----- base -----


F = TypeVar("F")
T = TypeVar("T")


class Codec(Generic[F, T]):
    """Base class for all things encode and decode."""

    def encode(self, value: F) -> T:
        """Encode value from F type to T type."""
        raise NotImplementedError

    def decode(self, value: T) -> F:
        """Decode value from T type to F type."""
        raise NotImplementedError


class String(Codec[F, str]):
    """
    Encodes Python types to/from Unicode string objects.
    """


class Binary(Codec[F, Union[bytes, bytearray]]):
    """
    Encodes Python types to/from binary objects.

    Attribute:
    • content_type: string containing the media type of the binary object representation.
    """


class JSON(Codec[F, Any]):
    """
    Encodes Python types to/from the JSON object model.

    The JSON object model is strictly composed of the following types:
    dict, list, str, int, float, bool, NoneType.

    Attribute:
    • json_type: the JSON object model type encoded/decoded by the codec.
    """


# ----- str -----


@affix_type_hints
class _Str_Binary(Binary[str]):
    """Bytes codec for Unicode character strings."""

    content_type = _TEXT_PLAIN

    @validate_arguments
    def encode(self, value: str) -> bytes:
        return value.encode()

    @validate_arguments
    def decode(self, value: Union[bytes, bytearray]) -> str:
        return value.decode()


_str_binarycodec = _Str_Binary()


@affix_type_hints
class _Str_String(String[str]):
    """String codec for Unicode character strings."""

    @validate_arguments
    def encode(self, value: str) -> str:
        return value

    @validate_arguments
    def decode(self, value: str) -> str:
        return value


_str_stringcodec = _Str_String()


@affix_type_hints
class _Str_JSON(JSON[str]):
    """JSON codec for Unicode character strings."""

    json_type = str

    @validate_arguments
    def encode(self, value: str) -> str:
        return value

    @validate_arguments
    def decode(self, value: str) -> str:
        return value


_str_jsoncodec = _Str_JSON()


@_provider
def _str(codec_type, python_type):
    if _issubclass(python_type, str):
        if codec_type is Binary:
            return _str_binarycodec
        if codec_type is String:
            return _str_stringcodec
        if codec_type is JSON:
            return _str_jsoncodec


# ----- bytes/bytearray -----


@affix_type_hints
class _Bytes_Binary(Binary[Union[bytes, bytearray]]):
    """Binary codec for byte sequences."""

    content_type = "application/octet-stream"

    @validate_arguments
    def encode(self, value: Union[bytes, bytearray]) -> Union[bytes, bytearray]:
        return value

    @validate_arguments
    def decode(self, value: Union[bytes, bytearray]) -> Union[bytes, bytearray]:
        return value


_bytes_binarycodec = _Bytes_Binary()


@affix_type_hints
class _Bytes_String(String[Union[bytes, bytearray]]):
    """
    String codec for byte sequences. A byte sequence is represented in string
    values as a base64-encoded string. Example: "SGVsbG8gRm9uZGF0".
    """

    @validate_arguments
    def encode(self, value: Union[bytes, bytearray]) -> str:
        return base64.b64encode(value).decode()

    @validate_arguments
    def decode(self, value: str) -> bytes:
        try:
            return base64.b64decode(value)
        except binascii.Error:
            raise ValueError("expecting a base64-encoded value")


_bytes_stringcodec = _Bytes_String()


@affix_type_hints
class _Bytes_JSON(JSON[Union[bytes, bytearray]]):
    """
    JSON codec for byte sequences. A byte sequence is represented in JSON
    values as a base64-encoded string. Example: "SGVsbG8gRm9uZGF0".
    """

    json_type = str

    @validate_arguments
    def encode(self, value: Union[bytes, bytearray]) -> str:
        return _bytes_stringcodec.encode(value)

    @validate_arguments
    def decode(self, value: str) -> bytes:
        return _bytes_stringcodec.decode(value)


_bytes_jsoncodec = _Bytes_JSON()


@_provider
def _bytes(codec_type, python_type):
    if _issubclass(python_type, (bytes, bytearray)):
        if codec_type is Binary:
            return _bytes_binarycodec
        if codec_type is String:
            return _bytes_stringcodec
        if codec_type is JSON:
            return _bytes_jsoncodec


# ----- int -----


@affix_type_hints
class _Int_String(String[int]):
    """String codec for integers."""

    @validate_arguments
    def encode(self, value: int) -> str:
        return str(value)

    @validate_arguments
    def decode(self, value: str) -> int:
        try:
            return int(value)
        except:
            raise ValueError(f"{value} is not a valid integer")


_int_stringcodec = _Int_String()


@affix_type_hints
class _Int_Binary(Binary[int]):
    """Binary codec for integers."""

    content_type = _TEXT_PLAIN

    @validate_arguments
    def encode(self, value: int) -> bytes:
        return _int_stringcodec.encode(value).encode()

    @validate_arguments
    def decode(self, value: Union[bytes, bytearray]) -> int:
        return _int_stringcodec.decode(value.decode())


_int_binarycodec = _Int_Binary()


@affix_type_hints
class _Int_JSON(JSON[int]):
    """JSON codec for integers."""

    json_type = Union[int, float]

    @validate_arguments
    def encode(self, value: int) -> int:
        return value

    @validate_arguments
    def decode(self, value: Union[int, float]) -> int:
        result = value
        if isinstance(result, float):
            result = int(result)
            if result != value:  # 1.0 == 1
                raise TypeError("expecting integer")
        return result


_int_jsoncodec = _Int_JSON()


@_provider
def _int(codec_type, python_type):
    if _issubclass(python_type, int) and not _issubclass(python_type, bool):
        if codec_type is Binary:
            return _int_binarycodec
        if codec_type is String:
            return _int_stringcodec
        if codec_type is JSON:
            return _int_jsoncodec


# ----- float -----


@affix_type_hints
class _Float_String(String[float]):
    """String codec for floating point numbers."""

    @validate_arguments
    def encode(self, value: float) -> str:
        return str(value)

    @validate_arguments
    def decode(self, value: str) -> float:
        try:
            return float(value)
        except:
            raise ValueError(f"{value} is not a valid floating point number")


_float_stringcodec = _Float_String()


@affix_type_hints
class _Float_Binary(Binary[float]):
    """Binary codec for floating point numbers."""

    content_type = _TEXT_PLAIN

    @validate_arguments
    def encode(self, value: float) -> bytes:
        return _float_stringcodec.encode(value).encode()

    @validate_arguments
    def decode(self, value: Union[bytes, bytearray]) -> float:
        return _float_stringcodec.decode(value.decode())


_float_binarycodec = _Float_Binary()


@affix_type_hints
class _Float_JSON(JSON[float]):
    """JSON codec for floating point numbers."""

    json_type = Union[int, float]

    @validate_arguments
    def encode(self, value: float) -> float:
        return value

    @validate_arguments
    def decode(self, value: Union[int, float]) -> float:
        return float(value)


_float_jsoncodec = _Float_JSON()


@_provider
def _float(codec_type, python_type):
    if _issubclass(python_type, float):
        if codec_type is Binary:
            return _float_binarycodec
        if codec_type is String:
            return _float_stringcodec
        if codec_type is JSON:
            return _float_jsoncodec


# ----- bool -----


@affix_type_hints
class _Bool_String(String[bool]):
    """String codec for boolean values."""

    @validate_arguments
    def encode(self, value: bool) -> str:
        return "true" if value else "false"

    @validate_arguments
    def decode(self, value: str) -> bool:
        try:
            return {"true": True, "false": False}[value]
        except KeyError:
            raise ValueError(f"{value} must be true or false")


_bool_stringcodec = _Bool_String()


@affix_type_hints
class _Bool_Binary(Binary[bool]):
    """Binary codec for boolean values."""

    content_type = _TEXT_PLAIN

    @validate_arguments
    def encode(self, value: bool) -> bytes:
        return _bool_stringcodec.encode(value).encode()

    @validate_arguments
    def decode(self, value: Union[bytes, bytearray]) -> bool:
        return _bool_stringcodec.decode(value.decode())


_bool_binarycodec = _Bool_Binary()


@affix_type_hints
class _Bool_JSON(JSON[bool]):
    """JSON codec for boolean values."""

    json_type = bool

    @validate_arguments
    def encode(self, value: bool) -> bool:
        return value

    @validate_arguments
    def decode(self, value: bool) -> bool:
        return value


_bool_jsoncodec = _Bool_JSON()


@_provider
def _bool(codec_type, python_type):
    if _issubclass(python_type, bool):
        if codec_type is Binary:
            return _bool_binarycodec
        if codec_type is String:
            return _bool_stringcodec
        if codec_type is JSON:
            return _bool_jsoncodec


# ----- NoneType -----


@affix_type_hints
class _NoneType_String(String[NoneType]):
    """String codec for None value."""

    @validate_arguments
    def encode(self, value: NoneType) -> str:
        return ""

    @validate_arguments
    def decode(self, value: str) -> NoneType:
        if str != "":
            raise ValueError("expecting empty string")
        return None


_nonetype_stringcodec = _NoneType_String()


@affix_type_hints
class _NoneType_Binary(Binary[NoneType]):
    """Binary codec for None value."""

    content_type = _TEXT_PLAIN

    @validate_arguments
    def encode(self, value: NoneType) -> bytes:
        return b""

    @validate_arguments
    def decode(self, value: Union[bytes, bytearray]) -> NoneType:
        if value != b"":
            raise ValueError("expecting empty byte sequence")
        return None


_nonetype_binarycodec = _NoneType_Binary()


@affix_type_hints
class _NoneType_JSON(JSON[NoneType]):
    """JSON codec for None value."""

    json_type = NoneType

    @validate_arguments
    def encode(self, value: NoneType) -> NoneType:
        return value

    @validate_arguments
    def decode(self, value: NoneType) -> NoneType:
        return value


_nonetype_jsoncodec = _NoneType_JSON()


@_provider
def _NoneType(codec_type, python_type):

    if python_type is NoneType:
        if codec_type is Binary:
            return _nonetype_binarycodec
        if codec_type is String:
            return _nonetype_stringcodec
        if codec_type is JSON:
            return _nonetype_jsoncodec


# ----- Decimal -----


@affix_type_hints
class _Decimal_String(String[Decimal]):
    """String codec for Decimal numbers."""

    @validate_arguments
    def encode(self, value: Decimal) -> str:
        return str(value)

    @validate_arguments
    def decode(self, value: str) -> Decimal:
        try:
            return Decimal(value)
        except decimal.InvalidOperation:
            raise ValueError(f"{value} is not a valid decimal number")


_decimal_string = _Decimal_String()


@affix_type_hints
class _Decimal_Binary(Binary[Decimal]):
    """Binary codec for Decimal numbers."""

    content_type = _TEXT_PLAIN

    @validate_arguments
    def encode(self, value: Decimal) -> bytes:
        return _decimal_string.encode(value).encode()

    @validate_arguments
    def decode(self, value: Union[bytes, bytearray]) -> Decimal:
        return _decimal_string.decode(value.decode())


_decimal_binary = _Decimal_Binary()


@affix_type_hints
class _Decimal_JSON(JSON[Decimal]):
    """
    JSON codec for Decimal numbers. Decimal numbers are represented in JSON as
    strings, due to the imprecision of floating point numbers.
    """

    json_type = str

    @validate_arguments
    def encode(self, value: Decimal) -> str:
        return _decimal_string.encode(value)

    @validate_arguments
    def decode(self, value: str) -> Decimal:
        return _decimal_string.decode(value)


_decimal_json = _Decimal_JSON()


@_provider
def _Decimal(codec_type, python_type):
    if _issubclass(python_type, Decimal):
        if codec_type is Binary:
            return _decimal_binary
        if codec_type is String:
            return _decimal_string
        if codec_type is JSON:
            return _decimal_json


# ----- date -----


@affix_type_hints
class _Date_String(String[date]):
    """
    String codec for dates. A date is represented in a string in RFC 3339
    format. Example: "2018-06-16".
    """

    @validate_arguments
    def encode(self, value: date) -> str:
        return value.isoformat()

    @validate_arguments
    def decode(self, value: str) -> date:
        try:
            return date.fromisoformat(value)
        except:
            raise ValueError(f"{value} is not a valid date")


_date_stringcodec = _Date_String()


@affix_type_hints
class _Date_Binary(Binary[date]):
    """
    Binary codec for dates. A date is represented in a binary format as an
    RFC 3339 UTF-8 encoded string. Example: "2018-06-16".
    """

    content_type = _TEXT_PLAIN

    @validate_arguments
    def encode(self, value: date) -> bytes:
        return _date_stringcodec.encode(value).encode()

    @validate_arguments
    def decode(self, value: Union[bytes, bytearray]) -> date:
        return _date_stringcodec.decode(value.decode())


_date_binarycodec = _Date_Binary()


@affix_type_hints
class _Date_JSON(JSON[date]):
    """
    JSON codec for dates. A date is represented in JSON as an RFC 3339
    formatted string. Example: "2018-06-16".
    """

    json_type = str

    @validate_arguments
    def encode(self, value: date) -> str:
        return _date_stringcodec.encode(value)

    @validate_arguments
    def decode(self, value: str) -> date:
        return _date_stringcodec.decode(value)


_date_jsoncodec = _Date_JSON()


@_provider
def _date(codec_type, python_type):
    if _issubclass(python_type, date) and not _issubclass(python_type, datetime):
        if codec_type is Binary:
            return _date_binarycodec
        if codec_type is String:
            return _date_stringcodec
        if codec_type is JSON:
            return _date_jsoncodec


# ----- datetime -----


def _to_utc(value):
    if value.tzinfo is None:  # naive value interpreted as UTC
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@affix_type_hints
class _Datetime_String(String[datetime]):
    """
    String codec for datetime. A datetime is represented in a string in
    RFC 3339 format. Example: "2018-06-16T12:34:56.789012Z".
    """

    @validate_arguments
    def encode(self, value: datetime) -> str:
        result = _to_utc(value).isoformat()
        if result.endswith("+00:00"):
            result = result[0:-6]
        if "+" not in result and not result.endswith("Z"):
            result = f"{result}Z"
        return result

    @validate_arguments
    def decode(self, value: str) -> datetime:
        if value.endswith("Z"):
            value = value[0:-1]
        try:
            return _to_utc(datetime.fromisoformat(value))
        except:
            raise ValueError(f"{value} is not a valid datetime")


_datetime_stringcodec = _Datetime_String()


@affix_type_hints
class _Datetime_Binary(Binary[datetime]):
    """
    Binary codec for datetimes. A datetime is represented in a binary format as
    an RFC 3339 UTF-8 encoded string. Example: "2018-06-16T12:34:56.789012Z".
    """

    content_type = _TEXT_PLAIN

    @validate_arguments
    def encode(self, value: datetime) -> bytes:
        return _datetime_stringcodec.encode(value).encode()

    @validate_arguments
    def decode(self, value: Union[bytes, bytearray]) -> datetime:
        return _datetime_stringcodec.decode(value.decode())


_datetime_binarycodec = _Datetime_Binary()


@affix_type_hints
class _Datetime_JSON(JSON[datetime]):
    """
    JSON codec for datetimes. A datetime is represented in JSON as an RFC 3339
    formatted string. Example: "2018-06-16T12:34:56.789012Z".
    """

    json_type = str

    @validate_arguments
    def encode(self, value: datetime) -> str:
        return _datetime_stringcodec.encode(value)

    @validate_arguments
    def decode(self, value: str) -> datetime:
        return _datetime_stringcodec.decode(value)


_datetime_jsoncodec = _Datetime_JSON()


@_provider
def _datetime(codec_type, python_type):
    if _issubclass(python_type, datetime):
        if codec_type is Binary:
            return _datetime_binarycodec
        if codec_type is String:
            return _datetime_stringcodec
        if codec_type is JSON:
            return _datetime_jsoncodec


# ----- UUID -----


@affix_type_hints
class _UUID_String(String[UUID]):
    """String codec for UUID."""

    @validate_arguments
    def encode(self, value: UUID) -> str:
        return str(value)

    @validate_arguments
    def decode(self, value: str) -> UUID:
        try:
            return UUID(value)
        except Exception as e:
            raise ValueError(f"{value} is not a valid UUID value")


_uuid_stringcodec = _UUID_String()


@affix_type_hints
class _UUID_Binary(Binary[UUID]):
    """Binary codec for UUID."""

    content_type = _TEXT_PLAIN

    @validate_arguments
    def encode(self, value: UUID) -> bytes:
        return _uuid_stringcodec.encode(value).encode()

    @validate_arguments
    def decode(self, value: Union[bytes, bytearray]) -> UUID:
        return _uuid_stringcodec.decode(value.decode())


_uuid_binarycodec = _UUID_Binary()


@affix_type_hints
class _UUID_JSON(JSON[UUID]):
    """JSON codec for UUID."""

    json_type = str

    @validate_arguments
    def encode(self, value: UUID) -> str:
        return _uuid_stringcodec.encode(value)

    @validate_arguments
    def decode(self, value: str) -> UUID:
        return _uuid_stringcodec.decode(value)


_uuid_jsoncodec = _UUID_JSON()


@_provider
def _uuid(codec_type, python_type):
    if _issubclass(python_type, UUID):
        if codec_type is Binary:
            return _uuid_binarycodec
        if codec_type is String:
            return _uuid_stringcodec
        if codec_type is JSON:
            return _uuid_jsoncodec


# ----- TypedDict -----


@_provider
def _typeddict(codec_type, python_type):

    if (
        not _issubclass(python_type, dict)
        or getattr(python_type, "__annotations__", None) is None
    ):
        return  # not a TypedDict

    if codec_type is JSON:

        if c := _building.get((codec_type, python_type)):
            return c  # return the (incomplete) outer one still being built

        hints = get_type_hints(python_type, include_extras=False)

        for key in hints:
            if type(key) is not str:
                raise TypeError("codec only supports TypedDict with str keys")

        @affix_type_hints(localns=locals())
        class _TypedDict_JSON(JSON[python_type]):

            json_type = dict[str, Any]  # will be replaced below

            def _process(self, value, method):
                result = {}
                for key in hints:
                    codec = get_codec(JSON, hints[key])
                    try:
                        result[key] = getattr(codec, method)(value[key])
                    except KeyError:
                        continue
                return result

            @validate_arguments
            def encode(self, value: python_type) -> Any:
                return self._process(value, "encode")

            def decode(self, value: Any) -> python_type:
                validate(value, self.json_type)
                return self._process(value, "decode")

        result = _TypedDict_JSON()
        _building[(codec_type, python_type)] = result

        try:
            json_type = TypedDict(
                "_TypedDict",
                {key: get_codec(JSON, hints[key]).json_type for key in hints},
                total=python_type.__total__,
            )
            json_type.__required_keys__ = python_type.__required_keys__
            json_type.__optional_keys__ = python_type.__optional_keys__
            result.json_type = result.__class__.json_type = json_type

        finally:
            del _building[(codec_type, python_type)]

        return result

    if codec_type is String:
        json_codec = get_codec(JSON, python_type)

        @affix_type_hints(localns=locals())
        class _TypedDict_String(String[python_type]):
            @validate_arguments
            def encode(self, value: python_type) -> str:
                return json.dumps(json_codec.encode(value))

            @validate_arguments
            def decode(self, value: str) -> python_type:
                return json_codec.decode(json.loads(value))

        return _TypedDict_String()

    if codec_type is Binary:
        string_codec = get_codec(String, python_type)

        @affix_type_hints(localns=locals())
        class _TypedDict_Binary(Binary[python_type]):
            content_type = "application/json"

            @validate_arguments
            def encode(self, value: python_type) -> bytes:
                return string_codec.encode(value).encode()

            @validate_arguments
            def decode(self, value: Union[bytes, bytearray]) -> python_type:
                return string_codec.decode(value.decode())

        return _TypedDict_Binary()


# ----- Mapping -----


@_provider
def _mapping(codec_type, python_type):

    origin = get_origin(python_type)

    if (
        not _issubclass(origin, Mapping)
        or getattr(python_type, "__annotations__", None) is not None
    ):
        return  # not a Mapping

    args = get_args(python_type)
    if len(args) != 2:
        raise TypeError("expecting Mapping[KT, VT]")

    if codec_type is JSON:
        key_codec = get_codec(String, args[0])
        value_codec = get_codec(JSON, args[1])
        _json_type = dict[str, value_codec.json_type]

        @affix_type_hints(localns=locals())
        class _Mapping_JSON(JSON[python_type]):
            json_type = _json_type

            @validate_arguments
            def encode(self, value: python_type) -> _json_type:
                return {key_codec.encode(k): value_codec.encode(v) for k, v in value.items()}

            @validate_arguments
            def decode(self, value: _json_type) -> python_type:
                return python_type(
                    {key_codec.decode(k): value_codec.decode(v) for k, v in value.items()}
                )

        return _Mapping_JSON()

    if codec_type is String:
        json_codec = get_codec(JSON, python_type)

        @affix_type_hints(localns=locals())
        class _Mapping_String(String[python_type]):
            @validate_arguments
            def encode(self, value: python_type) -> str:
                return json.dumps(json_codec.encode(value))

            @validate_arguments
            def decode(self, value: str) -> python_type:
                return json_codec.decode(json.loads(value))

        return _Mapping_String()

    if codec_type is Binary:

        string_codec = get_codec(String, python_type)

        @affix_type_hints(localns=locals())
        class _Mapping_Binary(Binary[python_type]):

            content_type = "application/json"

            @validate_arguments
            def encode(self, value: python_type) -> bytes:
                return string_codec.encode(value).encode()

            @validate_arguments
            def decode(self, value: Union[bytes, bytearray]) -> python_type:
                return string_codec.decode(value.decode())

        return _Mapping_Binary()


# ----- Iterable -----


def _csv_encode(value):
    sio = io.StringIO()
    csv.writer(sio).writerow(value)
    return sio.getvalue().rstrip("\r\n")


def _csv_decode(value):
    return csv.reader([value]).__next__()


@_provider
def _iterable(codec_type, python_type):

    origin = get_origin(python_type)

    if (
        not _issubclass(origin, Iterable)
        or _issubclass(python_type, (str, bytes, bytearray))
        or _issubclass(origin, Mapping)
    ):
        return

    args = get_args(python_type)

    if len(args) != 1:
        raise TypeError("expecting Iterable[T]")

    item_type = args[0]
    is_set = issubclass(origin, Set)

    if codec_type is JSON:

        item_codec = get_codec(JSON, item_type)
        _json_type = list[item_codec.json_type]

        @affix_type_hints(localns=locals())
        class _Iterable_JSON(JSON[python_type]):

            json_type = _json_type

            @validate_arguments
            def encode(self, value: python_type) -> _json_type:
                if is_set:
                    value = sorted(value)
                return [item_codec.encode(item) for item in value]

            @validate_arguments
            def decode(self, value: _json_type) -> python_type:
                return python_type((item_codec.decode(item) for item in value))

        return _Iterable_JSON()

    if codec_type is String:

        item_codec = get_codec(String, item_type)

        @affix_type_hints(localns=locals())
        class _Iterable_String(String[python_type]):
            @validate_arguments
            def encode(self, value: python_type) -> str:
                if is_set:
                    value = sorted(value)
                return _csv_encode((item_codec.encode(item) for item in value))

            @validate_arguments
            def decode(self, value: str) -> python_type:
                return python_type((item_codec.decode(item) for item in _csv_decode(value)))

        return _Iterable_String()

    if codec_type is Binary:

        string_codec = get_codec(String, python_type)

        @affix_type_hints(localns=locals())
        class _Iterable_Binary(Binary[python_type]):
            content_type = _TEXT_PLAIN

            @validate_arguments
            def encode(self, value: python_type) -> bytes:
                return string_codec.encode(value).encode()

            @validate_arguments
            def decode(self, value: Union[bytes, bytearray]) -> python_type:
                return string_codec.decode(value.decode())

        return _Iterable_Binary()


# ----- dataclass -----


# keywords have _ suffix in dataclass fields (e.g. "in_", "for_", ...)
_dc_kw = {k + "_": k for k in keyword.kwlist}


@_provider
def _dataclass(codec_type, python_type):

    if not is_dataclass(python_type):
        return

    if codec_type is JSON:

        def dict_key(key):
            if key.endswith("_"):
                truncated = key[:-1]
                if keyword.iskeyword(trunc):
                    return truncated
            return key

        if c := _building.get((codec_type, python_type)):
            return c  # return the (incomplete) outer one still being built

        hints = get_type_hints(python_type, include_extras=False)

        noneables = {
            name
            for name, hint in hints.items()
            if get_origin(hint) is Union
            and NoneType in get_args(hint)
            and getattr(python_type, name, None) is None
        }

        @affix_type_hints(localns=locals())
        class _Dataclass_JSON(JSON[python_type]):

            json_type = dict[str, Any]  # will be replaced below

            @validate_arguments
            def encode(self, value: python_type) -> Any:
                result = {}
                for key in hints:
                    v = getattr(value, key)
                    if v is not None:
                        result[_dc_kw.get(key, key)] = get_codec(JSON, hints[key]).encode(v)
                return result

            def decode(self, value: Any) -> python_type:
                validate(value, self.json_type)
                kwargs = {}
                for key in hints:
                    codec = get_codec(JSON, hints[key])
                    try:
                        kwargs[key] = codec.decode(value[_dc_kw.get(key, key)])
                    except KeyError:
                        if key in noneables:
                            kwargs[key] = None
                return python_type(**kwargs)

        result = _Dataclass_JSON()
        _building[(codec_type, python_type)] = result

        try:
            json_type = TypedDict(
                "_TypedDict",
                {key: get_codec(JSON, hints[key]).json_type for key in hints},
                total=False,
            )

            # workaround for https://bugs.python.org/issue42059
            json_type.__required_keys__ = frozenset()
            json_type.__optional_keys__ = frozenset(hints)

            result.json_type = result.__class__.json_type = json_type

        finally:
            del _building[(codec_type, python_type)]

        return result

    if codec_type is String:

        json_codec = get_codec(JSON, python_type)

        @affix_type_hints(localns=locals())
        class _Dataclass_String(String[python_type]):
            @validate_arguments
            def encode(self, value: python_type) -> str:
                return json.dumps(json_codec.encode(value))

            @validate_arguments
            def decode(self, value: str) -> python_type:
                return json_codec.decode(json.loads(value))

        return _Dataclass_String()

    if codec_type is Binary:

        string_codec = get_codec(String, python_type)

        @affix_type_hints(localns=locals())
        class _Dataclass_Binary(Binary[python_type]):

            content_type = "application/json"

            @validate_arguments
            def encode(self, value: python_type) -> bytes:
                return string_codec.encode(value).encode()

            @validate_arguments
            def decode(self, value: Union[bytes, bytearray]) -> python_type:
                return string_codec.decode(value.decode())

        return _Dataclass_Binary()


# ----- Union -----


@_provider
def _union(codec_type, python_type):

    origin = get_origin(python_type)

    if origin is not Union:
        return

    types = get_args(python_type)

    def process(codecs, method, value):
        for codec in codecs:
            try:
                return getattr(codec, method)(value)
            except (TypeError, ValueError) as e:
                continue
        raise ValueError

    if codec_type is String:

        codecs = tuple(get_codec(String, t) for t in types)

        @affix_type_hints(localns=locals())
        class _Union_String(String[python_type]):
            @validate_arguments
            def encode(self, value: python_type) -> str:
                return process(codecs, "encode", value)

            @validate_arguments
            def decode(self, value: str) -> python_type:
                return process(codecs, "decode", value)

        return _Union_String()

    if codec_type is Binary:

        codecs = tuple(get_codec(Binary, t) for t in types)

        @affix_type_hints(localns=locals())
        class _Union_Binary(Binary[python_type]):

            content_type = "application/octet-stream"

            @validate_arguments
            def encode(self, value: python_type) -> bytes:
                return process(codecs, "encode", value)

            @validate_arguments
            def decode(self, value: Union[bytes, bytearray]) -> python_type:
                return process(codecs, "decode", value)

        return _Union_Binary()

    if codec_type is JSON:

        codecs = tuple(get_codec(JSON, t) for t in types)
        _json_type = Union[tuple(codec.json_type for codec in codecs)]

        @affix_type_hints(localns=locals())
        class _Union_JSON(JSON[python_type]):

            json_type = _json_type

            @validate_arguments
            def encode(self, value: python_type) -> _json_type:
                return process(codecs, "encode", value)

            @validate_arguments
            def decode(self, value: _json_type) -> python_type:
                return process(codecs, "decode", value)

        return _Union_JSON()


# ----- Literal -----


@_provider
def _literal(codec_type, python_type):

    origin = get_origin(python_type)

    if origin is not Literal:
        return

    literals = {(type(l), l) for l in get_args(python_type)}

    def decode(codecs, value):
        for codec in codecs:
            try:
                v = getattr(codec, "decode")(value)
                if (type(v), v) in literals:
                    return v
            except:
                continue
        raise ValueError

    if codec_type is String:

        codecs = tuple(get_codec(String, literal[0]) for literal in literals)

        @affix_type_hints(localns=locals())
        class _Literal_String(String[python_type]):
            @validate_arguments
            def encode(self, value: python_type) -> str:
                return get_codec(String, type(value)).encode(value)

            @validate_arguments
            def decode(self, value: str) -> python_type:
                return decode(codecs, value)

        return _Literal_String()

    if codec_type is Binary:

        codecs = tuple(get_codec(Binary, literal[0]) for literal in literals)

        @affix_type_hints(localns=locals())
        class _Literal_Binary(Binary[python_type]):

            content_type = "application/octet-stream"

            @validate_arguments
            def encode(self, value: python_type) -> bytes:
                return get_codec(Binary, type(value)).encode(value)

            @validate_arguments
            def decode(self, value: Union[bytes, bytearray]) -> python_type:
                return decode(codecs, value)

        return _Literal_Binary()

    if codec_type is JSON:

        codecs = tuple(get_codec(JSON, literal[0]) for literal in literals)
        _json_type = Union[tuple(codec.json_type for codec in codecs)]

        @affix_type_hints(localns=locals())
        class _Literal_JSON(JSON[python_type]):

            json_type = _json_type

            @validate_arguments
            def encode(self, value: python_type) -> _json_type:
                return get_codec(JSON, type(value)).encode(value)

            @validate_arguments
            def decode(self, value: _json_type) -> python_type:
                return decode(codecs, value)

        return _Literal_JSON()


# ----- Any -----


@affix_type_hints
class _Any_String(String[Any]):
    """String codec for Any."""

    @validate_arguments
    def encode(self, value: Any) -> str:
        return get_codec(String, type(value)).encode(value)

    @validate_arguments
    def decode(self, value: str) -> str:
        return value


_any_stringcodec = _Any_String()


@affix_type_hints
class _Any_Binary(Binary[Any]):
    """Binary codec for Any."""

    content_type = "application/octet-stream"

    @validate_arguments
    def encode(self, value: Any) -> bytes:
        return get_codec(Binary, type(value)).encode(value)

    @validate_arguments
    def decode(self, value: Union[bytes, bytearray]) -> Union[bytes, bytearray]:
        return value


_any_binarycodec = _Any_Binary()


@affix_type_hints
class _Any_JSON(JSON[Any]):
    """JSON codec for Any."""

    json_type = Any

    @validate_arguments
    def encode(self, value: Any) -> Any:
        return get_codec(JSON, type(value)).encode(value)

    @validate_arguments
    def decode(self, value: Any) -> Any:
        return value


_any_jsoncodec = _Any_JSON()


@_provider
def _any(codec_type, python_type):
    if python_type is Any:
        if codec_type is Binary:
            return _any_binarycodec
        if codec_type is String:
            return _any_stringcodec
        if codec_type is JSON:
            return _any_jsoncodec


@functools.cache
def get_codec(codec_type, python_type):
    """Return a codec compatible with the specified Python type."""

    if get_origin(python_type) is Annotated:
        python_type = get_args(python_type)[0]  # strip annotation

    for provider in providers:
        if (codec := provider(codec_type, python_type)) is not None:
            return codec

    raise TypeError(f"failed to provide {codec_type} for {python_type}")
