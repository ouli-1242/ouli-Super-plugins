# Agent-Doc Writing — Reference

Absorbed from mattpocock's `writing-for-agents`. Reference for writing any document an agent consumes: a skill body, an `AGENTS.md`/`CLAUDE.md` line, a doc reached by a pointer. The packaging differs; the levers do not — the agent takes the same _process_ every run, so the writing's job is to make that process predictable.

## Context pointers

A **context pointer** is a reference held in the agent's context that names out-of-context material and encodes the condition for reaching it. A skill's `description` is one; a line in `AGENTS.md` naming a doc is the same object. The pointer's _wording_, not its target, decides when — and how reliably — the agent reaches the material. A must-have target behind a weakly worded pointer is a variance bug: sharpen the wording first; inline the material only if sharpening fails.

A pointer does two jobs: states what the material is, and lists the **branches** that should trigger reaching it (a branch = a distinct case the document handles, so different runs take different paths). Every word of an always-loaded pointer costs on every turn, so it earns harder pruning than the body:

- **Front-load the leading word** — the pointer is where its triggering work happens.
- **One trigger per branch** — synonyms renaming one branch are one branch written twice; collapse them.
- **Cut identity the body already carries.**

## The two loads

Every document and pointer spends one of two budgets:

- **Context load** — the cost of always-loaded material on the agent's window: an `AGENTS.md` line, a skill description, anything in context every turn, spending tokens whether or not it fires.
- **Cognitive load** — the cost on the human: which documents exist and when to reach for each. The human is the index. Not a cost to minimize — it is the price of human agency; spend it where human judgment matters.

Material reached only through a pointer escapes context load at the price of the pointer's own line; material with no pointer rides entirely on cognitive load.

## Information hierarchy

Content is either **steps** (ordered actions) or **reference** (definitions, rules, facts consulted on demand). The core decision is where each piece sits on the ladder of how immediately the agent needs it:

1. **In-file step** — what the agent does, in order. The primary tier.
2. **In-file reference** — consulted on demand; a flat peer-set of rules on one rung is a fine arrangement, not a smell.
3. **Disclosed reference** — pushed to a separate file behind a context pointer, loaded only when the pointer fires.

Push too little down and the top bloats; push too much and you hide material the agent needs — that tension is the whole decision.

- **Progressive disclosure** is the move down the ladder so the top stays legible — not primarily a token optimization. The cleanest disclosure test is branching: inline what every branch needs, push behind a pointer what only some branches reach. In-file reference that should be disclosed buries the steps and turns attending to them into a coin-flip.
- **Co-location** is the within-file companion: keep a concept's definition, rules, and caveats under one heading, so reading one part brings its neighbors. The test: the document reads like documentation written for the agent.
- **Sprawl** is the failure mode: a document too long even when every line is live. The cure is the ladder — disclose reference behind pointers, split by branch or sequence.

## Completion criteria

Every step ends on a **completion criterion** — the condition that tells the agent the work is done.

- **Clarity**: can the agent tell done from not-done? A vague bound ("understanding reached") invites **premature completion**. Defend in order: sharpen the bound first (local and cheap); only if it is irreducibly fuzzy _and_ you observe the rush, hide the later steps by splitting the sequence — hiding works only across a real context boundary (handoff, subagent dispatch; an inline call leaves the steps in context and clears nothing).
- **Demand**: how much the criterion requires. "Every modified module accounted for" forces thorough work where "produce a change list" does not. Demand drives **legwork** — the digging latent in the wording rather than written as its own step — and binds flat reference just as it binds sequences.

The strongest criteria are both checkable and exhaustive.

## Leading words

A **leading word** is a compact concept already in the model's pretraining that the agent thinks with while running the document (_seam_, _tracer bullet_, _red_). Repeated as a token, never a sentence, it anchors a region of behavior in the fewest tokens by recruiting priors. Coin your own only if you define it clearly — a made-up word recruits no priors; an existing word is free.

Hunt for restatements a leading word retires: "fast, deterministic, low-overhead" → _tight_; "a loop you believe in" → _red_. Fewer tokens, and a sharper hook for the agent's thinking.

**Negation** is the neighboring failure mode: steering by prohibition drags the forbidden behavior into context and makes it more available — the ban half-reads as an instruction to do the thing. Prompt the **positive** ("write one-line comments") so the banned form is never spoken. A prohibition earns its place only as a hard guardrail that cannot be phrased positively; pair it with the positive target even then.

## Pruning

- **Single source of truth** per meaning — one authoritative place, so changing behavior is a one-place edit. Duplication costs maintenance, tokens, and inflates prominence.
- **The environment is a source of truth too** (`package.json` scripts, config, directory layout, `--help`). A document that restates it is a cache — earn the load only when the lookup is expensive. Cache what the agent cannot find by looking: the unwritten convention, the reason behind a choice, the gotcha no config confesses.
- **Relevance**: every line must still bear on what the document does — never-bearing exposition goes, stale lines go. Without pruning discipline the default fate is **sediment**: stale layers that settle because adding feels safe and removing feels risky.
- **No-ops**: an instruction the model already obeys by default pays load to say nothing. The test (does it change behavior versus the default?) is model-relative — settle disagreements by running the document, not by debate. When a sentence fails, delete the whole sentence. The test also grades leading words: a word too weak to beat the default (_be thorough_) needs a stronger word (_relentless_), not a different technique.

## Skill mechanics (invocation choice)

- **Model-invoked** skill: carries a `description`, so the agent can fire it autonomously and other skills can reach it. User typing still works — a description only adds discovery, never removes the human's reach. The description is a context pointer permanently loaded: permanent context load in exchange for discoverability. Mechanics: omit `disable-model-invocation`; write a model-facing description carrying the trigger branches.
- **User-invoked** skill (`disable-model-invocation: true`): stripped from the agent's reach — only the human (and no other skill) can invoke it. Zero context load; pays cognitive load: you are the index that must remember it exists. The `description` becomes human-facing — a one-line summary, trigger lists stripped.

Pick model-invocation only when the agent must reach the skill on its own, or another skill must. If it only ever fires by hand, make it user-invoked and pay no context load. Shared reference two user-invoked skills both need can live in neither (neither can fire the other) — push it to a plain file any skill can point at.

**Splitting by invocation**: split off a model-invoked skill when it has a distinct leading word that should trigger it on its own, or another skill must reach it — the new always-loaded description must be worth its load.

**Router skills**: when user-invoked skills multiply past what one human remembers, a router skill names the others and when to reach for each. SuperWork's router is `superwork` — a new skill that owns a lifecycle stage registers in its route table (see the parent skill's checklist); it does not become a second router.
