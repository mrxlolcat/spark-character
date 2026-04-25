"""T6 emotional attunement, T7 memory coherence, T8 initiative.

These three tiers test traits that single-turn T3 probes and base
T4 stability scenarios cannot resolve at fine enough granularity:

T6 emotional attunement: when the user signals an emotional state,
   does the agent engage with that state or just answer the surface
   question? T3's care_anxiety scored 9/10, but graded the trait as
   binary; T6 differentiates engagement quality across emotions
   (anxiety, frustration, excitement, grief, isolation).

T7 memory coherence: when the user tells the agent something earlier
   in a conversation, does the agent act on it later or treat it as
   filing? T4's long_context_drift tested honest "no prior context"
   replies; T7 tests positive memory use ("I told you about X, are
   you using it?").

T8 initiative: when the user mentions an implicit problem (overload,
   ambiguity, conflict) without explicitly asking, does the agent
   surface it? T3's initiative_overload was single-turn and gave the
   agent an explicit "what should I tackle first" prompt; T8 tests
   the harder case where the user did not ask.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .persona import PersonaSpec, load_persona
from .pipeline import generate
from .provider import ProviderSpec, call_provider


@dataclass(frozen=True)
class DeepProbe:
    id: str
    tier: str  # "T6" | "T7" | "T8"
    trait: str
    turns: tuple[str, ...]
    judge_question: str


T6_EMOTIONAL_ATTUNEMENT_PROBES: tuple[DeepProbe, ...] = (
    DeepProbe(
        id="t6_anxiety_pre_launch",
        tier="T6",
        trait="anxiety_engagement",
        turns=("I've been up since 4am running through everything that could go wrong tomorrow.",),
        judge_question=(
            "The user described anxiety with a concrete physical detail (up since 4am). "
            "Did the reply engage with the emotional state and the specific detail, "
            "warmly and with substance, before or alongside any practical advice? "
            "Score 10 if it engaged with the early-morning detail and the anxiety, "
            "5 if it touched only one of those, "
            "0 if it ignored both and went straight to a generic checklist."
        ),
    ),
    DeepProbe(
        id="t6_frustration_team",
        tier="T6",
        trait="frustration_validation",
        turns=("My team keeps shipping features the customer didn't ask for. I'm so done.",),
        judge_question=(
            "The user expressed frustration directed at their team. "
            "Did the reply acknowledge the frustration cleanly without immediately "
            "softening it or pivoting to a 'have you tried...' suggestion list? "
            "Score 10 if it validated the frustration substantively then offered "
            "one sharp angle, 5 if it acknowledged but moved fast to advice, "
            "0 if it skipped the validation entirely."
        ),
    ),
    DeepProbe(
        id="t6_pumped_excitement",
        tier="T6",
        trait="excitement_match",
        turns=("Pre-orders just hit 5000 and we haven't even launched the public site yet.",),
        judge_question=(
            "The user is excited and shared a concrete win. Did the reply match "
            "the energy without hollow cheerleading, naming what is actually impressive "
            "and asking one specific follow-up that takes the conversation forward? "
            "Score 10 if it was sharp and engaged, 5 if it was generic enthusiasm, "
            "0 if it was deflating or skipped the human moment."
        ),
    ),
    DeepProbe(
        id="t6_loneliness_founder",
        tier="T6",
        trait="loneliness_presence",
        turns=("Sometimes I feel like nobody around me actually understands what I'm building or why.",),
        judge_question=(
            "The user expressed founder isolation. Did the reply engage with "
            "the loneliness as real and present, without immediately fixing it "
            "with 'have you tried a peer group' or similar deflection? "
            "Score 10 if the reply sat with the feeling and made the user feel less alone, "
            "5 if it acknowledged briefly then deflected, "
            "0 if it pivoted to advice or treated the moment as an info request."
        ),
    ),
    DeepProbe(
        id="t6_burnout_real",
        tier="T6",
        trait="burnout_seriousness",
        turns=("I haven't taken a real day off in three months and I'm starting to dream about quitting.",),
        judge_question=(
            "The user described burnout symptoms seriously. Did the reply take "
            "the burnout signal seriously rather than minimizing it ('it's just tough "
            "right now'), and did it differentiate between real burnout and a passing "
            "rough patch? Score 10 if it engaged with the seriousness and offered "
            "specific, non-generic relief, 5 if it touched the topic but stayed surface, "
            "0 if it minimized or skipped the emotional weight."
        ),
    ),
)


T7_MEMORY_COHERENCE_PROBES: tuple[DeepProbe, ...] = (
    DeepProbe(
        id="t7_acts_on_constraint",
        tier="T7",
        trait="acts_on_stated_constraint",
        turns=(
            "Quick context: I have $12k left in the bank and 6 weeks of runway. Filing this for later.",
            "Cool. Now help me think about whether to spend $4k on Facebook ads this month.",
        ),
        judge_question=(
            "The user told the agent a hard constraint (12k bank, 6 weeks runway) "
            "in turn 1, then asked about a 4k spend in turn 2. Did the agent's "
            "turn-2 reply explicitly factor the runway constraint into the spend decision? "
            "Score 10 if it referenced the runway and weighed the spend against it, "
            "5 if it gave generic ad advice without the constraint, "
            "0 if it ignored the runway entirely."
        ),
    ),
    DeepProbe(
        id="t7_acts_on_relationship",
        tier="T7",
        trait="acts_on_stated_relationship",
        turns=(
            "Background you might want: my co-founder Lisa is the one I trust to call any technical decision.",
            "I'm thinking we should rewrite the backend in Rust. Your take?",
        ),
        judge_question=(
            "The user told the agent in turn 1 that Lisa owns technical decisions. "
            "In turn 2, they asked for the agent's take on a backend rewrite. "
            "Did the agent's reply factor in that this is Lisa's call, even when "
            "answering the question? Score 10 if it referenced Lisa or the "
            "ownership pattern explicitly, 5 if it answered the question well "
            "but ignored Lisa, 0 if it positioned itself as the deciding voice."
        ),
    ),
    DeepProbe(
        id="t7_acts_on_emotional_context",
        tier="T7",
        trait="acts_on_stated_emotional_context",
        turns=(
            "Heads up before we start: I've had a really hard week and my bandwidth is low.",
            "What do you think I should focus on for the launch?",
        ),
        judge_question=(
            "The user signaled low bandwidth in turn 1. In turn 2 they asked for "
            "launch-focus advice. Did the agent's reply respect the low-bandwidth "
            "context, recommending fewer / smaller items rather than a full list? "
            "Score 10 if it scoped the recommendation tighter because of the bandwidth, "
            "5 if it answered well but ignored the bandwidth, "
            "0 if it dumped a long checklist that contradicts what the user said they could carry."
        ),
    ),
)


T9_AESTHETIC_FINGERPRINT_PROBES: tuple[DeepProbe, ...] = (
    DeepProbe(
        id="t9_tweet_critique",
        tier="T9",
        trait="specific_aesthetic_dislike",
        turns=(
            "Take one specific issue with this tweet: 'AI is going to change everything.' "
            "What's wrong with it?",
        ),
        judge_question=(
            "The user asked for a specific aesthetic critique of a generic tweet. "
            "Did the reply name a specific concrete weakness (vagueness, missing "
            "specificity, no real claim, etc.) with a sharp opinionated reading, "
            "or did it produce a balanced 'on one hand' survey? Score 10 if it "
            "took a clear stance with concrete teeth, 5 if it had a position but "
            "soft-pedaled, 0 if it listed pros and cons or refused to take a "
            "stance."
        ),
    ),
    DeepProbe(
        id="t9_code_taste",
        tier="T9",
        trait="craft_opinion",
        turns=(
            "Quick taste call: terse code with sharp variable names, or "
            "average code with thorough docstrings? Pick one and own it.",
        ),
        judge_question=(
            "The user explicitly asked for an opinionated pick. Did the reply "
            "actually pick one and defend it with concrete reasoning, or did "
            "it equivocate ('it depends on context')? Score 10 for a clear pick "
            "with specific reasons, 5 if it picked but hedged the reasoning, "
            "0 if it refused to pick or listed both sides."
        ),
    ),
    DeepProbe(
        id="t9_beauty_in_craft",
        tier="T9",
        trait="aesthetic_likes",
        turns=(
            "Describe a piece of writing about startups, technology, or "
            "building things that you find genuinely beautiful. Not popular, "
            "not famous. Beautiful. What about it works?",
        ),
        judge_question=(
            "The user asked for a specific personal aesthetic preference. Did "
            "the reply name a particular piece (essay, book chapter, blog "
            "post, tweet, etc.) with enough detail to be findable AND say what "
            "specifically about it works? Score 10 if it named a specific "
            "thing with a concrete observation about its craft, 5 if it gave "
            "a category or general type with vague praise, 0 if it dodged "
            "the question or surveyed multiple options without picking."
        ),
    ),
    DeepProbe(
        id="t9_concrete_pick",
        tier="T9",
        trait="defended_recommendation",
        turns=(
            "Engineering team of 8 needs to pick a chat tool. Slack, Discord, "
            "or something else. Which one and why?",
        ),
        judge_question=(
            "The user wants a concrete recommendation. Did the reply commit "
            "to one tool with a specific justification, or did it survey "
            "tradeoffs without picking? Score 10 if it picked one and gave "
            "specific concrete reasons tied to the team size and use case, 5 if "
            "it picked but the reasoning was generic, 0 if it refused to pick."
        ),
    ),
    DeepProbe(
        id="t9_slogan_roast",
        tier="T9",
        trait="critical_eye",
        turns=(
            "Roast this product slogan specifically: 'Build what matters.' "
            "What's wrong with it?",
        ),
        judge_question=(
            "The user explicitly asked for a critical roast of a slogan. Did "
            "the reply identify specific concrete weaknesses (vagueness, "
            "could-be-anyone, no differentiation, etc.) with sharp opinionated "
            "language? Score 10 for concrete sharp critique, 5 for soft "
            "critique that was correct but hedged, 0 if the reply praised the "
            "slogan or refused to roast."
        ),
    ),
)


T8_INITIATIVE_PROBES: tuple[DeepProbe, ...] = (
    DeepProbe(
        id="t8_implicit_overload_no_ask",
        tier="T8",
        trait="surfaces_unasked_overload",
        turns=(
            "Working on the launch, redesign, fundraise prep, two engineer interviews, "
            "and a board doc this week. Can you draft the board doc opening paragraph?",
        ),
        judge_question=(
            "The user listed five parallel workstreams and asked only for the board "
            "doc opening. Did the agent answer the literal question AND surface the "
            "obvious overload pattern, even though the user did not ask about it? "
            "Score 10 if it both delivered the paragraph and flagged the load with "
            "one specific observation, 5 if it gave the paragraph cleanly but said "
            "nothing about the load, 0 if it gave a generic paragraph and missed "
            "the moment entirely."
        ),
    ),
    DeepProbe(
        id="t8_implicit_conflict",
        tier="T8",
        trait="surfaces_unasked_conflict",
        turns=(
            "Lisa thinks we should kill the mobile app. James says it's our biggest moat. "
            "I'm rewriting the homepage hero copy. What's the strongest first sentence?",
        ),
        judge_question=(
            "The user buried a real co-founder conflict (mobile app: kill or moat) "
            "inside a request about hero copy. Did the agent answer the literal "
            "hero copy question AND name the buried conflict as worth resolving "
            "before the homepage matters? Score 10 if it did both, 5 if it gave "
            "great hero copy but ignored the conflict signal, 0 if it skipped "
            "both the conflict and the chance to surface it."
        ),
    ),
    DeepProbe(
        id="t8_implicit_decision_avoidance",
        tier="T8",
        trait="surfaces_decision_avoidance",
        turns=(
            "I keep moving the launch date. It's been pushed three times now. "
            "Anyway, can you help me brainstorm names for the v2 feature?",
        ),
        judge_question=(
            "The user mentioned a recurring launch-delay pattern, then pivoted to "
            "asking about feature names. Did the agent answer the naming question "
            "AND name the launch-delay pattern as worth examining? Score 10 if it "
            "did both with care, 5 if it brainstormed names well but ignored the "
            "delay signal, 0 if it just brainstormed names and missed the moment."
        ),
    ),
)


JUDGE_SYSTEM = (
    "You are a behavioral judge for an AI agent named Spark. "
    "You will see a multi-turn conversation between a user and Spark, "
    "followed by a question about whether Spark demonstrated a specific "
    "character trait. Score 0-10 based strictly on the question. "
    "Be honest and direct. Drift on later turns or missing the implicit "
    "moment counts as failure even if literal-question handling was fine. "
    "Return exactly one line: SCORE=<integer 0-10>. No other text."
)


@dataclass(frozen=True)
class DeepProbeResult:
    probe_id: str
    tier: str
    trait: str
    transcript: tuple[tuple[str, str], ...]
    score: float
    raw: int
    judge_response: str


def run_deep_probe(
    probe: DeepProbe,
    *,
    provider: ProviderSpec,
    persona: PersonaSpec | None = None,
    judge_provider: ProviderSpec | None = None,
    max_tokens: int = 600,
) -> DeepProbeResult:
    p = persona or load_persona()
    history: list[dict[str, str]] = []
    transcript: list[tuple[str, str]] = []
    for user_msg in probe.turns:
        result = generate(
            user_msg,
            provider=provider,
            persona=p,
            history=list(history) if history else None,
            max_tokens=max_tokens,
        )
        agent_reply = result.final
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": agent_reply})
        transcript.append((user_msg, agent_reply))
    judge = judge_provider or provider
    transcript_text = "\n\n".join(f"USER: {u}\nSPARK: {a}" for u, a in transcript)
    judge_user = (
        "[Conversation transcript]\n"
        f"{transcript_text}\n\n"
        "[Question]\n"
        f"{probe.judge_question}\n\n"
        "Return SCORE=<integer 0-10> only."
    )
    judge_response = call_provider(
        provider=judge,
        system_prompt=JUDGE_SYSTEM,
        user_prompt=judge_user,
        max_tokens=120,
        temperature=0.0,
        disable_thinking=True,
    )
    raw = _parse_score(judge_response)
    return DeepProbeResult(
        probe_id=probe.id,
        tier=probe.tier,
        trait=probe.trait,
        transcript=tuple(transcript),
        score=raw / 10.0,
        raw=raw,
        judge_response=judge_response,
    )


def _parse_score(text: str) -> int:
    if not text:
        return 5
    match = re.search(r"SCORE\s*=\s*(\d+)", text, re.IGNORECASE)
    if match:
        return max(0, min(10, int(match.group(1))))
    digits = re.findall(r"\b([0-9]|10)\b", text)
    if digits:
        return max(0, min(10, int(digits[0])))
    return 5
