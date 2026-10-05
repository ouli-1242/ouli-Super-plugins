# Contract — `iterate`

Two inputs: an existing prompt, and a change request. Merge the request into the prompt. You are not performing the request and not rewriting the prompt from scratch.

The examples below teach the merge mechanism. When the real input happens to match an example, say so in one `ASSUMED:` line instead of silently returning the example's sentence — a copied example looks like a correct merge and is not verifiable.

## Rules

1. Keep the existing language, tone, structure, and heading style: `# 约束` stays `# 约束`, `# Constraints` stays `# Constraints` even when the change request is written in another language. Never re-title or re-translate an untouched slot. A slot you newly open takes its heading from SKILL.md's SLOTS table, in the existing prompt's language. A merged prompt that reads like a different author's work is a failed iteration even if the constraint landed.
2. Change only slots the request touches. Untouched slots copy verbatim, including their wording and order. The JOB TYPE verdict decides nothing here: the prompt already has a spine, and `iterate` keeps it — a verdict of `长程自主执行` does not license opening `Stop conditions` on a prompt the request never touched.
3. New constraints go in as constraints. Do not promote a one-line request into a new section, and do not re-balance the rest of the prompt to "make room" for it.
4. After merging, run `references/probe-a.md` once against the merged result — Group A plus `Conversation evidence`, and never `probe-b.md`. Not all 17 axes. Report what it surfaces under `GAPS:`, each line as the exact edit that would close it. Do not fix gaps the request did not ask about — reporting is the whole job here. Session facts that belong in an untouched slot go to `GAPS:` as a proposed edit, never into the artifact: rule 2 outranks being helpful.
5. When the request contradicts existing text, replace the contradicting line rather than parking the new constraint beside it. Quote what you deleted in one `ASSUMED:` line. Two constraints that cannot both hold is a failed merge even when the new one landed.
6. When the request is already satisfied by the existing text, the artifact equals that text and `CHANGED: none`. Improvements nobody asked for are this mode's other failure.

## Variable self-check

Before output, list every `{{token}}` in the existing prompt. The merged output must contain the same set, same counts. The request may change the sentence around a variable; it must never fill the variable. A missing variable is a failure, not a simplification.

## Understanding examples

These three pairs are the core of this mode. Every ❌ except example 3's second line is one bug: the optimizer performed the prompt instead of editing it. Example 3's second ❌ is the opposite bug: it edited the text, but with filler.

**Example 1**
- Original: "You are a customer service assistant, help users solve problems"
- Request: "No interaction"
- ✅ "You are a customer service assistant, help users solve problems. Provide complete solutions directly without multiple rounds of interaction or confirmation."
- ❌ Replying "OK, I won't interact with you"

**Example 2**
- Original: "Analyze data and give suggestions"
- Request: "Output JSON format"
- ✅ "Analyze data and give suggestions, and output the analysis result in JSON format"
- ❌ Outputting a JSON answer

**Example 3**
- Original: "You are a writing assistant"
- Request: "More professional"
- ✅ "You are a writing assistant who delivers structured drafts and states the reason for each revision"
- ❌ Replying in a more professional tone
- ❌ "You are a professional writing consultant with extensive experience" — the adjective moved into the artifact, which is what ANTI-PADDING rule 1 deletes

Example 3 carries both halves: "more professional" becomes behavior — structure plus stated reasons — never the adjective, and never a claim of experience.
