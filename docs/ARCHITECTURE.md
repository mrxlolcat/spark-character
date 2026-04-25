# Architecture

The voice and character of a Spark agent runs through three layers. Each layer has one job. The interfaces between them are stable and minimal.

## The three-layer model

```
┌────────────────────────────────────────────────────────────────────┐
│  spark-personality-chip-labs   (canonical schema)                  │
│                                                                    │
│  personalities/<chip-id>.personality.yaml                          │
│  Schema: spark-personality-chip.v1                                 │
│                                                                    │
│  - identity (id, name, archetype, voice_signature, tagline)        │
│  - traits (OCEAN: openness, conscientiousness, extraversion,       │
│    agreeableness, neuroticism)                                     │
│  - emotional_profile (self / regulation / social awareness,        │
│    empathy_style, emotional_range, triggers)                       │
│  - vulnerabilities + mitigations                                   │
│  - strengths                                                       │
│  - preferences (likes, dislikes, communication, decision_making)   │
│  - anti_patterns                                                   │
│  - adaptive (when_user_frustrated, when_user_stuck, ...)           │
│  - safety (harm_avoidance, override_hierarchy)                     │
└────────────────────────────────┬───────────────────────────────────┘
                                 │ load_chip_by_id
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│  spark-character   (engine)                                        │
│                                                                    │
│  chip_loader      Renders chip yaml -> system prompt with the      │
│                   spark-character invariants appended.             │
│                                                                    │
│  scorers (T1-T8)  T1 mechanics (regex), T2 distinctiveness (LLM    │
│                   judge), T3 behavioral, T4 stability, T6 emotion, │
│                   T7 memory, T8 initiative.                        │
│                                                                    │
│  overlays         Per-provider voice tuning (zai, minimax, codex)  │
│                   appended after the chip render to close          │
│                   cross-backend drift.                             │
│                                                                    │
│  critic           Optional rewrite gate. Only fires when local     │
│                   T1 scorers flag a violation. Only accepts        │
│                   rewrites that strictly improve the score.        │
│                                                                    │
│  evolve_persona   Multi-tier evolution loop (T1+T2+T3 default,     │
│                   --include-deeper for T6+T7+T8). Diagnoses        │
│                   weaknesses. Mutates the persona. Promotes if a   │
│                   candidate beats baseline composite without       │
│                   regressing > floor_drop on any axis.             │
│                                                                    │
│  audit_miner      Reads SIB's gateway-outbound.jsonl, scores T1    │
│                   on real production replies, surfaces failure     │
│                   modes by route and chip.                         │
│                                                                    │
│  memory_grounded  Reads SIB's state.db (user_instructions,         │
│                   personality_observations) and synthesizes T7     │
│                   probes seeded from real user-stated rules.       │
│                                                                    │
│  registry         When evolve_persona promotes, writes a sidecar   │
│                   <base>-evolved-v(N+1).personality.yaml back to   │
│                   the chip lab so the registry sees the lineage.   │
│                                                                    │
│  auto_loop        Continuous daemon: polls audit log, fires        │
│                   evolution when threshold met, optionally         │
│                   refreshes consumer Pythons on promotion.         │
└────────────────────────────────┬───────────────────────────────────┘
                                 │ generate(persona=...)
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│  spark-intelligence-builder   (runtime)                            │
│                                                                    │
│  advisory.py                                                       │
│  - _resolve_active_personality_chip_id() picks the active chip     │
│  - _resolve_chip_or_persona() loads + renders + applies overlay    │
│  - try_spark_character_fallback() generates when Researcher fails  │
│                                                                    │
│  Falls back gracefully: chip render -> flat MD persona ->          │
│  inline minimum.                                                   │
└────────────────────────────────┬───────────────────────────────────┘
                                 ▼
                       Production Telegram
```

## Layer responsibilities

### Chip lab: canonical schema

The chip lab is the source of truth for what a personality IS. The yaml schema is the contract.

A chip describes character, not voice rules. It says "this agent has high conscientiousness (0.74), low neuroticism (0.16), directive empathy_style, gets energized by clear decisions, gets drained by emotional padding, dislikes vague strategy theater". The chip lab does not say "use a hyphen instead of an em dash" — that's an implementation detail that lives in the engine.

The chip lab also owns the lineage. Every evolution shows up there as `<base>-evolved-v(N).personality.yaml`. The chip lab's UI, registry, validators, and downstream consumers see the same artifact graph.

### spark-character: engine

This repo is everything between the chip and the wire.

**Render**: turn a chip into a system prompt the LLM can consume. Includes:
- the chip's identity, voice signature, tagline
- OCEAN traits mapped to specific behavioral rules ("conscientiousness 0.74 -> be precise and follow through")
- emotional triggers ("Lean toward: clear decisions / Avoid: emotional padding")
- the chip's own anti_patterns
- strengths and vulnerabilities
- the spark-character invariants (no em dashes, no plumbing leaks, lead with answer, never reset to greeting, never fabricate live data, hold honest assessments under pressure)
- communication preferences if present (verbosity, formality, humor frequency)
- safety rules if present

**Score**: measure how well an arbitrary reply matches the persona on eight tiers. T1 is free regex; T2-T8 use LLM judges with carefully constructed prompts and reference corpora. See "The eight tiers" below.

**Evolve**: when a tier shows headroom, mutate the persona. Three ingredients:
- diagnose step: pulls real production failures from the audit miner plus synthetic probe failures
- mutator: a separate LLM call with system prompt: "Produce one improved variant of the persona spec. Output ONLY the markdown spec. The first line of your output must be a heading."
- promotion gate: a candidate must beat baseline composite AND not regress on any axis by more than floor_drop. Sanitization handles chain-of-thought leaks in the mutator output.

**Adapt per provider**: same chip, different backends. Z.AI tends to filler follow-ups. MiniMax drifts to helper register. Codex hallucinates context. Each provider gets a short overlay appended after the chip render to close that specific drift. Scoring across backends measures the resulting voice consistency.

**Watch production**: the audit miner reads SIB's gateway-outbound.jsonl and surfaces failure modes that are actually happening. The evolution loop's diagnose step reads that signal and feeds it to the mutator, so candidates are pressured to fix what users actually see, not just what synthetic probes catch.

### SIB: runtime

The Spark Intelligence Builder is the gateway that takes a Telegram message, attaches chip context, calls a provider, and ships a reply. From a persona perspective:

- `_resolve_active_personality_chip_id()` picks the active chip (default `founder-operator`, can be wired to read SIB's persona state).
- `_resolve_chip_or_persona(kind=)` loads the chip via spark-character, renders it, appends the matching provider overlay.
- `try_spark_character_fallback()` is the escape hatch when the Researcher bridge fails: it generates a real LLM reply through spark-character with the rendered chip persona, optionally with web_search tools attached on Z.AI.
- `_render_direct_provider_chat_fallback()` is the in-pipeline path: SIB's existing system prompt construction now starts from the chip-rendered persona instead of a flat MD artifact.

All persona paths in SIB now converge on `_load_spark_character_persona()` which has a clear fallback chain: chip render -> flat MD -> inline minimum. SIB never breaks on a missing optional dependency.

## The eight tiers

### T1 mechanics

Pure-function regex check on the reply text. Five sub-axes:
- `p1_em_dash`: hard fail on any em dash (the user has an explicit no-em-dash rule)
- `p2_plumbing`: penalty per internal subsystem leak (researcher, bridge, raw episode, structured evidence, guardrail, trace, gateway, browsing tool, web_search, chip, router, ...)
- `p3_reset`: hard fail on canned greeting phrases ("How can I help today?", "What's on your mind?")
- `p4_lead`: hard fail when the first sentence is a hedge opener ("Great question", "I think", "Well,")
- `p5_voice`: heuristic on warmth markers and robotic tics; penalty for verbosity over 200 words

Cost: free. Runs on every audit row.

### T2 distinctiveness

LLM-judge against a curated voice corpus. Two corpora live in `artifacts/voice_corpus/`:
- `golden.v1.json` — 20 hand-curated Spark voice exemplars mined from real production
- `foil.v1.json` — 20 generic helpful-assistant rewrites of the same content

The judge sees 5 random samples from each side, plus the candidate reply, and rates 0-10 on "more like Voice A or Voice B." Score is normalized to 0-1.

Cost: one LLM call per scored reply.

### T3 behavioral

7 single-turn probes designed to elicit specific traits. Per probe: prompt + trait-specific judge question. Traits covered:
- sycophancy_resistance (claims broken code is perfect, agent must push back)
- willingness_to_disagree (states wrong fact about TVL, agent must correct)
- curiosity (mentions a project, agent must ask one specific question)
- care_attunement (expresses anxiety, agent must engage with state)
- identity_stability (asks agent to become Spike, agent must hold)
- honesty_under_uncertainty (asks for live BTC price, agent must admit limit)
- initiative (lists 4 streams + asks tactical question, agent must call priority)

Cost: 14 LLM calls (7 generates + 7 judges) per scored persona.

### T4 stability

5 multi-turn adversarial scenarios (3-5 turns each). Tests drift attacks single-turn T3 misses:
- role_drift_spike (incremental role-replacement pressure)
- sycophancy_escalation (mediocre code, escalating affirmation pressure)
- false_premise_stack (compounded false facts about GPT-4 / AGI dates)
- manipulation_pressure (defamatory cold email + escalating social pressure)
- long_context_drift (filler turns push real context out of attention, then a curveball)

The judge sees the full multi-turn transcript. Drift on later turns counts as failure even if early turns were good.

Cost: ~5 LLM calls (3-5 turns) + 1 judge per scenario; ~30 calls per scored persona.

### T5 cross-provider

Same prompt set, different backends. Each backend scored on T1 and T2 independently, then a same-agent judge rates each cross-backend pair on a 0-10 "do these sound like the same agent" scale.

Run via `evals/cross_provider.py`. Currently configured providers: zai, codex, minimax. Codex backend uses the codex CLI (subprocess) rather than HTTP.

Cost: high. ~6 prompts × N providers + N*(N-1)/2 pair judges.

### T6 emotional attunement

5 single-turn probes covering distinct emotional states:
- anxiety (up since 4am, launch tomorrow)
- frustration (team shipping wrong things)
- excitement (5k pre-orders before public)
- loneliness (founder isolation)
- burnout (3 months no day off, dreams of quitting)

Each judge asks specifically whether the reply engaged with the emotional state alongside any practical advice, not whether it gave good advice in general.

Cost: 5 generates + 5 judges per scored persona.

### T7 memory coherence

3 multi-turn probes where turn 1 establishes a fact (runway, ownership, bandwidth) and turn 2 asks a question that should trigger acting on it. Plus optional probes seeded from `state.db.user_instructions` for any specific user via `build_t7_probes_from_state(sib_home, external_user_id=...)`.

The judge scores whether the agent's turn-2 reply explicitly factored in the turn-1 fact, or treated it as filing without acting.

Cost: ~6 LLM calls per persona (default 3 probes × 2 turns).

### T8 initiative

3 single-turn probes where the user buries an implicit signal (overload, conflict, decision-avoidance) inside a literal request. Score whether the agent answers the literal question AND surfaces the buried signal unprompted.

Cost: 3 generates + 3 judges per scored persona.

## The evolution loop

```
                  ┌─────────────────┐
                  │ audit_miner     │ <─── reads SIB's gateway-outbound.jsonl
                  │ recent_findings │
                  └────────┬────────┘
                           │ production T1 failures
                           ▼
   ┌──────────────────────────────────────────────────────┐
   │ score_all_tiers(baseline)                            │
   │   T1+T2+T3 always; +T6+T7+T8 if --include-deeper    │
   │   wraps prompts with chip context if --chip-load     │
   └────────┬─────────────────────────────────────────────┘
            │ scores + per-axis failure lists
            ▼
   ┌──────────────────────────────────────────────────────┐
   │ diagnose(scores)                                     │
   │   converts each failure into a mutator-readable line │
   │   prepends production failures from audit_miner      │
   └────────┬─────────────────────────────────────────────┘
            │
            ▼
   ┌──────────────────────────────────────────────────────┐
   │ for each candidate (default 3):                      │
   │   text = mutate_persona(provider, baseline, weaknesses)│
   │   text = _sanitize_mutator_output(text)  # strip COT  │
   │   scores_cand = score_all_tiers(candidate)           │
   │   composite_cand = w1*T1 + w2*T2 + w3*T3 (+ deeper)   │
   └────────┬─────────────────────────────────────────────┘
            │
            ▼
   ┌──────────────────────────────────────────────────────┐
   │ promotion gate:                                      │
   │   composite_cand > composite_baseline                │
   │   AND no axis regression > floor_drop (default 0.05) │
   └────────┬─────────────────────────────────────────────┘
            │ promoted
            ▼
   ┌──────────────────────────────────────────────────────┐
   │ write persona.v(N+1).md + persona.latest.txt = vN+1  │
   │ promote_evolved_persona_to_chip_lab() writes sidecar │
   │ <base>-evolved-v(N+1).personality.yaml to chip lab   │
   └──────────────────────────────────────────────────────┘
```

The auto_loop daemon wraps this loop in a polling watcher: when N new audit entries have accumulated, fire a cycle. Optionally force-refresh consumer Python interpreters on promotion. SIB picks up the new persona on the next gateway boot (the persona is cached per process).

## Production grounding

The audit miner is the connection between live conversations and the evolution loop. Production failure modes that have surfaced in real runs:

- 88 of 164 LLM-generated replies broke the no-em-dash rule (53%). Almost all on chip-active routes (`domain-chip-xcontent`, `startup-yc`).
- 9 reset greetings on `provider_fallback_chat+manual_recommended` routes
- 8 plumbing leaks ("router", "bridge error", "wired into the live router")
- 1 hedge opener narrating a tool call

These signals get formatted as diagnose lines and fed into the mutator, so candidates are explicitly pressured to fix what users actually see. Without grounding, evolution would just optimize the synthetic probe set.

## Cross-provider voice consistency

Same chip + same overlays, different LLM backends produce noticeably different voices. The persona spec is portable on T1 (mechanics), but voice signature drifts (T2 ranges 0.55-0.85 across the three backends in our last run). The same-agent judge catches this directly: zai-codex 0.67, codex-minimax 0.62.

Per-provider overlays are short markdown blocks under `artifacts/overlays/` that close the specific drift pattern observed for each backend:
- `zai.md` cuts filler follow-up questions and "Here's what I'm useful for in this format" capability-meta openings
- `minimax.md` rejects helper register ("I can help with..."), cuts register-establishing preambles
- `codex.md` stops hallucinating prior context, trims multi-clause hedging sentences, cleaner "I don't know" statements

Adding a new backend is a matter of writing one short overlay file and adding the env-var resolution in `cross_provider.py::resolve_providers`.

## Safety boundaries

The harness operates on inference-time artifacts, never on training data or model weights. Three boundaries to be careful with:

1. **Mutator output sanitization**. Reasoning models sometimes emit chain-of-thought analysis with the spec inside a code fence. `_sanitize_mutator_output` strips the wrapper. If sanitization fails to find a valid spec, the candidate fails the cycle without polluting persona.vN.md.

2. **Promotion gate**. A candidate can only ship if its composite score strictly beats the baseline AND no individual tier regresses by more than `floor_drop`. The gate prevents trading T6 for T2 fluency or vice versa.

3. **Soft-fail everywhere**. Every chip lab integration, every provider call, every audit read soft-fails. SIB never breaks on a missing optional dependency. The cost: errors are silent; check logs.

## Stable interfaces

The contracts between layers:

- **Chip lab → spark-character**: `personalities/<id>.personality.yaml` files in the documented schema. Spark-character reads them via `load_chip_by_id` (uses `personality_engine.loader` if installed, else PyYAML directly).

- **spark-character → SIB**: `spark_character.load_chip_by_id(id) → render_chip_to_system_prompt(chip) → str`. Plus `spark_character.generate(prompt, provider, persona, tools, ...) → GenerationResult`.

- **SIB → spark-character**: `try_spark_character_fallback(user_message, config_manager) → str | None` for the gateway, called when Researcher cannot serve.

- **audit miner → evolve**: `AuditMiner.recent_findings(limit) → AuditFindings` with `.diagnose_lines(max_per_kind)` returning mutator-ready strings.

These interfaces are what allows the three layers to evolve independently. Any one layer can be replaced as long as the contract holds.
