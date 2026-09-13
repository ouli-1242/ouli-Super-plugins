# SDO: Triggering Conditions Only (BAD vs GOOD)

When a description summarizes the skill's workflow, agents follow the description instead of reading the skill body. A description saying "code review between tasks" made an agent do ONE review even though the skill's flowchart required TWO. Changing it to pure triggering conditions fixed it. A workflow summary is a shortcut that makes the body documentation agents skip.

```yaml
# BAD: summarizes workflow — agents follow this instead of reading
description: Use when executing plans - dispatches subagent per task with code review between tasks

# GOOD: triggering conditions only
description: Use when executing implementation plans with independent tasks
```
