"""Authority-boundary tests (invariant #1): the professor proposes; only the judger grants."""

from __future__ import annotations

import inspect

from ai_professor.contexts.judger import build_judger_registry
from ai_professor.contexts.professor import (
    NextTopicProposal,
    build_professor_registry,
    propose_next_topic,
)
from ai_professor.core.ledger import MilestoneLedger, mint_proof
from ai_professor.core.stores import Stores


def test_professor_registry_cannot_grant() -> None:
    reg = build_professor_registry()
    assert not reg.has("confirmMilestone")  # the teaching context cannot grant progression
    assert reg.has("nextTopic")  # it can only propose


def test_professor_builder_is_given_no_ledger() -> None:
    # Structural enforcement of invariant #1: the teaching context is never handed a write path.
    assert inspect.signature(build_professor_registry).parameters == {}
    assert "ledger" in inspect.signature(build_judger_registry).parameters


def test_professor_next_topic_only_proposes() -> None:
    result = propose_next_topic("7.1")
    assert isinstance(result, NextTopicProposal)
    assert result.from_node == "7.1"


def test_judger_registry_can_grant(stores: Stores) -> None:
    reg = build_judger_registry(MilestoneLedger(stores.events))
    assert reg.has("confirmMilestone")


def test_judger_confirm_tool_writes_ledger(stores: Stores) -> None:
    ledger = MilestoneLedger(stores.events)
    reg = build_judger_registry(ledger)
    tool = reg.get("confirmMilestone")
    tool.handler(mint_proof(milestone_id="m1", node_id="7.1", proof_id="p1", evidence=("s1",)))
    assert ledger.confirmed() == frozenset({"m1"})
