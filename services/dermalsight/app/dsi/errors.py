"""Shared sanitized exceptions for DSI internal provider boundaries."""


class ConsentNotAuthorized(ValueError):
    """The canonical identity service did not verify the requested DSI purpose."""


class DSIProviderUnavailable(RuntimeError):
    """A configured DSI internal dependency cannot safely complete the request."""
