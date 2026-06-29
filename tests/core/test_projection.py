"""Tests for the derived knowledge projection (store 2): fold, replay, time-travel."""

from __future__ import annotations

from ai_professor.core.events import AnswerSubmitted, MilestoneConfirmed, TopicStarted
from ai_professor.core.stores import Stores


def _seed_topic(stores: Stores) -> None:
    stores.events.append(TopicStarted(node_id="7.1"))
    stores.events.append(AnswerSubmitted(node_id="7.1", item_id="i", variant_seed=1, correct=True))
    stores.events.append(AnswerSubmitted(node_id="7.1", item_id="i", variant_seed=2, correct=True))
    stores.events.append(AnswerSubmitted(node_id="7.1", item_id="i", variant_seed=3, correct=False))


def test_fold_reconstructs_state(stores: Stores) -> None:
    _seed_topic(stores)
    state = stores.projection.current()
    assert state.current_node == "7.1"
    assert state.node("7.1").correct_submissions == 2  # two correct, one incorrect
    assert state.version == 4


def test_milestone_confirmed_updates_state(stores: Stores) -> None:
    stores.events.append(TopicStarted(node_id="7.1"))
    stores.events.append(MilestoneConfirmed(milestone_id="m1", node_id="7.1", proof_id="p1"))
    state = stores.projection.current()
    assert "m1" in state.confirmed_milestones
    assert "m1" in state.node("7.1").confirmed_milestones


def test_replay_is_deterministic(stores: Stores) -> None:
    _seed_topic(stores)
    assert stores.projection.current() == stores.projection.current()


def test_time_travel_as_of(stores: Stores) -> None:
    _seed_topic(stores)
    # After only the first event (TopicStarted), no answers have been folded yet.
    early = stores.projection.as_of(1)
    assert early.current_node == "7.1"
    assert early.node("7.1").correct_submissions == 0
    # Up to seq 3 (TopicStarted + two correct answers); the seq-4 incorrect answer is excluded.
    mid = stores.projection.as_of(3)
    assert mid.node("7.1").correct_submissions == 2


def test_unknown_node_returns_empty_state(stores: Stores) -> None:
    state = stores.projection.current()
    assert state.node("nope").correct_submissions == 0
    assert state.node("nope").confirmed_milestones == frozenset()
