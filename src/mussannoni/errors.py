"""Exceptions raised by the public API.

Every error the caller can provoke is one of these, so an application can catch
``MussaNnoniError`` and know it is looking at a problem with its own request rather than a bug
in the renderer.
"""

from __future__ import annotations


class MussaNnoniError(Exception):
    """Base class for every error this package raises deliberately."""


class UnknownReportError(MussaNnoniError, KeyError):
    """The requested report key (or level/key pair) is not in the registry."""

    def __str__(self) -> str:  # KeyError would otherwise repr() the message
        return self.args[0] if self.args else ""


class UnknownEngineError(MussaNnoniError, ValueError):
    """The requested rendering engine is not registered."""


class EngineUnavailableError(MussaNnoniError, RuntimeError):
    """The requested engine is registered but cannot run on this machine."""


class InvalidDocumentError(MussaNnoniError, ValueError):
    """A geometry document is missing a key the template requires, or has the wrong shape."""


class InvalidDataError(MussaNnoniError, ValueError):
    """Report data supplied to the table API does not match the report's layout."""


class RenderError(MussaNnoniError, RuntimeError):
    """An engine ran but did not produce a usable PDF."""
