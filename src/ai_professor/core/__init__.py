"""Integrity core: append-only event log, milestone ledger, knowledge projection, gating
state machine, and the three SQLite stores.

This package is deliberately isolated (DESIGN.md §7, PLAN.md): it holds the load-bearing
immutability + authority guarantees, so it stays a clean candidate for a PyO3/Rust port if
compiler-enforced internal invariants ever earn their cost.
"""
