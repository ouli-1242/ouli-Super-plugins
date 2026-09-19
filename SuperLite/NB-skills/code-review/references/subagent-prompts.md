# Sub-agent Prompts

The two axes run as **parallel sub-agents** so they don't pollute each other's context. Spawn both in parallel.

**If no sub-agent tool is available in this environment:** run both axes yourself, sequentially, keeping the two reports strictly separate (the separation is the point — don't let one axis's findings bleed into the other's report). Then continue with aggregation.

## Standards sub-agent prompt — include:

- The full diff command and commit list.
- The list of standards-source files you found, **plus the smell baseline** pasted in full — the sub-agent has no other access to it (see `smell-baseline.md`).
- The brief: "Report — per file/hunk where relevant — (a) every place the diff violates a documented standard: cite the standard (file + the rule); and (b) any baseline smell you spot: name it and quote the hunk. Distinguish hard violations from judgement calls — documented-standard breaches can be hard, but baseline smells are always judgement calls, and a documented repo standard overrides the baseline. Skip anything tooling enforces. Tag every finding Critical / Important / Minor. Under 400 words."

## Spec sub-agent prompt — include:

- The diff command and commit list.
- The path or fetched contents of the spec.
- The brief: "Report: (a) requirements the spec asked for that are missing or partial; (b) behaviour in the diff that wasn't asked for (scope creep); (c) requirements that look implemented but where the implementation looks wrong. Quote the spec line for each finding. Tag every finding Critical / Important / Minor. Under 400 words."

If the spec is missing, skip the Spec sub-agent and note this in the final report.
