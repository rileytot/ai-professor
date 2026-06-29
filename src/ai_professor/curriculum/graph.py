"""Tiny, dependency-free graph helpers for the deterministic curriculum QA checks.

Hand-rolled (not networkx) so the algorithms behind a consequential gate -- acyclicity and
reachability -- are auditable in-repo (invariant #4: deterministic authority you can inspect).
Curricula are modest in size, so the recursive cycle search is fine.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

Adjacency = Mapping[str, frozenset[str]]

_EMPTY: frozenset[str] = frozenset()


def build_adjacency(
    nodes: Iterable[str], edges: Iterable[tuple[str, str]]
) -> dict[str, frozenset[str]]:
    """Build a successor map ``node -> {successors}`` from nodes and (src, dst) edges."""
    out: dict[str, set[str]] = {n: set() for n in nodes}
    for src, dst in edges:
        out.setdefault(src, set()).add(dst)
        out.setdefault(dst, set())
    return {node: frozenset(succs) for node, succs in out.items()}


def find_cycle(adj: Adjacency) -> list[str] | None:
    """Return one cycle as a node path (``[a, b, ..., a]``) if any exists, else ``None``."""
    white, gray, black = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(adj, white)
    path: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = gray
        path.append(node)
        for nxt in adj.get(node, _EMPTY):
            state = color.get(nxt, white)
            if state == gray:  # back-edge to a node on the current path => cycle
                return [*path[path.index(nxt) :], nxt]
            if state == white:
                found = visit(nxt)
                if found is not None:
                    return found
        path.pop()
        color[node] = black
        return None

    for start in adj:
        if color[start] == white:
            found = visit(start)
            if found is not None:
                return found
    return None


def reachable_from(adj: Adjacency, sources: Iterable[str]) -> frozenset[str]:
    """All nodes reachable from ``sources`` following successor edges (inclusive of sources)."""
    seen: set[str] = set()
    stack = list(sources)
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adj.get(node, _EMPTY) - seen)
    return frozenset(seen)
