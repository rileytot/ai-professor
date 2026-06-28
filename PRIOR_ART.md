# PRIOR_ART.md — what to adopt, fork, reference, or skip

> Evaluated during the bootstrap research pass (see `DESIGN.md` §15.5). **Strategic read:** no existing
> system combines (a) strict-sourced assessment, (b) deterministic DAG gating with a separated
> *adversarial* judger, (c) a CAS-deterministic grading rail, and (d) build-once community-curated
> curricula — *that combination is this project's novel contribution.* But the grading rail, spaced
> repetition + BKT, citation-grounded tutoring + learner memory, and curated content libraries already
> exist as forkable parts. **The build is more integration than invention** — fork aggressively.

## Subsystem → source map

| Our subsystem | Source | Action |
|---|---|---|
| CAS grading rail | **SymPy** (BSD) — in-process | **ADOPT** as the v1 engine |
| CAS answer-test taxonomy + diagnostic feedback | **STACK/Maxima** (GPL) | **REFERENCE** the patterns; skip Moodle/PHP |
| Spaced-repetition scheduler | **OpenTutor** FSRS module (MIT) | **FORK** (port to Python module) |
| Mastery / knowledge-tracking | **OATutor** BKT + `skillModel.json` (MIT) | **REFERENCE** BKT; **ADOPT** schema idea |
| Curated content-library layout | **OATutor** `content-pool/` (MIT) | **ADOPT** the on-disk structure |
| Citation-grounding | **DeepTutor** PageIndex / dual-KG (Apache-2.0) | **REFERENCE** (post-v1 surface) |
| Learner-memory substrate | **DeepTutor** Trace-Forest (Apache-2.0) | **REFERENCE** (post-v1 surface) |
| External benchmark / eval | **DeepTutor** TutorBench (Apache-2.0) | **ADOPT** as candidate external eval |
| Hybrid-corpus (user-supplied copy) | **Open TutorAI** (BSD-3) | **REFERENCE** (post-v1 §9 flow) |

*Note: licensing is not a constraint for this project (non-commercial; fully open-source if released),
so all of the above are usable; choices below are on technical merit + integration cost.*

## STACK / Maxima — `maths/moodle-qtype_stack` (PHP + Maxima/Lisp, GPL)
The CAS-assessment gold standard: ~20 years of randomized question variants + Maxima answer-testing for
algebraic equivalence, numerical tolerance, **dimensional/units handling**, and **significant figures**,
plus **potential-response-trees (PRTs)** mapping answer properties → specific diagnostic feedback.
- **REFERENCE** the answer-test taxonomy (`AlgEquiv`, `NumRelative`, `NumAbsolute`, `NumSigFigs`,
  `Units`/`UnitsStrict`) when building `grading/cas.py`, and the **PRT pattern** for `grading/feedback.py`
  (serves the "diagnostic, encouraging gate" of DESIGN.md §6.2).
- **SKIP** the Moodle/PHP coupling entirely. Maxima-as-subprocess is heavier than SymPy-in-process and
  unnecessary for v1's numeric-template grading. Revisit Maxima only if symbolic/open-ended grading
  returns post-v1.

## SymPy — `sympy/sympy` (Python, BSD) — the v1 CAS engine
**ADOPT.** In-process, no subprocess overhead, `sympy.physics.units` for dimensional analysis, symbolic
equivalence + numeric eval. Sig-figs needs a thin custom wrapper. Satisfies invariant #4's "adopt, don't
build a grader" — SymPy *is* a mature CAS. Sufficient for v1; the heuristic-simplification weakness vs
Maxima does not bite numeric-template grading.

## DeepTutor — `HKUDS/DeepTutor` (Python + TS, Apache-2.0)
Closest prior art: citation-grounded tutoring (PageIndex, page-level citations; dual structural+semantic
KG) + a **Trace-Forest learner-memory** substrate (session summaries → weakness patterns → reflections)
+ difficulty-calibrated question generation. Ships **TutorBench** (90 learner profiles × interactive
tasks across 5–6 STEM domains incl. physics).
- **ADOPT TutorBench** as the candidate external benchmark (invariant #6 / DESIGN.md §8).
- **REFERENCE** the citation-grounding and Trace-Forest patterns when the open-ended/professor surfaces
  mature (post-v1). It is a tightly-coupled monolith and *generates* questions (vs our strict sourcing)
  with no deterministic-DAG gating, no separated adversarial judger, no CAS rail — **do not fork wholesale.**

## OpenTutor — `zijinz456/OpenTutor` (Python + TS, MIT)
Modular service layers: a dedicated `spaced_repetition/` (**FSRS 4.5**) and `learning_science/` (**BKT**).
- **FORK** the FSRS scheduler into `review/scheduler.py` and reference the BKT logic for mastery
  tracking. The algorithms are small and cleanly separable; port rather than depend on the FastAPI/Next
  stack.

## OATutor — `CAHLR/OATutor` (TypeScript/React, MIT)
Gold standard for **curriculum/content organization**: `skillModel.json` (step → knowledge-component),
`bktParams.json` (per-KC probMastery/probTransit/probSlip/probGuess), and a hierarchical
`content-pool/[problem]/steps/.../tutoring/` layout with hint pathways. Content is decoupled from the UI
(JSON-based) and already includes OpenStax sources.
- **ADOPT** the on-disk content-library structure as the model for `curricula/` (locators-only) +
  `grading/templates.py`. **REFERENCE** the BKT parameters and weakest-KC problem-selection heuristic.

## Open TutorAI — `Open-TutorAi/open-tutor-ai-CE` (Python + Svelte, BSD-3)
Multi-source RAG (local KB + web + chat history) with provider adapters; very recent (Feb 2026).
- **REFERENCE** the hybrid-corpus pattern for the post-v1 "user procures their own copy" flow
  (DESIGN.md §9). Early-stage — do not depend on it.

## Provider adapter libraries
- **`litellm`** (Python) — unified interface to 100+ providers with built-in retry/fallback; backs our
  *fallback* backends (Anthropic / OpenAI-standard / Ollama-local) behind `provider/backends.py`.
- The **OAuth Codex route** is unofficial and not covered by litellm — implement it directly in
  `provider/codex_oauth.py` (reads `~/.codex/auth.json`, OpenAI-Responses-shaped, full-history resend).
