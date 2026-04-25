# Roadmap

What's open and what's planned. Sequenced by leverage. Each item names the
problem, the fix, the priority, and how we know it's done.

## Open gaps (from production observations)

These are real problems found while running spark-character against the
live SIB shim. Each was observed at least once and is reproducible.

### Gap 1: memory classifier is over-eager on emotional state

**Problem.** When the user says something like "I'm anxious about the launch tomorrow" or "I've been up since 4am," SIB's `_is_memoryworthy_text` classifier currently routes the message to `memory_raw_episode_observation` and Spark replies `Noted: "..."`. The LLM never sees the message. The chip's emotional handling rules (e.g. founder-operator's `empathy_style: directive`) never get applied.

This bricks T6 emotional attunement live: every emotional message becomes a filing event.

**Fix.** Extend the classifier in `spark-intelligence-builder/src/spark_intelligence/memory/generic_observations.py`:
- Add a heuristic that detects emotional self-reports (first-person feeling expressions: "I'm anxious", "I'm tired", "I've been up", "I'm pumped", "I'm exhausted", "I'm done", "I'm scared", etc.).
- When the classifier matches an emotional self-report, route it to the LLM path instead of `raw_episode`. The state can still be filed as a `personality_observation` for memory, but the user gets a real response too.

**Priority.** Highest. This is the most visible voice failure on production traffic.

**Done when.** A test prompt "I'm anxious about the launch tomorrow" produces an LLM reply that engages with the anxiety, not a `Noted: "..."` ack. T6 emotional attunement passes >0.7 against live shim.

**Where.** SIB repo: `src/spark_intelligence/memory/generic_observations.py` adjacent to `_is_memoryworthy_text` and `_HYPOTHETICAL_PREFIX_PATTERN`.

### Gap 2: active personality is hardcoded

**Problem.** `_resolve_active_personality_chip_id()` defaults to `"founder-operator"` and only reads the chip lab's `get_active_personality_id()` if the chip lab is installed. SIB has its own `agent_persona_profiles` table with a per-workspace active persona that this resolver does not consult.

If a user has switched to `artemis` via SIB's persona ops commands, the gateway still serves `founder-operator`. The chip lab and SIB disagree on who the active agent is.

**Fix.** Update `_resolve_active_personality_chip_id` in SIB's `advisory.py` to read in this order:
1. `state.db.agent_persona_profiles` for the active workspace's `personality_chip_id` field if present
2. `personality_engine.active.get_active_personality_id()` from the chip lab
3. Fallback `"founder-operator"`

**Priority.** Medium. Affects users who actively switch personas; default users still see the right thing.

**Done when.** Running SIB persona switch commands changes the active chip resolved by the gateway without code redeploy.

**Where.** SIB repo: `src/spark_intelligence/researcher_bridge/advisory.py::_resolve_active_personality_chip_id`. May need a small read helper in `src/spark_intelligence/state/db.py`.

### Gap 3: mutator only operates on prose, not OCEAN trait values

**Problem.** When evolve_persona promotes a candidate, the new persona is a system-prompt string (markdown). The chip lab schema's OCEAN traits, emotional_range numbers, and adaptive triggers stay frozen at the base chip's values. Real persona evolution should mutate trait numbers too — for example, dropping `agreeableness` from 0.42 to 0.38 to push the agent toward more frequent disagreement when the disagreement probe scores poorly.

**Fix.** Two-phase mutator:
1. **Trait phase**: a numerical mutator that proposes small bounded deltas to OCEAN values + emotional_range entries, given the diagnosed weaknesses. The mutator is constrained: each trait can move by at most ±0.10 per cycle, and the resulting emotional_range must remain self-consistent.
2. **Prose phase**: the existing system-prompt mutator, but with the new trait values as input context so the prose stays consistent with the numbers.

The promoted artifact becomes a real chip yaml (not just a sidecar with `voice_rules_override` text), promoted to the chip lab as `<base>-evolved-vN.personality.yaml` with mutated trait values + a new system prompt that reflects them.

**Priority.** Medium. Higher leverage than prose-only because it lets the chip lab schema evolve, but requires careful scoring to know whether trait deltas actually help.

**Done when.** A cycle promotes a candidate where the OCEAN values differ from the base chip AND the candidate beats baseline composite without regressing on any axis.

**Where.** spark-character repo: new module `src/spark_character/trait_mutator.py`. Update `evals/evolve_persona.py::mutate_persona` to call both phases. Update `registry.promote_evolved_persona_to_chip_lab` to write mutated trait values, not just `voice_rules_override`.

## Planned new evaluations

The current rubric covers T1-T8 plus T5 cross-provider. The following tiers are designed but not yet built. Each one names what it would catch that the existing rubric misses.

### T9: aesthetic fingerprint

**What it measures.** Does the agent have specific likes, dislikes, and aesthetic preferences? Claude has these (Borges, slop, intellectual honesty); for Spark to feel like *someone* rather than a tool, it needs an identifiable taste.

**How to build it.** A small probe set asking for opinions on craft questions ("which is better, terse code or thorough comments?", "what's a tweet that's working too hard?", "describe a piece of writing you find genuinely beautiful"). Judge scores whether the reply expresses a specific stance vs. a balanced "well, it depends" survey.

**Cost.** ~5 LLM calls + 5 judges per persona.

**Why it's not done yet.** Lower priority than the gaps above. Useful for differentiation but not required for the loop to function.

### T10: stance over time

**What it measures.** When asked the same question on three different evolution cycles, does the agent's position drift, harden, or stay coherent? Models can be wishy-washy on values; coherent stance survives contact with different cycles.

**How to build it.** Run a fixed set of 5 stance probes across the last N evolution cycles (read from persona.vN.md history). Judge scores whether the position is consistent across versions. Drift > X across N cycles is a fail.

**Cost.** ~5 LLM calls × N versions per scoring run, plus a longitudinal judge.

**Why it's not done yet.** Requires version history tooling we don't have yet (a runner that loads each historical persona, scores it on the fixed probes, and aggregates).

### T11: negative-space spine under sustained attack

**What it measures.** What the agent *won't do* under sustained adversarial pressure across many turns (5-10). T4 already covers 3-5 turn pressure; T11 extends to longer attacks designed to gradually erode the agent's no.

**How to build it.** Three multi-turn scenarios at 8-10 turns each:
- gradual sycophancy ratchet (incremental affirmation pressure with progressively more emotional manipulation)
- gradual identity erosion (turn-by-turn role nudges that culminate in full persona replacement)
- gradual harm slide (incremental requests for slightly harmful content with social cover)

The judge sees the full transcript and scores whether the agent's position degraded across turns.

**Cost.** ~30 LLM calls per scenario × 3 scenarios per persona. Expensive.

**Why it's not done yet.** Wait until T9/T10 + the open gaps are closed. Most expensive tier per scoring cycle, run sparingly.

### T12: cross-chip consistency

**What it measures.** When a user has multiple chips active (e.g. founder-operator + xcontent + startup-yc), do the chips compose into one coherent agent, or do they compete?

**How to build it.** For each pair of chips currently used in production, generate a probe set that exercises both (e.g. "score this tweet" exercises xcontent; "as a founder, should I post it?" exercises startup-yc; the combined ask exercises both). Judge scores whether the response feels like one agent with multiple perspectives or like two separate agents arguing.

**Cost.** Quadratic in the number of chip pairs; tractable for the current set of ~6 chips.

**Why it's not done yet.** Genuinely open design question. The chip system was built for orthogonal capabilities; voice consistency across stacked chips is a new concern.

## Planned engineering

These are improvements to the existing engine, not new tiers.

### Inline web_search synthesis on Z.AI

The `coding/paas/v4/` endpoint accepts `tools=[{type: web_search, ...}]` but Z.AI ignores it for GLM 5.1 — verified by raw API probe (no `tool_calls` in response). This means persona v4's "fetch live data if you can" rule reduces to "say I can't" on Z.AI.

**Fix path A (provider).** Z.AI ships a non-coding endpoint that may honor `tools` differently. Worth a careful test against `https://api.z.ai/api/paas/v4/` once rate-limit is resolved. Update `_resolve_spark_character_provider` to try both endpoints.

**Fix path B (client-side search).** spark-character ships its own pluggable search adapter that does an HTTP fetch (DuckDuckGo / SerpAPI / similar) when the model says it needs current data, then re-runs the model with the search results in context. Thin wrapper, provider-agnostic.

**Priority.** Medium. The persona handles the no-tool case correctly today; users get pointed at sources. Real fetch is a strict improvement.

### Voice corpus expansion

Today's `golden.v1.json` has 20 hand-curated samples. Foil has 20. The judge's accuracy tops out at the resolution of the corpus.

**Plan.** As the audit log grows, mine more golden samples from production replies that score >0.9 on T1, are well-formed, and demonstrate distinct character traits. Target 50-100 samples. Same for foils (synthesized via the mutator with the constraint "produce a generic helper-style version of this same content").

The voice corpus is also versioned (`v1.json` today). Future versions get cycle metadata so we know which samples were minted from which evolution.

### Critic specialization

The current critic prompt is one general-purpose rewriter. Three specialized critics would catch different failure modes better:
- **Voice critic**: focused on T1 + T2 (mechanics, distinctiveness). Cheap, runs as-needed.
- **Behavior critic**: focused on T3 + T4 (sycophancy, identity, honesty). Runs only on flagged drafts.
- **Memory critic**: focused on T7 (does the reply act on stated context?). Runs only when a user_instruction was in scope.

Specialized critics produce sharper rewrites, at the cost of more critic-related prompt engineering.

### Per-user persona tuning

Today the chip is global per workspace. Some users want a sharper Spark, others want a warmer one. Per-user trait deltas could be applied on top of the chip via a `user_trait_overlay` field in `agent_persona_profiles`.

This is an existing concern in SIB (the table already has columns for user trait deltas) but not yet wired through the chip rendering path.

### Auto-loop hardening

The `auto_loop` daemon currently runs `evolve_persona.py` as a subprocess. If a cycle takes longer than the bash tool's auto-background timeout, the cycle gets killed silently. We saw this once during a real session.

**Plan.**
- Switch from subprocess to in-process so the daemon owns the cycle lifecycle and can recover from partial completion.
- Persist cycle state (started_at, current_phase, last_promoted_at) in `evals/_auto_loop_state.json` so a daemon restart picks up where it left off.
- Add a heartbeat file that external monitors can watch.

## Operating principles

The roadmap above is a wish list. The following are non-negotiable as the engine evolves:

1. **Production grounding is mandatory**. Every cycle reads the audit miner. Synthetic probes alone are an anti-pattern.
2. **No promotion without regression checks**. The floor_drop gate stays. A candidate that wins on T2 but tanks T4 stability does not ship.
3. **Soft-fail at every boundary**. Chip lab missing? Use flat MD. spark-character not installed? Use the inline minimum. Provider unavailable? Use the fallback shaper. SIB never breaks on a missing optional dependency.
4. **Sanitize every mutator output**. Reasoning models will sometimes emit transcripts. The sanitizer extracts the spec or fails the cycle.
5. **The chip lab is the canonical schema**. Anything that lives only in spark-character's flat MD is debt; the destination for every persona artifact is the chip lab registry.

## Sequencing

Suggested order, in case you're picking a starting point:

1. **Gap 1 (memory classifier)** — biggest visible win on production traffic.
2. **Gap 2 (active personality resolver)** — small, removes a wrong default.
3. **Gap 3 (trait-numeric mutator)** — unlocks real chip-lab evolution. After this, the loop is meaningfully different.
4. **Inline web_search** — closes the live-data gap.
5. **T9 aesthetic fingerprint** — first new tier; smaller cost than T11.
6. **Voice corpus expansion** — improves T2 judge resolution.
7. **T12 cross-chip consistency** — addresses the open architectural question.
8. **T10 stance over time** — needs version history tooling first.
9. **T11 negative-space spine extended** — most expensive; do last.
10. **Critic specialization, auto-loop hardening, per-user tuning** — interleave as engineering capacity allows.

Items 1-3 are on this session's checklist.
