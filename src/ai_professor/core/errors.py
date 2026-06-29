"""Integrity-core exceptions.

These name violations of the project's load-bearing invariants so they surface loudly rather
than silently corrupting state.
"""

from __future__ import annotations


class IntegrityError(Exception):
    """Base class for violations of a core integrity invariant."""


class CurriculumImmutableError(IntegrityError):
    """Raised when attempting to overwrite an existing curriculum version with new content.

    The curriculum is immutable per version (DESIGN.md §7): to change it, publish a new version.
    """

    def __init__(self, version: str) -> None:
        super().__init__(
            f"curriculum version {version!r} already exists and is immutable; publish a new version"
        )
        self.version = version


class UnknownEventType(IntegrityError):
    """Raised when the event log holds a type name with no registered constructor."""

    def __init__(self, type_name: str) -> None:
        super().__init__(f"unknown event type {type_name!r} (not registered via @event)")
        self.type_name = type_name
