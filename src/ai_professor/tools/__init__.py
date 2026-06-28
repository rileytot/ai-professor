"""Tool surface mediating the contexts (``nextTopic``, ``confirmMilestone``, serve-variant,
submit, hint, grade, ...).

Per invariant #8: this is transport/wiring only. The guarantees come from immutability and
where authority sits (the state machine + ledger), not from the tools themselves.
"""
