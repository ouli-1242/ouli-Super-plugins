# Agent Compatibility Matrix

Skills follow the shared [Agent Skills specification](https://agentskills.io), so **basic skills work across agents**. Advanced frontmatter features, however, have uneven support — a skill that relies on them may not run on the user's target agent. Check before recommending:

| Feature | Cursor | Claude Code | Codex | OpenCode | Hermes |
| --- | --- | --- | --- | --- | --- |
| Basic skills | ✓ | ✓ | ✓ | ✓ | ✓ |
| `allowed-tools` | ✓ | ✓ | ✓ | ✓ | ⚠ |
| Hooks | ✓ | ✓ | ✗ | ✗ | ⚠ |
| `context: fork` | ✗ | ✓ | ✗ | ✗ | ⚠ |

Key takeaways:

- **Cursor supports hooks**, but through a standalone `hooks.json` (`~/.cursor/hooks.json` for user scope, `.cursor/hooks.json` for project scope) — not via hooks embedded in SKILL.md frontmatter. That is the one difference from Claude Code, which supports both.
- **`context: fork`** remains Claude Code-only; **hooks** are unavailable on Codex and OpenCode.
- **Hermes** (⚠) is agentskills.io-compatible for basic skills; its support for `allowed-tools`, hooks, and `context: fork` is not confirmed in the compatibility table — verify against [Hermes docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills) before recommending a skill that relies on them.

> Note: the table above reflects the original author's survey. The official `skills` CLI README maintains a newer 18-column compatibility table — cross-check it before making a compatibility-sensitive recommendation.