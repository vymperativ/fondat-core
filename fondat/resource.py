"""
Module to implement resources.

A resource is an addressible object that exposes operations through a uniform
set of methods.


A resource class contains operation methods, each decorated with the
@operation decorator.
"""

import asyncio
import functools
import inspect
import fondat.context as context
import fondat.monitor as monitor
import fondat.schema as schema
import wrapt


class ResourceError(Exception):
    """
    Base class for resource errors.

    Parameters:
    • detail: Textual description of the error.
    • code: HTTP status associated with the error.
    """

    def __init__(self, detail=None, code=None):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        try:
            self.detail, self.code
        except AttributeError as ae:
            raise ValueError(ae)

        super().__init__(self.detail)

    def __str__(self):
        return self.detail


class BadRequest(ResourceError):
    """Raised if the request is malformed."""

    detail, code = "Bad Request", 400


class Unauthorized(ResourceError):
    """Raised if the request lacks valid authentication credentials."""

    detail, code = "Unauthorized", 401


class Forbidden(ResourceError):
    """Raised if authorization to the resource is refused."""

    detail, code = "Forbidden", 403


class NotFound(ResourceError):
    """Raised if the resource could not be found."""

    detail, code = "Not Found", 404


class OperationNotAllowed(ResourceError):
    """Raised if the resource does not allow the requested operation."""

    detail, code = "Operation Not Allowed", 405


class Conflict(ResourceError):
    """Raised if there is a conflict with the current state of the resource."""

    detail, code = "Conflict", 409


class PreconditionFailed(ResourceError):
    """Raised if the revision provided does not match the current resource."""

    detail, code = "Precondition Failed", 412


class InternalServerError(ResourceError):
    """Raised if the server encountered an unexpected condition."""

    detail, code = "Internal Server Error", 500


def _summary(function):
    """
    Derive summary information from a function's docstring or name. The summary is
    the first sentence of the docstring, ending in a period, or if no dostring is
    present, the function's name capitalized.
    """
    if not function.__doc__:
        return f"{function.__name__.capitalize()}."
    result = []
    for word in function.__doc__.split():
        result.append(word)
        if word.endswith("."):
            break
    return " ".join(result)


async def authorize(security):
    """
    Peform authorization of an operation.

    Parameters:
    • security: Iterable of security requirements.

    This coroutine executes the security requirements. If any security
    requirement does not raise an exception then this coroutine passes and
    authorization is granted.

    If one security requirement raises a Forbidden exception, then a Forbidden
    exception will be raised; otherwise an Unauthorized exception will be
    raised. If a non-security exception is raised, then it is re-raised.
    """
    exception = None
    for requirement in security or []:
        try:
            await requirement.authorize()
            return  # security requirement authorized the operation
        except Forbidden:
            exception = Forbidden
        except Unauthorized:
            if not exception:
                exception = Unauthorized
        except:
            raise
    if exception:
        raise exception


def _params(function):
    sig = inspect.signature(function)
    return schema.dict(
        props={k: v for k, v in function.__annotations__.items() if k != "return"},
        required={p.name for p in sig.parameters.values() if p.default is p.empty},
    )


class _Descriptor:
    def __init__(self, **kwargs):
        for key in kwargs:
            setattr(self, key, kwargs[key])


def resource(wrapped=None, *, tag=None):
    """
    Decorate a class to be a resource containing operations.

    Parameters:
    • tag: Tag to group resources.  [resource class name in lower case]
    """

    if wrapped is None:
        return functools.partial(resource, tag=tag)

    operations = {}
    for name in dir(wrapped):
        attr = getattr(wrapped, name)
        if operation := getattr(attr, "_fondat_operation", None):
            operations[name] = operation
    wrapped._fondat_resource = _Descriptor(
        tag=tag or wrapped.__name__.lower(), operations=operations,
    )
    return wrapped


_methods = {
    "get": "query",
    "put": "mutation",
    "post": "mutation",
    "delete": "mutation",
    "patch": "mutation",
}


def operation(
    wrapped=None, *, type=None, security=None, publish=True, deprecated=False,
):
    """
    Decorate a resource coroutine to register it as an operation.

    Parameters:
    • type: Type of operation.  {"query", "mutation", "link"}
    • security: Security requirements for the operation.
    • publish: Publish the operation in documentation.
    • deprecated: Declare the operation as deprecated.

    If method name is "get", then type shall default to "query"; if name is
    one of {"put", "post", "delete", "patch"} then type shall default to
    "mutation"; otherwise type must be specified.
    """

    if wrapped is None:
        return functools.partial(
            operation,
            type=type,
            security=security,
            publish=publish,
            deprecated=deprecated,
        )

    if not asyncio.iscoroutinefunction(wrapped):
        raise TypeError("operation must be a coroutine")

    name = wrapped.__name__
    description = wrapped.__doc__ or name
    summary = _summary(wrapped)

    _type = type or (_methods.get(name))

    if _type is None:
        raise ValueError(f"unknown operation type: {type}")
    if _type not in {"query", "mutation", "link"}:
        raise ValueError(f"invalid operation type: {type}")

    @wrapt.decorator
    async def wrapper(wrapped, instance, args, kwargs):
        operation = getattr(wrapped, "_fondat_operation")
        tags = {
            "resource": f"{instance.__class__.__module__}.{instance.__class__.__qualname__}",
            "operation": wrapped.__name__,
        }
        with context.push({"context": "fondat.operation", **tags}):
            async with monitor.timer({"name": "operation_duration_seconds", **tags}):
                async with monitor.counter({"name": "operation_calls_total", **tags}):
                    await authorize(operation.security)
                    schema.validate_arguments(wrapped, args, kwargs)
                    result = await wrapped(*args, **kwargs)
                    schema.validate_return(wrapped, result, InternalServerError)
                    return result

    wrapped._fondat_operation = _Descriptor(
        name=name,
        type=_type,
        summary=summary,
        description=description,
        security=security,
        publish=publish,
        deprecated=deprecated,
        params=_params(wrapped),
        returns=wrapped.__annotations__.get("return"),
    )

    return wrapper(wrapped)


def get_operations(resource):
    """Return dict of name-to-descriptor for resource operation methods."""
    try:
        return resource._fondat_resource.operations
    except AttributeError:
        return {}
