# AI-Native Curriculum Harness — Design Synthesis

> **Status:** Pre-build design synthesis. This document captures the complete reasoning, architecture, and decisions reached during the initial planning phase. It is written so that a future session can *advocate for these positions as well as the original reasoning could* — therefore it preserves the **arguments and rejected alternatives**, not just the conclusions. Where a choice was made, the "why" and the "instead of what" are recorded, because those are what a future session needs to defend the choice or knowingly revise it.
>
> **How to read this:** Sections 1–3 are the conceptual foundation (read first, in order). Sections 4–11 are the subsystems. Section 12 is the concrete v1 build plan. Section 13 distills the recurring design principles. Section 14 lists open/deferred decisions. Section 15 (added after a research pass) records what is empirically known vs unknown about each idea, related work, and forkable components.

---

## 1. Thesis

**Core insight.** If a single AI context is asked to *both* explain concepts *and* decide which concepts to teach next, skipping is near-guaranteed — the model has no external structure forcing completeness, and its "what next" judgment is stochastic and unauditable. The fix is to **separate the *explain* decision from the *advance* decision**, and to make the advance decision answer to a **fixed, pre-built, source-grounded curriculum** rather than to in-session model judgment.

**What is being built.** A *harness* — not a chatbot, not a prompt. A deterministic system in which:

1. A **curriculum** (a DAG of topics with gating milestones, grounded in human-authored sources) is generated **once, carefully, and reviewed**, then
2. **deterministically worked through** across many separate learning sessions (potentially hundreds), where
3. **progression between topics is gated by demonstrated proficiency**, judged in a context deliberately isolated from the teaching context.

The curriculum *is* the harness. The AI "professor" that teaches is subordinate to it.

**The ambition (north star).** A motivated self-learner could say little more than *"make me a physics major,"* and the system would harvest accredited curricula and textbooks into an organized, well-gated curriculum that — over hundreds of sessions — confers physics-major-equivalent **lecture-and-problem-set knowledge**. (Scope boundary in §10: this is *not* the same as a full degree; lab/experimental/research competence is out of reach for this architecture.)

**Design temperament.** The approach is admittedly "vibey" and has real hallucination exposure. The goal is not zero risk; it is that **the harness keeps things coherent enough that the vast majority of what the learner absorbs is grounded in truth, and a minimal amount of critical information is skipped.** Every design decision below is in service of pushing those two numbers in the right direction, and of being honest about where the residual risk lives.

---

## 2. The hallucination model (conceptual foundation)

The single most important reframe in the whole design: **"ground all testable content in textbooks" defends exactly one of (at least) four distinct hallucination surfaces.** Treating that one constraint as if it secures the whole system is the central error to avoid. The four faces:

1. **Assessment-item content** — the literal text of problems and their answers.
   *Covered* by the grounding rule (problems/answers come from sources, never generated).

2. **Curriculum structure & completeness** — the topic set, the prerequisite edges, the ordering, and crucially *what is missing*.
   **NOT covered** by grounding problems. This is **the highest-risk surface in the design.** Critical property: **omission is invisible.** A model building a curriculum cannot easily know what it left out, because the omitted thing isn't represented anywhere to be checked against, and there is no single source document for "the complete set of things a physics major must know." A curriculum of impeccably-sourced problems can silently omit all of statistical mechanics, or gate Lagrangian mechanics before the calculus of variations it requires, and a problem-grounding rule waves both through. This is *exactly* the skipping failure the project set out to eliminate — relocating it from the learning session to the curriculum-generation session does not close it.
   **Fix:** two-layer grounding (§4) — source the *structure*, not just the assessment.

3. **Milestone-satisfaction judgment** — deciding whether a piece of student work satisfies a milestone.
   **NOT covered**, and the "judger only checks off boxes" framing actively hides this. For physics, student work is derivations, proofs, multi-step modeling, and lab analysis. There is no quote to match a derivation against. Whether a four-line derivation with a sign error in step three "demonstrates mastery" is an open-ended evaluation carrying the full hallucination-and-sycophancy load. Renaming it "checking a box" does not make it string-matching.
   **Fix:** the grading partition (§5) — push as much as possible onto deterministic (CAS) checking; constrain the rest with reference-comparison and citation gates.

4. **Instruction itself** — the explanations, analogies, and worked-example walkthroughs the professor produces *during* learning sessions.
   **NOT covered.** Grounding assessment does not ground teaching. A learner can be taught a subtly wrong mental model, then pass a *sourced* assessment by pattern-matching, and carry the misconception downstream.
   **Fix:** push the professor toward **navigating and quoting source material** (assigned readings + Socratic guidance *over the actual textbook*) rather than free-lecturing from its own weights. Professor as reading-guide and problem-set coach, not oracle.

**Why this model matters:** every later decision is traceable to "which face does this defend, and what's still exposed." A future session should resist any proposal that implicitly assumes face #1's defense generalizes to #2–#4.

---

## 3. System architecture (separated contexts)

The system is a set of **deliberately isolated contexts** mediated by tools, with authority and immutability — not the tooling itself — providing the guarantees.

**The contexts:**

- **Curriculum-generation context.** Builds the DAG and attaches sourced assessment items + milestones. Runs rarely (ideally once per curriculum version). **This is the single trust root** (see below).
- **Learning-session context ("the professor").** Teaches one topic at a time. Has rapport with the learner. Is *subordinate*: it can *propose* advancement but cannot *grant* it.
- **Judging context ("the judger").** Decides readiness to advance. Runs in a **lean context** containing *only* the learner's work on the current topic plus the relevant curriculum milestones — deliberately **excluding** the large, rapport-laden learning-session context, to maintain an independent point of view. Has an **adversarial objective**: try to falsify mastery, not to help.
- **Knowledge-state store.** Tracks the learner's mastery (see §7). Never loaded in full into a learning session.

**The trust-root asymmetry (critical).** The judger reads milestones *from* the curriculum-generation context's output, so it can validate **work-against-milestone** but never **milestone-against-reality**. No amount of downstream decorrelation changes this: **curriculum-generation is the one context whose correctness everything else inherits.** Hence the disproportionate investment in sourcing and reviewing the curriculum (§4) and the deterministic QA checks (§8). A future session should treat "harden the curriculum-gen step" as categorically more important than hardening any other context.

**On MCP and "the harness."** MCP (or any tool transport) is **wiring, not a guarantee.** It mediates inter-context calls and gates progression *mechanically*, but the *robustness* comes from **where authority sits and what is immutable**: the curriculum and the milestone ledger are append-only and outside the professor's reach. You could build these guarantees without MCP, and you could build something fragile with it. Put the rigor in the **state machine and the immutability**, and let MCP just be the transport. (Do not attribute robustness to MCP in any future writeup.)

**Tool sketches (illustrative, not exhaustive — many more needed):**

- `nextTopic` — the professor calls this when it believes the learner is ready. It **triggers a fresh judger instance** that uses explicit curriculum milestones to decide, specifically avoiding the learning-session context.
- `confirmMilestone` — the judger checks off a milestone against a `todo`-style list that can *only* be mutated through this tool. It **requires proof as input** (e.g., practice-problem answers/work), recorded for **later audit**.

The milestone ledger behaves like a checklist that only the judger can check, only with proof, and only ever append-only.

---

## 4. The curriculum DAG

### 4.1 Two-layer grounding
Ground **both** layers, not just one:

- **Structure layer (the DAG):** the topic set, prerequisite edges, and ordering are **derived from authoritative external structure**, not synthesized freely.
- **Assessment layer:** sourced problems/items attached to each node.

This converts the riskiest generative step (face #2) from "construct a curriculum" into "retrieve and reconcile authoritative structure."

### 4.2 Sourcing the structure (completeness anchoring)
Grounding **nests by granularity and weakens as it goes finer**:

- **Accreditation / degree requirements** → pins the **coarse** competency set against a real external standard. (This is what "physics major" *means*.)
- **Course catalogs + OpenCourseWare dependency chains (multiple programs)** → **intermediate** structure.
- **Textbook tables-of-contents + section learning objectives** → **fine** structure.

**Completeness is externally anchored at the top and becomes editorial judgment at the bottom**, which is exactly where **multi-source reconciliation** earns its keep. Reconciliation throws off a bonus signal: a topic appearing in *all* sampled programs is **consensus-core**; one appearing in *some* flags itself as **completeness-uncertain**. → **graded completeness confidence**, not binary, telling you where to spend review attention.

**Why not hand-author the DAG?** Because a DAG built from one incomplete human's knowledge bakes in *that human's omissions*, concentrated precisely in the upper-division material they never reached. Anchoring completeness to cross-program consensus is strictly better than anchoring it to one person. (This is why the originator — who reached junior year before leaving — should *verify*, not author; see §4.5 and §12.)

### 4.3 The DAG is the crown jewel
For the **full-degree** target, the universal DAG is **the single highest-value, highest-risk artifact** — build-once, improve-forever. Pour multi-source reconciliation and human/expert review into it. Everything downstream inherits its quality.

- **Versioning with migration.** Learners persist against the DAG for *hundreds of sessions*. This is the **database-schema-migration problem**: if a learner is 80 sessions into v1 and you ship v2 with a reordered module, you need a defined migration (does completed-node status remap? carry forward?) or you strand your most invested users. Easy to not notice you need it until someone's progress breaks.
- **Provenance stamping.** Each DAG records which sources/versions fed it and whether it has been human-reviewed or is **provisional**. Surface provisional status to the learner ("this curriculum hasn't been expert-reviewed yet") — honest, and lets a motivated self-learner calibrate trust.

### 4.4 Per-user projection (where personalization lives)
The per-user curriculum is a **projection** of the universal DAG, and the projection is a **safe, deterministic operation**:

- **Prerequisite-closed (downward-closed under the prereq relation).** Selecting a target node *mandatorily* pulls in its entire transitive prerequisite closure, or gaps re-enter through the back door. **Deterministically checkable.**
- **Subset-of-a-superset principle.** "Everything *you* need" is a subset of "everything *anyone* would need." Building the curriculum *entirely* around the user is dangerous (re-introduces omission/sycophancy/skipping); taking a **personalized subset of an all-encompassing curriculum** is safe.

**Where personalization actually lives** (less than it sounds for a fixed accredited target):
- **Entry pruning** — skip prereqs the learner can already demonstrate (this is most of the practical personalization; requires cold-start assessment, §11).
- **Elective/specialization selection** — upper-division branches.
- **Per-node depth & review intensity.**
The **core path is nearly invariant** because accreditation largely fixes the terminal competency set.

**Determinism vs adaptivity reconciled:** the curriculum is a **DAG with branch points**, not a forced line. **Determinism lives at the node-and-gate level** (each gate is fixed and mechanical); **adaptivity lives at the path level** (which branch, how much remediation, depth of review). This resolves the apparent tension between "static/deterministic curriculum" and "tailored to the learner."

### 4.5 Community curation (open-source maturation path)
Given the "free, open-source, motivated self-learners" framing, the natural and *safer* dynamic:
- **Lazy-generate** a provisional DAG on first request (bootstrap),
- **expert + peer review over time** promotes it toward canonical (maturation),
- the curated artifact is **shared** (structure + citations only — see §9 copyright constraint).

This turns the crown-jewel problem from "every instance regenerates and re-risks it" into "the community builds and hardens a few excellent DAGs once."

---

## 5. Grading

### 5.1 The partition (don't grade everything the same way)
"Open-ended" hides a large *gradeable* majority. Partition by how reliably each piece can be checked:

- **CAS oracle (deterministic, no model in the loop).** For the computational majority, a computer-algebra system (SymPy / Wolfram / Maxima) verifies final answers and often intermediate steps — symbolic equivalence, dimensional analysis, limiting-case behavior. **This sidesteps hallucination *and* sycophancy entirely for that subset.** Maximize this subset.
- **Reference-comparison LLM grading.** For structured-but-not-CAS-checkable work, grade **against a reference solution**, not de novo. Comparison is far more constrained than open evaluation.
- **Citation-gated learner self-adjudication.** For the genuinely open-ended residue (proofs, conceptual explanation, lab interpretation), the learner self-assesses but must **justify with textbook quotes**, and an LLM evaluates the *rationality of the argument* (§5.3).

### 5.2 Numeric template parameterization (the highest-leverage single mechanism)
Take a human-authored problem, **vary its numeric inputs**, and let the **CAS compute each variant's answer**. Payoffs:
- **Unlimited fresh problems** from a finite sourced set.
- **Deterministic answer keys** — which *dissolves the "textbooks ship only odd-numbered answers / no answers" problem*, the single most annoying practical gap, exactly at the surface (the answer key) you most need to be ground truth.
- **Lookup-resistance** — defeats the Goodhart trap that internet-famous problems have internet-famous answers a learner can copy.
Changing "5 kg" to "7 kg" is a far safer generative act than inventing a problem, and it is CAS-verifiable. **Push as much of the curriculum as possible onto this rail.** *(This rail is not speculative — it is exactly what STACK/Maxima has done in production for ~20 years; see §15.1/§15.5. Treat it as adopt-or-fork, not build-from-scratch.)*

### 5.3 Grading open-ended work (where the design's integrity concentrates)
**The training-data hedge is weak and partly counterproductive.** "Hope the problem was in the model's training data" conflates the model having *seen* a problem with the model *correctly evaluating a novel learner's attempt*. The learner's work is novel even when the problem is canonical; grading reliability is roughly independent of whether *this* problem was memorized. A model good at physics reasoning grades an unseen problem fine; a weak one misgrades a famous one. **Physics Stack Exchange and similar are actively risky here** — full of confident-but-wrong and contested answers, so "wide internet presence" correlates with "many conflicting takes in the training distribution," which can *degrade* grading on exactly the non-trivial problems. It also stacks a second streetlight effect (skewing toward famous paradoxes, away from the systematic grind that is most of a curriculum).

**The salvageable kernel:** prefer problems with **established canonical *reference solutions*** — not because the model grades them better, but because you can obtain a **trustworthy reference to grade against.** That is *reference availability*, not *model familiarity*.

**Mitigations for the open-ended residue (none rely on training-data presence):**
- **Rubric decomposition** — turn "is this derivation correct" into a list of narrow, individually-reliable checks ("invokes energy conservation," "Lagrangian signs correct," "dimensionally consistent," "reduces correctly as v→0"). Same advise-vs-block narrow-gate logic used elsewhere.
- **Reference-comparison** — grade against a known-correct solution, not from nothing.
- **Multi-sample with disagreement → escalate.** Grade N times / N framings; let disagreement **escalate to uncertainty/human review rather than silently pass.** *This is the key move:* it converts a silent wrong-pass into a detected "I'm not sure."
- **Adversarial framing** — prompt the judger to *find the flaw*; pass only if it cannot.
- **Confidence-gated human-in-the-loop fallback** — acceptable here. For a personal tool, **the learner is the human in the loop** and bears the cost of their own false pass, with real metacognitive benefit. Full autonomy on the hard residue is *not* a requirement; it's the part nobody has solved.

### 5.4 The citation-faithfulness gate (the integrity hinge of self-adjudication)
Requiring the learner to justify a self-assessment with textbook quotes, then having an LLM evaluate the *argument*, is genuinely strong — it **converts open-ended grading into a more constrained *verification* task** ("does this cited passage support this claim?"), and the learner *surfaces the reference*. It is also **pedagogically load-bearing**: articulating *why* an answer is right, grounded in source, is **retrieval practice + self-explanation**, two of the most evidence-backed learning mechanisms. The fallback becomes a feature.

**But this configuration is highly sycophancy-prone**, because a fluent, confident, well-structured justification that is *subtly wrong* is the worst case for argument-evaluation (models reward form), and the learner is an **adversary-by-incentive** (they want to pass). Two non-negotiable defenses:
1. **Verify the quote is real and says what's claimed *before* evaluating the argument.** Citation-faithfulness is itself a known hallucination point — learners will paraphrase a source into supporting something it doesn't, sometimes unknowingly. This check is **more deterministic** than argument evaluation and **gates** it: *no valid citation, no argument review.* Without this specific gate, you have built a machine that rewards eloquence.
2. **Give the evaluator the reference solution too** (where one exists), so it checks the argument **against ground truth**, not merely for internal coherence — which is exactly what a fluent-but-wrong justification has in abundance. Frame adversarially ("find the gap"), not agreeably ("does this seem right").

---

## 6. Gating & progression

### 6.1 Three gate types (the third is missing from naive designs)
1. **Per-node continuous gates** — proficiency on the current topic gates advancement. (The `nextTopic` → judger flow.)
2. **Reactive review** — if the learner is shaky on a prerequisite, trigger a detailed review in a **separate forked session** (§7).
3. **Cumulative module checkpoints** — periodically re-test an **entire DAG-module at once** (the midterm/final analog). **Not bureaucratic cruft:** this is the **proactive integrity check** that catches accumulated decay and false-passes *before* they cross a module boundary and compound. It is precisely why real programs have comprehensive exams. **Place cumulative gates at module boundaries** for proactive detection with **bounded latency**.

These make the claim "a false pass can always be reconciled later" *actually true* — without cumulative checkpoints, that claim is unfounded (see §6.2).

### 6.2 False-pass vs false-fail (the corrected asymmetry)
**Naive intuition (to be resisted):** "false fails are worse because a frustrated learner may never return, whereas a false pass can always be reconciled later."

**The correction:** the second half is the problem. In a design without full in-context memory, **detection is the expensive, unreliable thing — not the reconciling.** A false pass is **latent**: surfaced only when something downstream leans on it, and *diagnosing which* decayed/false-passed prerequisite is the culprit is itself fallible. So "always reconciled later" presumes the system reliably *notices and correctly attributes* an error it has no direct record of. A false fail, by contrast, is **loud and immediate** — the learner is right there, the signal unambiguous. **The naive view treats the loud-correctable error as dangerous and the silent-maybe-never-detected error as self-healing. That is backwards on detectability.**

**The reframe that dissolves the dilemma:** you are optimizing the wrong variable. The cost of a false fail is **not** the misgrade — it is **frustration-and-abandonment**, and that cost is set by **how the gate behaves on a borderline-but-failing attempt**, not by the pass/fail threshold. A gate that says *"not yet — your energy step is missing this term, look at §4.3 and try the variant"* costs almost nothing emotionally even when it's a false fail, because it reads as **teaching, not rejection.** The threshold question and the abandonment question are **separable**, and the naive view fuses them.

**Therefore:** tune for **diagnostic, encouraging, low-stakes-retry gate behavior** (unlimited friendly retries, specific actionable feedback, never a verdict-with-no-recourse) at the **interaction layer**, and you can then afford to set the **threshold stricter** than instinct suggests — which protects against the genuinely dangerous silent-compounding case. Borrow mastery learning's stance: **failing a gate is the default expected state of learning, not a punishment** — you simply haven't finished the topic yet.

**Decision:** keep the threshold **variable** (tune on real data), but **do not enter data collection believing false-fails are the thing to minimize at the threshold.** Minimize **abandonment at the interaction layer**; let the **threshold lean strict.** (Cumulative checkpoints, §6.1, are what make strict-threshold-plus-latent-error-recovery coherent.)

---

## 7. Memory & state

**Stance:** the earlier "don't always reference a giant memory tree" was about **context bloat** (and the hallucinations/overlooking that bloat causes), **not** anti-memory sentiment. There **should** be a thorough knowledge-tracking memory system. It simply must **never be loaded in full into a learning session**, and only the **minimal most-relevant parts** should enter context.

**Deterministic, graph-structured retrieval (not semantic search).** *How* "minimal relevant parts" is selected is itself a failure surface — a retrieval miss runs the session blind to relevant history. **Do not use embedding/semantic search if avoidable.** The DAG already provides a **deterministic relevance criterion**: pull state for the **current node and its immediate prerequisite/successor neighborhood by graph adjacency.** This trades context-bloat for retrieval-miss and then **minimizes** the retrieval-miss by structuring retrieval on the graph.

**Spaced repetition.** Include a spaced-repetition system, FIRe-style ("Fractional Implicit Repetition" — reviewing an advanced topic implicitly reviews its prerequisites; propagate "trickle-down" credit through the **same prereq graph**). This is the mechanism that addresses **forgetting**, which the naive "reached X ⇒ knows prerequisites" assumption ignores. Forgetting is real and large over months-long timelines; the prerequisite assumption is only safe *with* review.

**Failure localization.** When a learner stalls on topic Y, the system must distinguish "Y is genuinely hard" from "prereq Z decayed or was false-passed." A lightweight per-topic state (last-passed timestamp + score) plus the shaky-prereq trigger provides this diagnostic — the safety net for gate errors. **Shaky prerequisite → fork a separate session that reviews the memory tree in detail** for the implicated region (the detailed review happens *off* the main learning context).

**Storage architecture — event sourcing with three distinct stores.** The valuable property the design already requires (proofs "audited later"; curriculum + ledger immutable) is an **immutable audit trail** ⇒ **event-sourcing**: an **append-only event log**, with the knowledge state as a **derived projection** folded from events (giving replay + time-travel to any past state, and a clean split between "what happened" and "current mastery"). Keep **three stores distinct** because they have different immutability needs:
1. **Curriculum** — immutable per version.
2. **Knowledge projection** — append-derived view.
3. **Session transcripts** — append-only audit log.
The judger reads milestones from (1) and a *slice* of current-topic work from (3), and writes checkmarks to (2).

**Forks emit, don't merge (decided).** Review forks **emit events** ("reviewed T, outcome O") but do **not merge their details back into the trunk** — the trunk only needs to know the review happened successfully, not its contents (avoids context bloat). **Therefore an event log suffices; true tree/branch-merge semantics are not needed.** *Caveat for a future session:* do **not** adopt tree complexity reflexively because a coding agent (e.g. Pi) stores sessions as trees — that case branches into **speculative edits that get discarded**, a different access pattern than read-only review side-quests. (This is reasoning about architecture, not an assertion about any agent's internals.) Reserve branch/merge only if genuinely divergent, mergeable curriculum *paths* ever become a requirement.

**Input → log.** When handwriting input is added (later; §12), the **corrected-and-confirmed transcription** enters the append-only log — **never the raw image** — so an OCR misread can never silently become part of the audit trail.

---

## 8. Integrity, decorrelation & validation

**Decorrelation is about inputs and objective, not model identity.** "Use a decorrelated model for the judger" is **aspirational** — two models trained on overlapping web corpora **share failure modes** (the same wrong physics common online, the same sycophancy gradients). A different model *reduces* correlation; it does not remove it. **The decorrelation you can actually bank on is already designed in:** the judger sees **different inputs** (lean, work-only) and has a **different objective** (falsify mastery, not help). Lean on **input-and-objective decorrelation** as the real mechanism; treat **model-identity as a minor bonus.**

**Goodhart / teaching-to-the-test.** If the professor knows the judger's exact rubric, it can coach the learner to trip the checkboxes without understanding. Defenses: (a) keep some **separation** between what the professor sees and what the judger checks, and/or (b) make the milestone pool **rich and sampled** enough that **gaming it ≈ learning it** (numeric parameterization, §5.2, directly supports this).

**Audit with teeth (but it is QC, not a guarantee).** Random-sample the `confirmMilestone` proofs; use **judger-vs-audit disagreement to recalibrate.** Be clear-eyed: **"audited later by another LLM" is infinite regress** — the only true ground truth in the audit is a **human or a CAS**, so the audit is a **sampling/QC mechanism, not a guarantee.**

**Determinism is a multiplier, not a virtue in itself.** Deterministically executing an LLM-generated curriculum means **faithfully executing whatever flaws the curriculum has, identically, for every user.** ⇒ **curriculum QA is the whole game.** Good news: much of it is **deterministically checkable** before any learner touches it —
- prereq graph is **acyclic**;
- every node **reachable** from entry;
- the **terminal** ("physics major") reachable;
- every gate's milestones **covered by upstream nodes**;
- every milestone has **≥1 sourced item with a sourced-or-CAS-verifiable answer**;
- **no orphan nodes**;
- (v1 specifically) **every textbook learning objective maps to a node** — completeness as a mechanical coverage check.
This catches a whole class of structural hallucinations **for free**. What is *not* deterministically checkable (true completeness, pedagogical ordering quality) is where human/expert/multi-model review is spent.

**Meta-Goodhart (the hazard hanging over the whole project).** The entire edifice can silently drift from *"physics-major-equivalent"* to *"passes my own generated gates."* You **cannot verify introspectively** that finishing the harness confers the claimed equivalence — it needs an **external standard.** **Design toward a measurable external benchmark from day one** (e.g., does completing a module predict performance on the **GRE Physics subject test** or a real qualifying exam?). This is both the **north-star metric** and the **honesty check** against drift.

---

## 9. Copyright & sourcing

**The legal framing must be honest (one earlier claim was wrong).** "We don't host the content and don't make money, therefore we're absolved of liability" is **overstated**:
- Non-commercial use is **one fair-use factor, not immunity** (Napster was free).
- A tool can incur **contributory or inducement liability without hosting any content** if designed/marketed primarily to infringe (the Grokster line).

**Honest characterization of the user-supplies-their-own-copy model:** not "absolved of liability," but **"low enforcement risk, with a plausible personal-use / format-shift posture *for the user*."** The emulator/ROM precedent is real (emulators are legal; the user supplies the ROM they own; personal format-shifting is well-established). The rhythm-game-community norm survives on **non-enforcement and obscurity**, not a clean legal theory — hold that distinction honestly. *(Not legal advice; this is the landscape. The call is the originator's.)*

**The architectural constraint that makes the hybrid sound:** **shareable artifacts must contain only structure and citations/locators — never copyrighted content.** An open-source learning tool will *want* curriculum-sharing, and a curriculum with **embedded** sourced problems is exactly the artifact people would swap — at which point the project becomes a **redistribution vector** and the personal-copy defense evaporates. So:
- The shareable curriculum stores **locators** ("Griffiths 3e, problem 2.12"; "OCW 8.04, PS3, Q2").
- The problem text is **rehydrated locally** from each user's own copy **at runtime**, never embedded in the shared file.
- **Structure travels; content stays local and per-user.**
This keeps the open-licensed default fully shareable, isolates copyrighted material to machines whose owners supplied it, and is a cleaner separation anyway (same structure binds to different editions).

**Sourcing posture:**
- **Default: open-licensed only.** **OpenStax** (e.g., *University Physics* — CC BY, ships end-of-chapter problems with *selected* answers; strong spine candidate). **MIT OCW** (generally **CC BY-NC-SA** — usable with attribution, but **NC and share-alike bite the moment you productize**).
- **Hybrid (accepted):** open-licensed by default; if the user **procures non-open sources themselves**, the system uses them **without asking questions** — the user takes on the copyright risk. Given the structure/locators-only sharing constraint, this makes the posture *stronger*, not weaker.
- **Verify each source's exact license before building on it.** The "all testable info is verbatim-sourced" rule collides with "I have the right to store and serve it"; open licensing resolves it without quietly violating the no-generation rule.

---

## 10. Scope (honest boundaries)

"Physics-major-equivalence" is fuzzy; the achievable slice is **narrower than a degree**, and this must be named so *"make me a physics major"* doesn't quietly overpromise.

- **CAN plausibly deliver:** the **lecture-and-problem-set knowledge** of a physics major.
- **CANNOT deliver:** experimental/lab competence (not assessable via quoted problems), genuine research skill, or the deepest open-ended problem-solving where gating breaks down.

Still enormously valuable — but the boundary is structural, not a temporary limitation.

---

## 11. Cold start

"Skip what they already know" (entry pruning, §4.4) requires **assessing incoming knowledge across the whole DAG at entry** — the same open-ended grading problem, **all at once, with no prior state.** ALEKS spends ~25–30 adaptive items locating a student's knowledge state among many; **an analog is needed.** A bad placement either **bores** the learner through known material or **drops** them into a gap. This is an explicit subproblem to design (and an argument for making the cold-start assessment itself lean on CAS-checkable items where possible).

---

## 12. The v1 build slice (the concrete plan)

**Principle:** the design's total surface area (reconciliation pipeline + CAS-grading layer + three-context MCP orchestration + memory/event-store + cold-start + …) is large enough to **never ship** if built all at once. **Build the smallest end-to-end slice that exercises the core thesis, and only that.** If the thin slice doesn't produce real learning, nothing else matters; if it does, every deferred piece is an **extension of a working spine** rather than a bet.

**The slice (amended through discussion):**
- **Content:** **OpenStax *University Physics* Vol. 1** — fully **CC BY**, so **zero copyright complexity** for v1.
- **DAG construction — *extract-and-verify*, not hand-author and not the full reconciliation pipeline:**
  - Extract the DAG from the book's **table-of-contents + section-level learning objectives** ("by the end of this section you will be able to…"), which is a **human-authored completeness specification for the book's scope.** Chapter/section structure = first-pass topic hierarchy; linear reading order = most of the prerequisite graph.
  - **The only real generative act** that remains is: **cluster the learning objectives into gateable nodes** and **propose the non-linear cross-edges** (e.g., rotational kinetic energy depending on *both* energy *and* rotation). The originator is **content to verify model-proposed edges at this stage** (verification they are well-suited for at this level).
  - **Completeness check is deterministic:** every learning objective maps to a node, or it doesn't — verified mechanically. **Plus one manual cross-source diff** of the TOC against the **MIT 8.01 syllabus** (or Halliday) — an afternoon, not a pipeline.
  - **Why extract-and-verify, not the pipeline, for v1:** intro mechanics is **the most standardized content in all of physics pedagogy** — essentially no genuine disagreement about what belongs. The reconciliation pipeline exists to resolve completeness where it is *contested* (the upper division); pointed at intro mechanics it is heavy machinery solving a problem this slice barely has. **The crown-jewel argument holds for the full degree and dies for the v1 cut.** Extract-and-verify also routes *around* the one thing human verification is bad at — **omission-blindness** — by borrowing the textbook's *own* definition of complete (its LOs). And it keeps the largest sub-project (the pipeline, the genuine never-ship risk) **off the critical path to first light**, so a v1 stall is unambiguously a spine problem, not a pipeline problem.
- **Grading:** **CAS-graded numeric-template problems only.** **Skip the open-ended residue entirely for v1** (defer reference-comparison grading and citation-gated self-adjudication). *(Adopt or fork STACK/Maxima for this rail rather than building it; see §15.5–§15.6.)*
- **Architecture:** the **three-context separation** (curriculum-gen / professor / judger) end-to-end.
- **Gating:** per-node gates + a **cumulative checkpoint at the end** of the volume. Spaced review across sessions.
- **Deferred to later versions:** the reconciliation pipeline (→ **v2**, *debugged on this same forgiving intro/early-intermediate regime where the originator's verification is most reliable*), the copyright hybrid, the handwriting input layer, and the hardest grading residue.

**What v1 proves:** *separated grading + deterministic gating + sourced assessment + spaced review across sessions*, end-to-end, with **everything the spine doesn't need deferred.**

**The verification gradient (why this sequencing honors the originator's strength).** Human verification is strong against **errors of commission** (a wrong edge, a misstated topic) and **nearly blind to errors of omission** (noticing something is missing requires already holding the complete set to diff against — exactly what nobody has, and what a junior-year-level background has *least* of in the upper division). The originator's verification reliability is **strongest at v1's level and degrades exactly as the material climbs toward where they left off.** So human-verification is most justified **now**, and the reconciliation pipeline **earns its necessity precisely where the human check runs out** (upper division). They are **complementary across the curriculum, not competing for the v1 slot.**

---

## 13. Recurring design principles (the meta-patterns)

A future session can use these as a compression of the whole philosophy:

1. **Separate deciding-what-to-teach from teaching.** Authority over progression never sits with the rapport-holding tutor.
2. **Ground structure, not just content.** Two-layer grounding. Omission is the invisible, dominant risk.
3. **Put ground truth in a human/deterministic source; let the LLM *advise*, not *gate*.** Wherever a consequential decision can be made by a deterministic policy (CAS, graph check, immutable ledger), it should be. The LLM owns high-variance generation (explanation, hints, item *variants*), never coverage or final authority.
4. **Decorrelate by inputs and objective, not by model identity.**
5. **Convert open evaluation into constrained verification** (reference-comparison; citation-faithfulness; rubric decomposition).
6. **Make silent errors loud.** Multi-sample → escalate; cumulative checkpoints; failure localization. A detected "unsure" is infinitely better than a silent wrong-pass.
7. **Exploit determinism as QA.** Faithful execution makes pre-flight mechanical checks high-leverage.
8. **Separate the threshold question from the experience question.** Strict gates + gentle, diagnostic, low-stakes-retry behavior.
9. **Validate against an external standard, never against your own gates.** Guard the meta-Goodhart.
10. **Ship the thinnest spine; defer everything the spine doesn't need.**
11. **Don't attribute guarantees to transport (MCP).** Guarantees come from authority + immutability.
12. **Be honest about scope and about law.** Name what the architecture structurally cannot do; characterize legal risk accurately rather than wishfully.

---

## 14. Open / deferred decisions

- **Gate thresholds** — left variable, tuned on real data (§6.2). Default posture: lean strict, soften the *experience*.
- **Cold-start placement assessment** — design pending (§11).
- **Full open-ended grading reliability** — deferred past v1; the hard residue is acknowledged as not-fully-solved by anyone (§5.3).
- **DAG versioning/migration mechanics** — needed before the *second* curriculum version ships (§4.3).
- **The full tool surface** — only `nextTopic` and `confirmMilestone` sketched; many more needed (§3).
- **Reconciliation pipeline design** — v2; debugged on intro/early-intermediate physics (§12).
- **Hybrid-source UX and the exact "user procures their own copy" flow** — pending (§9).

---

## 15. Research findings: known vs unknown efficacy, related work, forkable components

> *(Populated by a dedicated breadth-first research pass after §1–14 were written. §1–14 are deliberately left untouched ("pristine synthesis") to honor the anti-drift intent; all research-derived updates live here and cross-reference the sections they modify. Goals of the pass: (a) is each idea's efficacy known or unknown; (b) ideas we missed; (c) open-source projects to use or fork.)*

**Headline: the design is unusually well-aligned with the evidence.** Almost every mitigation we proposed maps to a *documented, named* failure mode it defends against, and several architectural choices independently match emerging best practice. The genuinely novel/unproven part is narrow and identifiable, and much of the system is **integration of existing forkable parts rather than invention.**

### 15.1 What is empirically KNOWN (validated)

**Mastery-based progression works — but the famous number is a myth.** Bloom's "2 sigma" is not a robust finding (it traces to two small 1984 dissertations); mastery learning's real, replicated effect is ~0.5σ (Kulik, Kulik & Bangert-Drowns 1990, d≈0.5). Modern tutoring meta-analysis (Nickow, Oreopoulos & Quan 2020) found average tutoring effect ≈0.37σ, with **none of 96 studies reaching 2σ**. *Adjustment:* pitch the project's expected gain as ~0.5σ, not 2σ — still very large for something scalable.

**ITS rivals human tutoring; step-based beats answer-based.** VanLehn 2011 (human tutoring d≈0.79 — itself far below the mythical 2.0; step-based ITS d≈0.76); Ma et al. 2014 (ITS vs large-group g≈0.42; ITS vs individual human tutoring not significant); Kulik & Fletcher 2016 (median 0.66). Implications: (1) the separated-tutor architecture has strong precedent; (2) **tutors that engage intermediate *steps* outperform answer-only tutors** — a mild tension with v1's CAS-final-answer grading and an argument to check derivation *steps* (which CAS step-checking and rubric decomposition both enable) beyond v1. **Critical caveat that validates our external-benchmark insistence (§8):** Kulik & Fletcher found ITS gains *much larger on locally-developed tests than on standardized tests* — systems look better on assessments aligned to their own objectives. **That is the meta-Goodhart, measured in the wild.** It is why GRE-Physics-style external validation is non-negotiable.

**Structured AI tutoring beats strong classroom instruction for intro physics (RCT).** Kestin et al. 2025 (*Scientific Reports*), ~194 Harvard students, intro physics (PS2), within-subject crossover: a custom AI tutor (**GPT-4 + expert-authored scaffolds + anti-hallucination guardrails**) produced roughly 2× the learning gains of strong active-learning instruction, in less time, with higher engagement. Confirms two things: (a) the win came from *scaffolding + guardrails*, not raw LLM — **our central thesis**; (b) the authors *explicitly disclaim* higher-order synthesis and long-term retention — the RCT validates exactly v1's regime (intro, structured, "middle-order" Bloom levels) and is cautious precisely where we flagged the hard residue. Fully consistent with our scope (§10).

**Retrieval practice and spaced practice are robust** (grounds self-adjudication §5.4 and spaced review §7). Testing effect: g≈0.50 (Rowland 2014; 159 studies, 81% favor retrieval) to ≈0.70 (Adesope et al. 2017). Transfer: d≈0.40 (Pan & Rickard 2018). Self-explanation is also well-supported (Bisra et al. 2018, g≈0.55). **Honest caveat:** retrieval-practice benefits are *weaker and less consistent for procedural problem-solving transfer* than for factual/conceptual retention — and physics is procedure-heavy. So spaced review will solidly aid retention; its boost to *novel problem-solving transfer* is more modest.

**CAS-based assessment with randomized variants is mature, proven tech — not speculative.** **STACK** (System for Teaching and Assessment using a Computer algebra Kernel; C. Sangwin; GPL; GitHub `maths/moodle-qtype_stack`) has for ~20 years done *exactly* the §5.2 rail: randomized question variants from structured templates, CAS (Maxima) answer-testing for **algebraic equivalence, numerical tolerance, dimensional analysis, and significant figures**, multi-part questions, and "potential response trees" mapping answer properties to diagnostic feedback. It is used for physics (e.g. thermodynamics, mechanics). STACK's own docs independently note randomization makes online answer-lookup **nearly impossible** — our lookup-resistance claim, confirmed in practice. **Maxima runs offline in a sandbox (no Moodle needed).** *Adjustment:* the v1 grading layer is **largely solved engineering** — adopt STACK question banks / Maxima answer-tests, or fork the answer-test logic. The novel part of the project is *not* the grading rail.

**LLM-assisted curriculum/prereq extraction with human verification is the field-standard approach, with error rates in the range our plan assumes.** Auto-HKG (high-school math): concept extraction ~90% accurate (fine-grained), ~75% (coarse-grained), manually verified. Multiple systems (LLM-assisted curriculum-KG completion; ACE) use LLM-proposes/expert-verifies — exactly our extract-and-verify (§12). **Prerequisite-edge extraction is consistently the harder sub-task** (its own subfield: LectureBank; graph autoencoders), confirming the originator should concentrate verification on the non-linear cross-edges. KG-grounding measurably cuts hallucination (~54% RAG-accuracy gain, Gartner-cited). Schema versioning/migration is a *named* open problem — validating §4.3.

**Grounding is necessary; "no grounding" fails hard.** Without RAG, even GPT-4 answers only ~⅓ of university STEM exam questions correctly (Extance 2023). Validates the whole two-layer-grounding thesis.

### 15.2 LLM-as-judge: every one of our mitigations defends a NAMED bias
The 2024–2026 LLM-as-judge literature is the most striking alignment in the whole pass. Documented bias → the mitigation we already specified:
- **Authority bias — judges favor answers containing citations *even when the citations are fabricated*** (Chen et al. 2024). → exactly why §5.4's **citation-faithfulness gate must verify the quote is real and on-point *before* evaluating the argument.** Our instinct defends a named, measured failure.
- **Leniency bias — judges score leniently** (Thakur et al. 2025). → grading-sycophancy is real; validates strict threshold (§6.2) + **adversarial "find the flaw" framing**.
- **Fluency/verbosity/format bias — longer, well-formatted, fluent answers favored over factual ones.** → validates "fluent-but-wrong is the worst case" (§5.4); defend via reference-comparison + decomposition.
- **Self-enhancement/egocentric bias — models rate their *own* outputs higher.** → a real reason to prefer a *different* model for the judger after all (mild support for model-identity decorrelation, atop the input/objective decorrelation that does the heavy lifting, §8).
- **Low test-retest reliability / self-consistency** — identical input + rubric, different verdicts on resampling. → validates **multi-sample → escalate** (§5.3): sampling the variance to *detect* uncertainty is exactly right.
- **Only the largest models align reasonably with human graders, and even they are prompt-sensitive and lenient** (Thakur et al.). → small *local* models may be unreliable judges; capability matters; hybrid human-in-the-loop is "essential for high-fidelity/domain-critical" tasks (validates the confidence-gated fallback §5.3).
- **Rubrics help** — structured/instance-specific rubrics + CoT raise human correlation (G-Eval; Prometheus; HealthBench, with 48k physician-authored *instance-specific* criteria). → validates per-milestone **rubric decomposition** (§5.3); HealthBench is the gold-standard pattern to emulate.

**Net:** even with all mitigations, LLM grading of open-ended work has irreducible reliability limits. This *confirms* the decisions to (a) maximize the CAS-deterministic fraction, (b) defer the open-ended residue past v1, and (c) fall back to citation-gated learner self-adjudication. **Do not claim open-ended autonomous grading is solved — nobody has.**

### 15.3 Active research on our exact central question
Whether LLMs *actually model a learner's knowledge* when choosing what to teach — versus using heuristics — is an *open* question (e.g., Harootonian & Griffiths, "Do LLMs Mentalize When They Teach?", testing whether teacher-LLMs do inverse-planning over learner state or fall back on rules of thumb). The premise behind separating the what-to-teach decision from the LLM (§1) is precisely what this literature is probing. Its being unresolved is corroboration that trusting an in-context LLM to *own* coverage is not safe.

### 15.4 Ideas we had not fully considered (adopt)
- **Potential-response-tree feedback** (STACK): structured mapping of *which property* a wrong answer has → *specific* diagnostic feedback. Directly serves the "diagnostic, encouraging gate behavior" of §6.2. Adopt for gate feedback.
- **Difficulty-calibrated item selection** (DeepTutor; ITS "difficulty selection"; IRT): choose item difficulty against estimated ability. Complements mastery gating.
- **Instance-specific rubrics** (HealthBench): per-item rubrics rather than one global rubric — the rigorous form of §5.3 decomposition.
- **Groundedness-vs-preference tradeoff (caution):** learners *prefer* responses that are **not** maximally textbook-grounded (math-QA RAG study); over-grounding feels worse even when more accurate. → tension with the §2 face-#4 mitigation. *Resolution:* ground the *substance and assessment* strictly, but give the professor **stylistic latitude in explanation** (grounded-but-not-stilted). Watch in UX.
- **LLM self-correction is unreliable** (Huang et al., "LLMs Cannot Self-Correct Reasoning Yet"): intrinsic self-critique often fails to fix reasoning errors absent external feedback. → do **not** rely on the judger "double-checking itself"; rely on **independent inputs + reference comparison + CAS** as the external signal. Reinforces §8.

### 15.5 Forkable / studyable prior systems (ranked by relevance)
- **DeepTutor** (HKUDS; `github.com/HKUDS/DeepTutor`; ~20k★, very actively developed, Docker, multi-provider): "fully open-source agentic framework unifying **citation-grounded** problem tutoring with **difficulty-calibrated question generation**," coupling **static knowledge grounding with dynamic learner memory** over **university-level curricula**. The closest existing system to our design. Ships **TutorBench** (interactive benchmark; learner profiles; 5 domains) — a candidate external eval. *Differences:* it *generates* questions (vs strict sourcing) and lacks deterministic-DAG gating, a separated adversarial judger, and a CAS rail. **Action: study deeply; fork components (citation grounding, learner-memory substrate); benchmark against TutorBench.**
- **STACK** (`maths/moodle-qtype_stack`; GPL): the CAS grading rail (§15.1). **Action: adopt question banks / Maxima answer-tests, or fork the answer-test logic for the v1 grader.**
- **OATutor** (Berkeley; Pardos et al., CHI 2023): open-source adaptive tutoring system + **curated content library**, built for learning-sciences research. **Action: study its content-library structure and adaptivity model.**
- **OpenTutor** (`zijinz456/OpenTutor`): FastAPI + Next.js; **BKT** mastery, **FSRS** spaced repetition, hybrid BM25+vector RAG, 3 agents, grounded in uploaded material; smaller/solo project. **Action: fork the FSRS scheduler and BKT implementation; reference the block architecture.**
- **Open TutorAI** (arXiv 2602.07176): OpenWebUI-based; RAG over educator-curated + user docs (hybrid corpus matching §9); planned LO→content knowledge graph. Research-grade. **Action: reference the hybrid-corpus pattern.**
- Also noted: **CurriculumTutor** (AIED 2022, adaptive curriculum-mastery algorithm); an existing **Claude Code skill** AI tutor with spaced repetition (relevant since the build target is Claude Code).

**Strategic read:** no existing system combines (a) strict-sourced assessment, (b) deterministic DAG gating with a separated *adversarial* judger, (c) a CAS-deterministic grading rail, and (d) build-once community-curated curricula. **That combination is the project's novel contribution.** But the grading rail (STACK), spaced repetition + BKT (OpenTutor/FSRS), citation-grounded tutoring + learner memory (DeepTutor), and curated content libraries (OATutor) **already exist as forkable parts.** *The build is more integration than invention* — which de-risks it and argues for forking aggressively rather than greenfielding.

### 15.6 Net adjustments to the design (cross-referenced)
1. Pitch outcomes as **~0.5σ mastery-learning + structured-AI-tutor gains**, not "2 sigma." (→ §1)
2. Treat the **CAS grading rail as adopt-not-build** — fork STACK/Maxima. (→ §5.2, §12)
3. **Fork aggressively** (DeepTutor, STACK, OpenTutor, OATutor) rather than greenfield. (→ §12, §13-#10)
4. Add **potential-response-tree-style diagnostic feedback** to gates. (→ §6.2)
5. Plan to **engage derivation steps**, not just final answers, beyond v1 (step-based > answer-based). (→ §5, §6)
6. Give the professor **stylistic latitude** in explanation while keeping substance/assessment strictly grounded. (→ §2 face-#4, §9)
7. Adopt **TutorBench** now and design toward **GRE-Physics** as external validation — reinforcing the meta-Goodhart guard. (→ §8, §11)
8. **Do not rely on judger self-correction**; rely on independent inputs + reference + CAS. (→ §8)
9. Reconfirmed unchanged by evidence: two-layer grounding, separated contexts, deterministic gating, three gate types, event-sourced state, prerequisite-closed projection, copyright structure/locators-only sharing, scope boundary. (→ §2–§12)
