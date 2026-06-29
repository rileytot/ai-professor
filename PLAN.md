# PLAN — AI-Native Curriculum Harness, v1 vertical slice

## Context

We are bootstrapping an **AI-native curriculum harness**: a deterministic system that turns
human-authored sources into a source-grounded curriculum DAG, then has a learner work through it
across many sessions, with progression **gated by demonstrated proficiency judged in a context
isolated from teaching**. The motivating thesis (`DESIGN.md` §1): an LLM asked to *both* teach *and*
decide what to teach next will skip material; the fix is to separate those and subordinate teaching
to a pre-built, reviewed, grounded curriculum.

`DESIGN.md` is authoritative and already records the reasoning + rejected alternatives. This plan
builds **only the v1 slice** (`DESIGN.md` §12) and resists scope creep toward the full "physics
major" system — that over-build is the explicit never-ship risk this slice exists to avoid.

**What v1 proves:** *separated grading + deterministic gating + sourced assessment + spaced review
across sessions*, end-to-end, for a **single chapter**, with everything the spine doesn't need
deferred. If the thin slice produces real learning, every deferred piece becomes an extension of a
working spine rather than a bet.

## Decisions (confirmed this session)

- **Stack: pure Python.** LLM-authority boundary is *architectural* (tool-surface/process), so it is
  equally strong in Python; Python maximizes first-light probability (the dominant risk) in the
  developer's strongest language. The integrity core is kept **physically isolated** (`core/`) so a
  PyO3/Rust port stays clean if compiler-enforced internal invariants later earn their cost.
- **CAS: SymPy in-process.** Sufficient for v1 numeric-template grading (units, numeric eval,
  tolerance, sig-figs). STACK's answer-tests + potential-response-trees are *reference patterns* for
  diagnostic feedback, not adopted code. Maxima is revisited only if/when symbolic/open-ended grading
  returns post-v1. (Satisfies invariant #4 "adopt, don't build a grader" — SymPy *is* a mature CAS.)
- **Runtime LLM backend: OAuth Codex route first**, behind a swappable `LLMProvider` adapter, with
  `litellm`-backed fallbacks (Anthropic / OpenAI-standard / Ollama-local) and **auto-fallback** on
  auth/transport failure. The Codex backend is custom in any language (unofficial route); our
  event-sourced transcript already supplies the full-history resend its stateless endpoint needs.
- **Storage: event-sourcing on SQLite**, three distinct stores (§7): (1) curriculum — immutable per
  version; (2) knowledge projection — derived/folded from events; (3) transcript/event log —
  append-only audit. Append-only enforced by the store API (no update/delete path).
- **v1 judger is deterministic.** Because v1 grading is fully CAS, the judger needs **no LLM**: it is
  an isolated gating service (CAS check + policy + ledger write) that sees ONLY current-topic work +
  relevant milestones. This is the strongest realization of invariants #1/#2/#4. The LLM-judger
  machinery (adversarial framing, multi-sample → escalate, citation gate) is the **post-v1 extension
  point**; its *interface* (confirmMilestone requires proof, isolated inputs, adversarial posture) is
  established now.
- **Content/chapter:** OpenStax *University Physics* Vol. 1 (CC BY), **Chapter 7 "Work and Kinetic
  Energy"** (sections 7.1 Work, 7.2 Kinetic Energy, 7.3 Work-Energy Theorem, 7.4 Power). Confirmed via
  research: standard "By the end of this section, you will be able to:" LO format; CNXML/PDF source
  available.
- **Cold-start: skipped for v1** (start-from-zero, single chapter) — §11/§12. Revisit at volume scale.
- **Gate threshold: lean strict, soften the experience** (§6.2). Starting default: a milestone is
  mastered = **3 distinct correct numeric-variant items** (tune on data), with **unlimited friendly,
  diagnostic retries** between attempts (never a verdict-with-no-recourse).
- **Shareable curriculum = structure + locators only** (invariant #7), enforced from commit one even
  though OpenStax is CC BY. Problem *content* lives only in a local, git-ignored `content/` dir.
- **Retrieval = deterministic graph-adjacency** (current node + immediate prereq/successor neighbors),
  never embedding/semantic search (§7).

## The 10 invariants (→ go verbatim-faithful into `CLAUDE.md`, with IMPORTANT/YOU MUST/NEVER markers)

1. **Authority lives in immutable state, never in the teaching model.** Professor may *propose*
   advancement (`nextTopic`); only the judger may *grant* it (`confirmMilestone`, with proof).
   **NEVER let the teaching context grant its own progression.**
2. **The judger runs lean, isolated, adversarial.** It receives ONLY current-topic work + relevant
   milestones — **never** the teaching transcript. It tries to *falsify* mastery. Calibrate it to flag
   only milestone-relevant deficiencies.
3. **Ground two layers, not one.** Assessment (problems/answers sourced, never generated) AND
   curriculum structure (topic set + edges from the textbook's own LOs + cross-source diff).
   **Omission is the invisible, dominant risk** (§2 face #2).
4. **Prefer deterministic authority over model judgment** for every consequential decision: CAS for
   answer-checking, graph algorithms for coverage, an immutable ledger for progression. The LLM owns
   high-variance *generation*, never final authority over coverage.
5. **Citation-faithfulness gate precedes argument evaluation** (§5.4). Verify a quoted source is real
   and supports the claim before evaluating the argument. *(Deferred past v1; bake the invariant in
   now so it is never retrofitted unsafely.)*
6. **Validate against an EXTERNAL standard, never the system's own gates** (meta-Goodhart, §8).
7. **Shareable artifacts contain ONLY structure + source locators, never copyrighted content** (§9).
8. **Do not attribute guarantees to MCP/transport** (§3). Guarantees come from immutability + where
   authority sits.
9. **Do not rely on LLM self-correction** (§15.4). Use independent inputs + reference-comparison + CAS.
10. **Keep context lean** — quality degrades as context fills; use subagents for file-heavy subtasks.
    The system is *about* coherence under context limits; build it that way.

## Architecture (Python)

Three deliberately isolated contexts mediated by a tool surface; **authority + immutability** (not
the transport) provide the guarantees.

- **curriculum-gen / extractor context** — builds the Ch 7 DAG from TOC + LOs, proposes node
  clustering + cross-edges; human-verified; runs once; output is immutable. The single trust root.
- **professor context** — teaches one topic, navigates/quotes source, generates hints, serves numeric
  variants, proposes `nextTopic`. **Subordinate**: its tool registry does **not** include
  `confirmMilestone`. Stylistic latitude in explanation; substance/assessment strictly grounded.
- **judger context (deterministic in v1)** — fresh isolated instance on `nextTopic`; receives ONLY
  current-topic work + milestones; runs CAS checks; applies the gating policy; **sole writer** of
  `confirmMilestone` (with `VerifiedProof`) to the append-only ledger.

**Capability-token pattern (the Python enforcement of invariant #1):** `confirm_milestone(p:
VerifiedProof)` where `VerifiedProof` is only minted inside the judger's verification path
(module-private factory); the professor's tool registry omits the write tool; the event/ledger store
exposes only `append` + read views (no update/delete). Backed by a deterministic QA + integrity test
wall rather than a compiler.

## Proposed project structure

```
ai-professor/
├─ DESIGN.md  CLAUDE.md  PRIOR_ART.md  PLAN.md  README.md  pyproject.toml
├─ src/ai_professor/
│  ├─ core/            # ISOLATED integrity core (PyO3/Rust-port candidate)
│  │  ├─ events.py  ledger.py  projection.py  state_machine.py  stores.py
│  ├─ curriculum/     ingest.py  extract.py  dag.py  qa_checks.py  provenance.py
│  ├─ grading/        templates.py  cas.py  feedback.py
│  ├─ contexts/       professor.py  judger.py  extractor.py
│  ├─ tools/          # nextTopic, confirmMilestone, serveVariant, submit, hint, grade …
│  ├─ provider/       adapter.py  codex_oauth.py  backends.py
│  ├─ review/         scheduler.py (FSRS)  fire.py (trickle-down credit)
│  ├─ retrieval.py  session.py  checkpoint.py
├─ content/           # LOCAL ONLY, git-ignored — user's OpenStax copy / rehydrated text
├─ curricula/         # SHAREABLE — structure + locators ONLY, never content
├─ eval/              # external-benchmark harness (TutorBench-style)
└─ tests/  (core/ curriculum/ grading/ contexts/ + integration/)
```

## Phase-gated build (vertical slice; first-light at one section)

**Every phase:** ships unit + integration tests; ends with an **adversarial review subagent** that
checks the diff against this plan + `DESIGN.md` invariants (correctness/requirement gaps only, not
style — mirroring the system's own judger); then **commit + push** to the `ai-professor` repo.

### Phase 0 — Foundations & guardrails
- `git init`; create/connect the `ai-professor` GitHub repo (via `gh`; create if absent); first commit.
- `CLAUDE.md` (≤200 lines: mission paragraph, the 10 invariants with emphasis markers, v1 scope
  boundary, pointer to `DESIGN.md` as authoritative). `PRIOR_ART.md` (table below). `PLAN.md` (this).
- Python scaffold: `pyproject.toml` (uv), package layout, `ruff` + `mypy --strict` + `pytest` +
  pre-commit. `content/` git-ignored.
- Three-store storage on SQLite: append-only event log (no update/delete in API), immutable-per-version
  curriculum store, derived knowledge projection. Event-sourcing primitives: event types, `append`,
  `fold`/`replay`.
- `LLMProvider` adapter: interface + **OAuth Codex backend** (reads `~/.codex/auth.json`, Responses-
  shaped, full-history resend; secrets never logged) + `litellm` fallbacks + auto-fallback on failure.
- Capability-token + dual tool-registry skeleton (professor registry vs judger registry).
- **DoD/tests:** append-only enforced (mutate attempt fails); replay reconstructs projection;
  time-travel works. Adapter dispatches; OAuth request shape correct (mocked); auto-fallback fires on
  simulated auth failure. Professor registry asserts **no** `confirmMilestone`; `VerifiedProof`
  un-constructable outside judger module. CI green; mypy strict clean; pushed.

### Phase 1 — Ch 7 curriculum DAG (extract-and-verify) + deterministic QA wall
- Ingest OpenStax Univ Physics Vol 1 Ch 7 (7.1–7.4): section structure, LOs (key on "By the end of
  this section, you will be able to:"), end-of-chapter problems + available answers. Content → local;
  **curriculum stores locators only** (e.g., "OpenStax Univ. Physics Vol.1 §7.1, problem 7.12").
- Extractor proposes LO→node clustering + non-linear cross-edges (e.g., 7.3 depends on 7.1 + 7.2);
  CoT + structured XML output; **human-verify** step for the proposed edges; provenance-stamp
  (sources/versions, human-reviewed vs provisional).
- The **7 deterministic QA checks** (§8) as a runnable validator + tests: acyclic; entry-reachable;
  terminal reachable; every gate's milestones covered upstream; every milestone has ≥1 sourced item
  with a CAS-verifiable answer; no orphans; **every LO maps to a node** (completeness).
- Manual cross-source diff: Ch 7 TOC vs MIT 8.01 work/energy syllabus (documented artifact, an
  afternoon — not a pipeline).
- **DoD/tests:** all 7 QA checks pass; extraction unit tests; completeness check passes; curriculum
  artifact contains **no** copyrighted content (asserted); human-verified edges + provenance committed.

### Phase 2 — CAS numeric-template grading rail (SymPy)
- Template = sourced problem + parameter spec (ranges/constraints) + answer formula; **deterministic
  seeded sampling** (reproducible for audit); SymPy computes the answer with units; grader checks
  learner answer within tolerance + sig-figs + unit-equivalence.
- Potential-response-tree-style diagnostic feedback (reference STACK) for wrong answers (feeds the
  gentle gate). Author **≥1 numeric-template item per Ch 7 milestone**.
- **DoD/tests:** golden tests (template+seed → known answer); tolerance/sig-fig/unit edge cases;
  determinism (same template+seed → identical grade every run); lookup-resistance (distinct seeds →
  distinct numbers); subset cross-checked vs OpenStax answer key; every milestone has a passing
  template.

### Phase 3 — FIRST LIGHT: one section (7.1) end-to-end
- Thin professor teaches 7.1 (quotes source, hints, serves variants, proposes `nextTopic`).
- Deterministic judger: fresh isolated instance; ONLY 7.1 work + 7.1 milestones; CAS check; gating
  policy (lean-strict: 3 correct distinct variants); writes `confirmMilestone` (with proof) **or**
  returns diagnostic "not-yet" (specific, actionable, retry-friendly — §6.2).
- Append-only ledger records the proof for audit. Session driver ties professor → submit → grade →
  `nextTopic` → judger → ledger → state advance.
- **DoD/integrity tests (invariants #1/#2/#4):** professor cannot write the ledger (structural);
  judger inputs contain no teaching transcript (asserted); `confirmMilestone` rejects invalid/absent
  proof; ledger append-only; passing K variants advances state, failing yields diagnostic + retry, no
  advance; projection reflects new mastery; replay reproduces it. **Live demo:** a learner completes
  7.1 end-to-end and the gate behaves correctly. ← *first light.*

### Phase 4 — Widen to full Ch 7 + multi-session + spaced review + checkpoint + external eval
- Extend professor/judger/items to all of 7.1–7.4 with verified cross-edges gating order.
- Multi-session continuity: each session re-orients from state via **graph-adjacency retrieval**
  (current node + neighbors), not semantic search.
- Spaced review: **FSRS scheduler** (fork OpenTutor) across sections; **FIRe** trickle-down credit
  through the prereq graph. Reactive-review fork on a shaky prereq **emits an event, does not merge**.
- **Cumulative checkpoint** at end of Ch 7 (midterm/final analog; re-tests the module — §6.1).
- **External-benchmark scaffold**: a minimal harness reporting a number **not derived from our own
  gates** (TutorBench-style task or a held-out problem set) — invariant #6.
- **DoD/tests:** full Ch 7 traversable with correct gating order; session-reset recovery (fresh
  session re-orients from state alone); spaced-review + FIRe propagation tests; reactive fork emits
  event without trunk bloat; cumulative checkpoint catches an injected decayed/false-passed prereq;
  benchmark harness runs. **Demo:** a learner works all of Ch 7 across ≥2 sessions with spaced review
  and a final cumulative checkpoint.

## Prior-art map (→ `PRIOR_ART.md`; from this session's research)

| Project | Lang / License | Verdict for our subsystems |
|---|---|---|
| **STACK / Maxima** (`maths/moodle-qtype_stack`) | PHP+Lisp / GPL | **REFERENCE** the answer-test taxonomy (AlgEquiv, NumRelative, NumSigFigs, Units) + potential-response-tree diagnostic feedback. **SKIP** the Moodle/PHP coupling. v1 grader = SymPy, not adopted STACK code. |
| **DeepTutor** (`HKUDS/DeepTutor`) | Py+TS / Apache-2.0 | **REFERENCE** citation-grounding (PageIndex, page-level cites) + Trace-Forest learner-memory pattern. **ADOPT TutorBench** as the candidate external eval (invariant #6). Monolithic — don't fork wholesale. |
| **OpenTutor** (`zijinz456/OpenTutor`) | Py+TS / MIT | **FORK** the FSRS scheduler + BKT (separable service modules) into `review/`. |
| **OATutor** (`CAHLR/OATutor`) | TS / MIT | **ADOPT** the content-library schema (`skillModel.json` + `bktParams.json` + `content-pool/`) as the curated-item layout; reference BKT + problem-selection heuristics. |
| **Open TutorAI** (`Open-TutorAi/open-tutor-ai-CE`) | Py+Svelte / BSD-3 | **REFERENCE** the hybrid-corpus pattern for the post-v1 user-supplied-copy flow (§9). Early-stage; don't depend on it. |

## Verification (end-to-end)

- `pytest` (all) / `pytest tests/integration` (end-to-end + integrity tests); `mypy --strict`; `ruff`.
- `python -m ai_professor.curriculum.qa_checks curricula/univ_physics_v1_ch7.json` → runs the 7 §8 checks.
- `python -m ai_professor.session --topic 7.1` → first-light session (Phase 3 demo).
- `python -m ai_professor.session --chapter 7 --sessions 2` → multi-session + checkpoint (Phase 4).
- `python -m ai_professor.eval` → external-benchmark harness (reports a non-self-referential number).

## Deferred past v1 (scope guard — `DESIGN.md` §10/§12/§14)

Reconciliation pipeline (→ v2); copyright hybrid + user-supplied-copy UX; handwriting input; the hard
open-ended grading residue (reference-comparison + citation-gated self-adjudication); cold-start
placement; DAG versioning/migration; the full tool surface beyond `nextTopic`/`confirmMilestone`.
**"Physics major" remains the north star, not a v1 deliverable.**

## Risks / watch-items

- **Never-ship** (the dominant risk) → mitigated by the thin single-chapter slice; a v1 stall is
  unambiguously a spine problem, not a pipeline problem.
- **Omission** (the invisible risk) → mitigated by the LO→node completeness check + the MIT 8.01 diff.
- **Grading sycophancy** → not present in v1 (CAS is deterministic); the reason open-ended grading is
  deferred.
- **OAuth-route fragility** → mitigated by the adapter + auto-fallback to litellm backends.
- **Python integrity-by-discipline residual** → mitigated by core isolation + capability tokens + the
  integrity test wall; a PyO3/Rust core port remains a clean future option if it earns its cost.
