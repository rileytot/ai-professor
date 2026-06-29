"""Tests for the dependency-free graph helpers."""

from __future__ import annotations

from ai_professor.curriculum.graph import build_adjacency, find_cycle, reachable_from


def test_build_adjacency_includes_isolated_and_edge_endpoints() -> None:
    adj = build_adjacency(["a", "b", "c"], [("a", "b")])
    assert adj["a"] == frozenset({"b"})
    assert adj["b"] == frozenset()
    assert adj["c"] == frozenset()


def test_find_cycle_returns_none_for_a_dag() -> None:
    adj = build_adjacency(["a", "b", "c"], [("a", "b"), ("b", "c"), ("a", "c")])
    assert find_cycle(adj) is None


def test_find_cycle_detects_a_cycle() -> None:
    adj = build_adjacency(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")])
    cycle = find_cycle(adj)
    assert cycle is not None
    assert cycle[0] == cycle[-1]  # closed loop
    assert len(cycle) >= 3


def test_reachable_from() -> None:
    adj = build_adjacency(["a", "b", "c", "d"], [("a", "b"), ("b", "c")])
    assert reachable_from(adj, ["a"]) == frozenset({"a", "b", "c"})
    assert "d" not in reachable_from(adj, ["a"])
