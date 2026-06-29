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


class ProofForgeryError(IntegrityError):
    """Raised when a milestone is confirmed without a genuinely-minted ``VerifiedProof``.

    The proof is an unforgeable capability token: it can only be minted by the judger's
    verification path (DESIGN.md §3, invariant #1). A confirmation backed by anything else --
    a hand-built object, a look-alike, a token minted without the module-private guard -- is a
    forgery and is refused.
    """

    def __init__(
        self, detail: str = "milestone confirmation requires a minted VerifiedProof"
    ) -> None:
        super().__init__(detail)
