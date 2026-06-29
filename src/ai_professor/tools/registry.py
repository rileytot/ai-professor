"""Tool registry: the per-context tool surface.

Per invariant #8, tools are transport, not authority. The integrity property they carry is
*which context gets which tools*: the professor's registry omits ``confirmMilestone`` so the
teaching context structurally cannot grant progression; the judger's registry holds it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Tool:
    """A named handler exposed to a context."""

    name: str
    handler: Callable[..., Any]
    description: str = ""


class ToolRegistry:
    """An immutable-after-construction set of tools available to one context."""

    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool {tool.name!r}")
        self._tools[tool.name] = tool

    def has(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"no tool {name!r} in this registry") from None

    def names(self) -> frozenset[str]:
        return frozenset(self._tools)
