# CLAUDE.md — AI-Native Curriculum Harness

Operating guide for any agent working in this repo.

**`DESIGN.md` is the authoritative specification and reasoning corpus.** It records not just decisions
but the *arguments and rejected alternatives* behind each. Read the relevant sections before proposing
changes. If you believe `DESIGN.md` is wrong or silent on something, **raise it explicitly — do not
silently diverge.** The phase-gated build plan is `PLAN.md`; prior-art evaluation is `PRIOR_ART.md`.

## Mission

Turn human-authored sources (textbooks, OpenCourseWare) into a **source-grounded curriculum DAG**,
then have a learner work through it across many sessions, with **progression gated by demonstrated
proficiency judged in a context isolated from teaching.** The thesis: an LLM asked to *both* teach
*and* decide what to teach next will skip material; the fix is to separate those and subordinate
teaching to a pre-built, reviewed, grounded curriculum. **The curriculum is the harness; the AI
"professor" is subordinate to it.**

## The 10 invariants — YOU MUST NOT violate these

These are load-bearing. They are the project's integrity.

1. **Authority lives in immutable state, never in the teaching model.** The curriculum and the
   milestone ledger are append-only and outside the professor's reach. The professor may *propose*
   advancement (`nextTopic`); only the judger may *grant* it (`confirmMilestone`, with proof).
   **NEVER let the teaching context grant its own progression.**
2. **The judger runs lean, isolated, adversarial.** It receives ONLY the learner's current-topic work
   plus the relevant milestones — **NEVER** the teaching-session transcript. Its job is to *falsify*
   mastery and find the flaw. Calibrate it to flag only milestone-relevant deficiencies.
3. **Ground two layers, not one.** Both the *assessment* (problems/answers from sources, never
   generated) AND the *curriculum structure* (topic set + prerequisite edges, from the textbook's own
   learning objectives + cross-source diff). **IMPORTANT: omission is the invisible, dominant risk.**
   "Every problem is sourced" does NOT make "the topic set complete."
4. **Prefer deterministic authority over model judgment** for every consequential decision: CAS for
   answer-checking, graph algorithms for coverage, an immutable ledger for progression. The LLM owns
   high-variance *generation* (explanation, hints, numeric *variants*), **never** final authority over
   coverage. Adopt a CAS (SymPy/Maxima); do NOT build a grader from scratch.
5. **The citation-faithfulness gate precedes argument evaluation.** When evaluating evidence-justified
   self-assessment, FIRST verify the quoted source is real and supports the claim; refuse to evaluate
   the argument otherwise. *(Deferred past v1 — but bake the invariant in now; never retrofit unsafely.)*
6. **Validate against an EXTERNAL standard, never the system's own gates** (meta-Goodhart). Design
   measurement toward an external benchmark (TutorBench now; GRE-Physics-style later).
7. **Shareable artifacts contain ONLY structure + source locators, never copyrighted content.**
   Curriculum files store citations ("OpenStax Univ. Physics Vol. 1 §7.2, problem 7.12"); problem text
   is rehydrated locally from the user's own copy at runtime. **This repo is public — enforce from
   commit one.** `content/` is git-ignored; `curricula/` holds locators only.
8. **Do not attribute guarantees to MCP/transport.** MCP is wiring. Guarantees come from immutability
   + where authority sits. Put rigor in the state machine, not the wiring.
9. **Do not rely on LLM self-correction.** A judger "double-checking itself" is not a safety mechanism;
   independent inputs, reference-comparison, and CAS are.
10. **Keep context lean.** Quality degrades as context fills. Use subagents for file-heavy or
    specialized subtasks; keep the main thread focused. **This system is *about* coherence under
    context limits — build it the way it is meant to work.**

## v1 scope boundary (DESIGN.md §12) — resist scope creep

Build **only** the thinnest end-to-end slice that exercises the core thesis, for a **single chapter**:
- **Content:** OpenStax *University Physics* Vol. 1 (CC BY), **Chapter 7 "Work and Kinetic Energy"**.
- **DAG:** *extract-and-verify* from the book's TOC + section learning objectives — NOT the full
  reconciliation pipeline (that is v2). The only generative act: cluster LOs into gateable nodes and
  propose non-linear cross-edges; a human verifies.
- **Grading:** **CAS-graded numeric-template problems only.** Skip the open-ended residue.
- **Architecture:** the three-context separation (curriculum-gen / professor / judger) end-to-end.
- **Gating:** per-node gates + a cumulative checkpoint at the end + spaced review across sessions.

**Deferred (do NOT build in v1):** reconciliation pipeline, copyright hybrid, handwriting input, the
hard open-ended grading residue, cold-start placement, DAG versioning/migration, the full tool surface.
**"Physics major" is the north star, NOT a v1 deliverable.** The never-ship risk this slice avoids is
building the whole system at once.

## Stack & key decisions (confirmed)

- **Pure Python** (3.12). The LLM-authority boundary is *architectural* (tool-surface/process), so it
  is equally strong in Python. The integrity core is kept physically isolated in `src/ai_professor/core/`
  so a PyO3/Rust port stays clean if compiler-enforced internal invariants later earn their cost.
- **CAS: SymPy in-process** (sufficient for v1 numeric-template grading). STACK's answer-tests +
  potential-response-trees are *reference patterns*, not adopted code.
- **Runtime LLM: OAuth Codex route first**, behind a swappable `LLMProvider` adapter, with
  `litellm`-backed fallbacks (Anthropic / OpenAI / Ollama-local) and auto-fallback on failure.
- **Storage: event-sourcing on SQLite**, three distinct stores (DESIGN.md §7): curriculum (immutable
  per version), knowledge projection (derived/folded), transcript/event log (append-only). Append-only
  is enforced by the store API (no update/delete path).
- **v1 judger is deterministic.** Because v1 grading is fully CAS, the judger needs no LLM: it is an
  isolated gating service (CAS check + policy + ledger write) seeing ONLY current-topic work +
  milestones. The LLM-judger machinery (adversarial framing, multi-sample→escalate, citation gate) is
  the post-v1 extension point; its *interface* (proof-required, isolated inputs) exists now.
- **Retrieval = deterministic graph-adjacency** (current node + neighbors), never semantic search.

## Architecture (three isolated contexts)

- **curriculum-gen / extractor** — builds the DAG from TOC + LOs; human-verified; runs once; output
  immutable. **The single trust root** — harden this above all else.
- **professor** — teaches one topic, navigates/quotes source, hints, serves variants, proposes
  `nextTopic`. Subordinate: its tool registry does **not** include `confirmMilestone`. Stylistic
  latitude in explanation; substance/assessment strictly grounded.
- **judger** (deterministic in v1) — fresh isolated instance on `nextTopic`; CAS-checks current-topic
  work against milestones; sole writer of `confirmMilestone` (with a `VerifiedProof` capability token)
  to the append-only ledger.

## How to work

- **Vertical slice, not horizontal phases.** Build the thinnest end-to-end path first (one section),
  prove it, then widen. Do NOT build "all DAG, then all grading, then all UI."
- **Each phase ships with tests**, including the deterministic curriculum-QA checks (DESIGN.md §8):
  acyclic prereq graph; entry/terminal reachable; every milestone covered upstream; every milestone has
  ≥1 sourced item with a CAS-verifiable answer; no orphans; every LO maps to a node. These are mostly
  free and high-leverage — implement them early.
- **Use an adversarial review subagent at each phase gate** to check the diff against `PLAN.md` +
  `DESIGN.md` invariants, reporting only correctness/requirement gaps, not style.
- **Fork before you build** (DESIGN.md §15.5): STACK/Maxima (CAS), OpenTutor (FSRS/BKT), OATutor
  (content schema), DeepTutor (citation-grounding, learner memory, TutorBench eval). See `PRIOR_ART.md`.
- **Commit frequently** to the `ai-professor` repo (remote: `origin`, public).

## Internal LLM prompting standards (extractor, professor, judger)

Evidence-backed only — no persona padding, no emotional-manipulation tricks. Use: clear decomposed
instructions; structured (XML-tagged) output for anything parsed; few-shot where format must be pinned;
chain-of-thought for reasoning steps; **never trust a single sample for a consequential judgment**
(self-consistency / multi-sample → escalate on disagreement); rubric decomposition for open-ended
evaluation; reference-comparison over de-novo evaluation; adversarial framing for the judger.

## Commands

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows (Git Bash); use .venv\Scripts\activate in PowerShell
pip install -e ".[dev]"                              # editable install + dev deps
pytest                                               # all tests
pytest tests/integration                             # end-to-end + integrity tests
mypy src                                              # strict type-check
ruff check . && ruff format --check .                # lint + format
```
