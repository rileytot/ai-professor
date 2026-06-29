# AI-Native Curriculum Harness

A deterministic system that turns human-authored sources (textbooks, OpenCourseWare) into a
**source-grounded curriculum DAG**, then has a learner work through it across many sessions, with
**progression gated by demonstrated proficiency judged in a context isolated from teaching.**

The motivating thesis: an LLM asked to *both* teach *and* decide what to teach next will skip material.
The fix is to separate those decisions and subordinate teaching to a pre-built, reviewed, grounded
curriculum. **The curriculum is the harness; the AI "professor" is subordinate to it.**

> **Status: pre-v1, under active construction.** The current build target is a thin end-to-end vertical
> slice over **one chapter** of OpenStax *University Physics* Vol. 1 — see `PLAN.md`. "Make me a physics
> major" is the north star, **not** a current deliverable.

## Documents

- **`DESIGN.md`** — authoritative specification + reasoning corpus (decisions *and* rejected alternatives).
- **`PLAN.md`** — the phase-gated v1 build plan.
- **`CLAUDE.md`** — operating guide + the 10 load-bearing invariants for any agent working here.
- **`PRIOR_ART.md`** — what existing systems to adopt / fork / reference / skip.

## Copyright & content (please read)

This repository contains **only curriculum structure and source locators** — never copyrighted content.
Problem text is rehydrated at runtime from the user's own copy of a source, kept in a local, git-ignored
`content/` directory. v1 uses CC-BY OpenStax material, but the structure/locators-only separation is
enforced from the first commit so the design stays sound for non-open sources a user supplies themselves.

## Quick start (development)

```bash
python -m venv .venv
. .venv/Scripts/activate        # Git Bash on Windows;  .venv\Scripts\Activate.ps1 in PowerShell
pip install -e ".[dev]"
pytest
```

## License

To be determined (intended fully open-source if released). Until a `LICENSE` file is added, all rights
reserved by the author.
